"""ContextBuilder — plan sections 6, 7, 9, 18.

Rule: OLD HISTORY -> SUMMARY, RECENT HISTORY -> COMPLETE RESPONSES.

- DB always holds the FULL TRANSCRIPT (every turn).
- The LLM only sees ACTIVE CONTEXT:
    original question + latest summary + last N complete turns + role prompt.
"""
from __future__ import annotations

import json

from sqlalchemy import desc
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from .token_counter import estimate_messages_tokens


def get_latest_summary(db: Session, conversation_id: int) -> models.ContextSummary | None:
    return (
        db.query(models.ContextSummary)
        .filter(models.ContextSummary.conversation_id == conversation_id)
        .order_by(desc(models.ContextSummary.id))
        .first()
    )


def get_recent_turns(db: Session, conversation_id: int, limit: int) -> list[models.Turn]:
    rows = (
        db.query(models.Turn)
        .filter(
            models.Turn.conversation_id == conversation_id,
            models.Turn.status == "ok",
        )
        .order_by(desc(models.Turn.turn_number))
        .limit(limit)
        .all()
    )
    return list(reversed(rows))


CHAT_TYPE_INSTRUCTIONS: dict[str, str] = {
    "research": (
        "Chat mode: Research & Analysis. Hypothesize, cite mechanisms/evidence, "
        "challenge assumptions, and synthesize what is established vs unresolved."
    ),
    "debate": (
        "Chat mode: Formal Debate. Argue your assigned side (affirmative/negative), "
        "rebut directly, stay on-thesis, and let the judge weigh argument strength."
    ),
    "architecture": (
        "Chat mode: Software Architecture. Design modules/interfaces, flag security, "
        "reliability, latency and cost trade-offs, and give concrete implementation steps."
    ),
    "brainstorm": (
        "Chat mode: Brainstorming & Strategy. Generate bold ideas, advocate the user, "
        "check feasibility/cost, and converge toward a prioritized MVP roadmap."
    ),
    "custom": "Chat mode: Custom. Follow your assigned role prompt exactly.",
}

KNOWN_ROLES: list[str] = [
    "Lead Researcher",
    "Skeptic",
    "Peer Reviewer",
    "Empirical Specialist",
    "Mathematical Analyst",
    "Synthesizer",
    "Affirmative",
    "Proponent",
    "Negative",
    "Opponent",
    "Cross-Examiner",
    "Moderator",
    "Judge",
    "System Architect",
    "Security Auditor",
    "Security & Reliability Auditor",
    "Performance Specialist",
    "Reviewer",
    "Pragmatist",
    "Visionary Ideator",
    "Ideator",
    "Customer Advocate",
    "User Advocate",
    "Pragmatic Realist",
    "Product Strategist",
]


def extract_role_name(prompt: str | None) -> str | None:
    """Derive a display role from a system prompt (plan §3).

    Matches known role labels first, else parses "You are the/a <role>.".
    """
    if not prompt or not prompt.strip():
        return None
    text = prompt.strip()
    lowered = text.lower()
    for role in KNOWN_ROLES:
        if role.lower() in lowered:
            return role
    import re

    m = re.search(r"you are (?:the|a|an)\s+([^.:\n]{2,60})", text, re.IGNORECASE)
    if m:
        candidate = m.group(1).strip().strip("'\"")
        # Title-case short candidates for badge display.
        if len(candidate) <= 60:
            return " ".join(w.capitalize() for w in candidate.split())
    return None


def resolve_system_prompt(
    model: models.LLMModel,
    link: models.GroupModel | None,
    chat_type: str = "research",
) -> tuple[str, str | None]:
    """Per-model role; group-level override wins (plan section 10).

    Combines model prompt / override with chat-type context instructions.
    Returns (effective_prompt, role_name).
    """
    if link and (link.system_prompt_override or "").strip():
        base = link.system_prompt_override.strip()
    else:
        base = (model.system_prompt or "").strip()
    role_name = extract_role_name(base)
    instruction = CHAT_TYPE_INSTRUCTIONS.get((chat_type or "research").lower(), "")
    if instruction and instruction.lower() not in base.lower():
        effective = f"{base}\n\n{instruction}" if base else instruction
    else:
        effective = base
    if not effective:
        effective = (
            f"You are {model.name}, a researcher in a multi-LLM research group. "
            "Read the original question and previous researchers' responses carefully. "
            "Build on useful arguments, correct errors with evidence, state uncertainty explicitly."
        )
    return effective, role_name


def build_context(
    db: Session,
    conversation: models.Conversation,
    next_model: models.LLMModel,
    link: models.GroupModel | None = None,
    max_turns: int | None = None,
    max_tokens: int | None = None,
) -> tuple[list[dict[str, str]], dict]:
    """Return (messages, debug_payload). debug_payload is stored as Turn.input_context."""
    max_turns = max_turns if max_turns is not None else settings.MAX_CONTEXT_TURNS
    max_tokens = max_tokens if max_tokens is not None else settings.MAX_CONTEXT_TOKENS

    chat_type = getattr(conversation, "chat_type", None) or "research"
    system_prompt, role_name = resolve_system_prompt(next_model, link, chat_type)
    if not system_prompt:
        system_prompt = (
            f"You are {next_model.name}, a researcher in a multi-LLM research group. "
            "Read the original question and previous researchers' responses carefully. "
            "Build on useful arguments, correct errors with evidence, state uncertainty explicitly."
        )

    summary_row = get_latest_summary(db, conversation.id)
    recent = get_recent_turns(db, conversation.id, max_turns)

    # Token budget: shrink recent window if needed (never drop the original question).
    messages = _assemble(conversation.original_prompt, summary_row, recent, system_prompt)
    while len(recent) > 1 and estimate_messages_tokens(messages) > max_tokens:
        recent = recent[1:]
        messages = _assemble(conversation.original_prompt, summary_row, recent, system_prompt)

    # Human-readable user block (also what providers without chat roles can consume).
    parts = [f"Original research question:\n{conversation.original_prompt}"]
    if summary_row:
        parts.append(
            f"Summary of older history (up to turn {summary_row.up_to_turn_number}):\n"
            f"{summary_row.summary}"
        )
    if recent:
        transcript = "\n\n".join(
            f"[Turn {t.turn_number} | Round {t.round_number} | "
            f"{t.model.name if t.model else 'unknown'}]:\n{t.response}"
            for t in recent
        )
        parts.append(f"Recent complete responses (most recent last):\n{transcript}")
    parts.append(
        "Now contribute your own analysis as the next researcher. "
        "Do not merely repeat; advance the investigation."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "\n\n---\n\n".join(parts)},
    ]

    debug_payload = {
        "conversation_id": conversation.id,
        "next_model_id": next_model.id,
        "next_model_name": next_model.name,
        "original_prompt": conversation.original_prompt,
        "summary_used": summary_row.summary if summary_row else None,
        "summary_up_to_turn": summary_row.up_to_turn_number if summary_row else None,
        "recent_turn_numbers": [t.turn_number for t in recent],
        "messages": messages,
        "role_name": role_name,
        "chat_type": chat_type,
        "system_prompt": system_prompt,
    }
    return messages, debug_payload


def _assemble(original_prompt, summary_row, recent, system_prompt):
    msgs = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": original_prompt},
    ]
    if summary_row:
        msgs.append({"role": "user", "content": summary_row.summary})
    for t in recent:
        msgs.append({"role": "user", "content": t.response or ""})
    return msgs


def serialize_context(debug_payload: dict) -> str:
    return json.dumps(debug_payload, ensure_ascii=False)
