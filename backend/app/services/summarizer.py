"""Summarization — plan section 8.

Compresses OLD turns into a `context_summaries` row without deleting anything.
Prefers an LLM summary; falls back to extractive truncation when no LLM works.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .. import models
from ..config import settings


SUMMARIZER_SYSTEM = """You summarize multi-LLM research conversations for future reasoning.
Preserve: important claims, arguments, evidence, agreements, disagreements,
corrections, hypotheses, unresolved questions, numerical results, assumptions.
Avoid generic statements like 'the models discussed X'. Be specific about WHO
claimed WHAT and WHAT remains unresolved. Prioritize facts that affect future reasoning."""

SUMMARIZER_USER_TEMPLATE = """Summarize turns {start_turn} to {end_turn} of this research discussion.
Original question: {question}

Previous summary (may be empty):
{previous_summary}

Turns to summarize:
{turns_text}

Write a dense, self-contained summary."""


async def summarize_old_history(
    db: Session,
    conversation: models.Conversation,
    llm_manager,
    chunk_size: int | None = None,
) -> models.ContextSummary | None:
    from .context_builder import get_latest_summary

    chunk_size = chunk_size or settings.SUMMARY_CHUNK_SIZE
    latest = get_latest_summary(db, conversation.id)
    covered_until = latest.up_to_turn_number if latest else 0

    old_turns = (
        db.query(models.Turn)
        .filter(
            models.Turn.conversation_id == conversation.id,
            models.Turn.turn_number > covered_until,
            models.Turn.status == "ok",
        )
        .order_by(models.Turn.turn_number)
        .all()
    )
    # Keep the sliding window intact: only summarize turns outside active context.
    if len(old_turns) <= settings.MAX_CONTEXT_TURNS:
        return None
    to_cover = old_turns[: max(1, len(old_turns) - settings.MAX_CONTEXT_TURNS)]
    # Bound each summary to a chunk so prompts stay small.
    to_cover = to_cover[:chunk_size]
    if not to_cover:
        return None

    turns_text = "\n\n".join(
        f"[Turn {t.turn_number} | {t.model.name if t.model else '?'}]:\n{(t.response or '')[:4000]}"
        for t in to_cover
    )
    previous = latest.summary if latest else "(none)"

    summary_text: str | None = None
    try:
        # Use the first enabled model as the summarizer engine.
        summarizer_model = to_cover[0].model or db.query(models.LLMModel).first()
        if summarizer_model is not None:
            messages = [
                {"role": "system", "content": SUMMARIZER_SYSTEM},
                {
                    "role": "user",
                    "content": SUMMARIZER_USER_TEMPLATE.format(
                        start_turn=to_cover[0].turn_number,
                        end_turn=to_cover[-1].turn_number,
                        question=conversation.original_prompt[:2000],
                        previous_summary=previous[:4000],
                        turns_text=turns_text[:12000],
                    ),
                },
            ]
            result = await llm_manager.generate(summarizer_model, messages)
            summary_text = result.text.strip()
    except Exception:
        summary_text = None

    if not summary_text:
        # Deterministic fallback: keep first 500 chars of each old turn.
        bits = [
            f"Turn {t.turn_number} ({t.model.name if t.model else '?'}): {(t.response or '')[:500]}"
            for t in to_cover
        ]
        prefix = f"{previous}\n\n" if previous and previous != "(none)" else ""
        summary_text = prefix + "\n".join(bits)

    if latest and latest.up_to_turn_number == to_cover[-1].turn_number:
        latest.summary = summary_text
        db.commit()
        db.refresh(latest)
        return latest

    row = models.ContextSummary(
        conversation_id=conversation.id,
        up_to_turn_id=to_cover[-1].id,
        up_to_turn_number=to_cover[-1].turn_number,
        summary=summary_text,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def needs_summarization(db: Session, conversation: models.Conversation) -> bool:
    from .context_builder import get_latest_summary

    latest = get_latest_summary(db, conversation.id)
    covered = latest.up_to_turn_number if latest else 0
    total = (
        db.query(models.Turn)
        .filter(models.Turn.conversation_id == conversation.id, models.Turn.status == "ok")
        .count()
    )
    uncovered = total - covered
    return uncovered > max(settings.SUMMARIZE_AFTER_TURNS, settings.MAX_CONTEXT_TURNS + 2)
