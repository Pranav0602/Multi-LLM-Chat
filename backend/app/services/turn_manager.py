"""TurnManager — plan sections 5, 11, 12, 16, 17.

Responsibilities:
1. Determine next model via `turn_order` (never hard-coded).
2. Build context (ContextBuilder).
3. Call LLM (LLMManager) with timeout + retries.
4. Store response incl. exact `input_context`.
5. Update conversation state (round/turn counters).
6. Trigger summarization when needed.
7. Advance; on provider failure store an error turn and continue.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from .context_builder import build_context, serialize_context
from .summarizer import needs_summarization, summarize_old_history
from .token_counter import estimate_tokens


def get_ordered_enabled_links(db: Session, group_id: int) -> list[models.GroupModel]:
    return (
        db.query(models.GroupModel)
        .filter(models.GroupModel.group_id == group_id, models.GroupModel.is_enabled.is_(True))
        .order_by(models.GroupModel.turn_order, models.GroupModel.id)
        .all()
    )


def get_next_link(db: Session, conversation: models.Conversation) -> models.GroupModel | None:
    """Round-robin over enabled links ordered by turn_order.

    `current_turn` counts executed turns; next index = current_turn % len(links).
    Round increments every time we wrap around to the first link.
    """
    links = get_ordered_enabled_links(db, conversation.group_id)
    if not links:
        return None
    return links[conversation.current_turn % len(links)]


def compute_round_turn(conversation: models.Conversation, n_models: int) -> tuple[int, int]:
    """Return (round_number, turn_number) for the upcoming turn (1-indexed)."""
    turn_number = conversation.current_turn + 1
    round_number = (conversation.current_turn // max(1, n_models)) + 1
    return round_number, turn_number


async def execute_turn(db: Session, conversation: models.Conversation, llm_manager) -> models.Turn:
    links = get_ordered_enabled_links(db, conversation.group_id)
    if not links:
        raise ValueError("Research group has no enabled models")

    link = get_next_link(db, conversation)
    assert link is not None
    model = db.get(models.LLMModel, link.model_id)
    if model is None:
        raise ValueError(f"Model id={link.model_id} not found")

    round_number, turn_number = compute_round_turn(conversation, len(links))
    messages, debug_payload = build_context(db, conversation, model, link)
    input_context_str = serialize_context(debug_payload)
    input_tokens = estimate_tokens(input_context_str)

    try:
        result = await llm_manager.generate(model, messages)
        turn = models.Turn(
            conversation_id=conversation.id,
            model_id=model.id,
            round_number=round_number,
            turn_number=turn_number,
            input_context=input_context_str,
            response=result.text,
            status="ok",
            input_tokens=result.input_tokens or input_tokens,
            output_tokens=result.output_tokens or estimate_tokens(result.text),
        )
    except Exception as exc:  # noqa: BLE001 — one model must not kill the conversation
        turn = models.Turn(
            conversation_id=conversation.id,
            model_id=model.id,
            round_number=round_number,
            turn_number=turn_number,
            input_context=input_context_str,
            response="",
            status="error",
            error_message=f"{type(exc).__name__}: {exc}",
            input_tokens=input_tokens,
            output_tokens=0,
        )

    db.add(turn)
    conversation.current_turn = turn_number
    conversation.current_round = round_number
    if conversation.current_round > conversation.max_rounds:
        conversation.status = "completed"
    db.commit()
    db.refresh(turn)

    if turn.status == "ok" and needs_summarization(db, conversation):
        try:
            await summarize_old_history(db, conversation, llm_manager)
        except Exception:
            pass  # summarization is best-effort; transcript is already safe

    return turn


async def execute_round(db: Session, conversation: models.Conversation, llm_manager) -> list[models.Turn]:
    """Run one full round (each enabled model speaks once), tolerating failures."""
    n = len(get_ordered_enabled_links(db, conversation.group_id))
    turns: list[models.Turn] = []
    for _ in range(max(1, n)):
        if conversation.status in ("paused", "completed", "stopped"):
            break
        turns.append(await execute_turn(db, conversation, llm_manager))
    return turns


async def run_conversation(
    db: Session,
    conversation: models.Conversation,
    llm_manager,
    max_new_turns: int | None = None,
) -> list[models.Turn]:
    """Drive turns until max_rounds reached or status stops. Respects pause/stop."""
    db.refresh(conversation)
    out: list[models.Turn] = []
    guard = 0
    while conversation.status == "active":
        if max_new_turns is not None and len(out) >= max_new_turns:
            break
        if conversation.current_round > conversation.max_rounds:
            conversation.status = "completed"
            db.commit()
            break
        out.append(await execute_turn(db, conversation, llm_manager))
        db.refresh(conversation)
        guard += 1
        if guard > 1000:  # safety net
            break
    return out
