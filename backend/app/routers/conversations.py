"""Conversation endpoints — plan section 19 + 14/15/16.

Covers: create/get, start/pause/stop/continue, single turn, summarize,
full transcript, streaming (SSE), retry of failed turns.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sse_starlette.sse import EventSourceResponse

from .. import models, schemas
from ..database import get_db
from ..llm.manager import llm_manager
from ..services import turn_manager
from ..services.context_builder import build_context, get_latest_summary
from ..services.summarizer import summarize_old_history
from ..services.turn_manager import get_ordered_enabled_links

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _get_or_404(db: Session, conv_id: int) -> models.Conversation:
    conv = db.get(models.Conversation, conv_id)
    if not conv:
        raise HTTPException(404, "Conversation not found")
    return conv


def _extract_turn_role(t: models.Turn) -> str | None:
    """Role badge for a turn: prefer stored debug payload, else model prompt."""
    try:
        payload = json.loads(t.input_context or "{}")
        if isinstance(payload, dict) and payload.get("role_name"):
            return payload["role_name"]
    except Exception:
        pass
    try:
        from ..services.context_builder import extract_role_name

        prompt = None
        if isinstance(payload, dict) and payload.get("system_prompt"):
            prompt = payload["system_prompt"]
        elif t.model and t.model.system_prompt:
            prompt = t.model.system_prompt
        return extract_role_name(prompt)
    except Exception:
        return None


def _turn_out(t: models.Turn) -> schemas.TurnOut:
    return schemas.TurnOut(
        id=t.id,
        conversation_id=t.conversation_id,
        model_id=t.model_id,
        round_number=t.round_number,
        turn_number=t.turn_number,
        input_context=t.input_context,
        response=t.response,
        status=t.status,
        error_message=t.error_message,
        input_tokens=t.input_tokens,
        output_tokens=t.output_tokens,
        created_at=t.created_at,
        model_name=t.model.name if t.model else None,
        provider=t.model.provider if t.model else None,
        role_name=_extract_turn_role(t),
    )


@router.post("", response_model=schemas.ConversationOut)
def create_conversation(payload: schemas.ConversationCreate, db: Session = Depends(get_db)):
    if not db.get(models.Group, payload.group_id):
        raise HTTPException(404, "Group not found")
    allowed = {"research", "debate", "architecture", "brainstorm", "custom"}
    chat_type = (payload.chat_type or "research").lower()
    if chat_type not in allowed:
        raise HTTPException(422, f"Invalid chat_type '{payload.chat_type}'. Allowed: {sorted(allowed)}")
    conv = models.Conversation(
        group_id=payload.group_id,
        title=payload.title or payload.original_prompt[:120],
        original_prompt=payload.original_prompt,
        max_rounds=payload.max_rounds,
        status="active",
        chat_type=chat_type,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


@router.get("/{conv_id}", response_model=schemas.ConversationOut)
def get_conversation(conv_id: int, db: Session = Depends(get_db)):
    return _get_or_404(db, conv_id)


@router.get("/{conv_id}/turns", response_model=list[schemas.TurnOut])
def list_turns(conv_id: int, db: Session = Depends(get_db)):
    _get_or_404(db, conv_id)
    rows = (
        db.query(models.Turn)
        .options(joinedload(models.Turn.model))
        .filter(models.Turn.conversation_id == conv_id)
        .order_by(models.Turn.turn_number)
        .all()
    )
    return [_turn_out(t) for t in rows]


@router.get("/{conv_id}/summaries", response_model=list[schemas.SummaryOut])
def list_summaries(conv_id: int, db: Session = Depends(get_db)):
    _get_or_404(db, conv_id)
    return (
        db.query(models.ContextSummary)
        .filter(models.ContextSummary.conversation_id == conv_id)
        .order_by(models.ContextSummary.id)
        .all()
    )


@router.post("/{conv_id}/turn", response_model=schemas.TurnOut)
async def run_single_turn(conv_id: int, db: Session = Depends(get_db)):
    conv = _get_or_404(db, conv_id)
    if conv.status in ("completed", "stopped"):
        raise HTTPException(409, f"Conversation is {conv.status}; use /continue to resume")
    conv.status = "active"
    db.commit()
    turn = await turn_manager.execute_turn(db, conv, llm_manager)
    turn = db.query(models.Turn).options(joinedload(models.Turn.model)).filter_by(id=turn.id).one()
    return _turn_out(turn)


@router.post("/{conv_id}/start")
async def start_conversation(conv_id: int, body: schemas.ConversationControl | None = None, db: Session = Depends(get_db)):
    conv = _get_or_404(db, conv_id)
    if body and body.max_rounds:
        conv.max_rounds = body.max_rounds
    conv.status = "active"
    db.commit()
    turns = await turn_manager.run_conversation(db, conv, llm_manager)
    return {"status": conv.status, "new_turns": len(turns)}


@router.post("/{conv_id}/continue")
async def continue_conversation(conv_id: int, body: schemas.ConversationControl | None = None, db: Session = Depends(get_db)):
    conv = _get_or_404(db, conv_id)
    if conv.status == "completed":
        raise HTTPException(409, "Conversation already completed")
    if body and body.max_rounds:
        conv.max_rounds = body.max_rounds
    conv.status = "active"
    db.commit()
    turns = await turn_manager.run_conversation(db, conv, llm_manager)
    return {"status": conv.status, "new_turns": len(turns)}


@router.post("/{conv_id}/pause")
def pause_conversation(conv_id: int, db: Session = Depends(get_db)):
    conv = _get_or_404(db, conv_id)
    conv.status = "paused"
    db.commit()
    return {"status": conv.status}


@router.post("/{conv_id}/stop")
def stop_conversation(conv_id: int, db: Session = Depends(get_db)):
    conv = _get_or_404(db, conv_id)
    conv.status = "stopped"
    db.commit()
    return {"status": conv.status}


@router.post("/{conv_id}/summarize", response_model=schemas.SummaryOut | None)
async def summarize_now(conv_id: int, db: Session = Depends(get_db)):
    conv = _get_or_404(db, conv_id)
    row = await summarize_old_history(db, conv, llm_manager)
    if row is None:
        raise HTTPException(409, "Nothing to summarize yet (transcript fits in context window)")
    return row


@router.post("/{conv_id}/retry/{turn_number}", response_model=schemas.TurnOut)
async def retry_turn(conv_id: int, turn_number: int, db: Session = Depends(get_db)):
    """Retry a failed turn: rebuild context and regenerate with the same model."""
    conv = _get_or_404(db, conv_id)
    failed = (
        db.query(models.Turn)
        .filter(models.Turn.conversation_id == conv_id, models.Turn.turn_number == turn_number)
        .first()
    )
    if not failed:
        raise HTTPException(404, "Turn not found")
    if failed.status != "error":
        raise HTTPException(409, "Only error turns can be retried")
    model = db.get(models.LLMModel, failed.model_id) if failed.model_id else None
    if not model:
        raise HTTPException(404, "Original model no longer exists")
    link = (
        db.query(models.GroupModel)
        .filter(models.GroupModel.group_id == conv.group_id, models.GroupModel.model_id == model.id)
        .first()
    )
    messages, debug = build_context(db, conv, model, link)
    from ..services.context_builder import serialize_context
    from ..services.token_counter import estimate_tokens

    try:
        result = await llm_manager.generate(model, messages)
        failed.response = result.text
        failed.status = "ok"
        failed.error_message = ""
        failed.input_context = serialize_context(debug)
        failed.input_tokens = result.input_tokens or estimate_tokens(failed.input_context)
        failed.output_tokens = result.output_tokens or estimate_tokens(result.text)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        failed.error_message = f"{type(exc).__name__}: {exc}"
        db.commit()
        raise HTTPException(502, f"Retry failed: {exc}")
    db.refresh(failed)
    return _turn_out(failed)


@router.get("/{conv_id}/stream")
async def stream_next_turn(conv_id: int, db: Session = Depends(get_db)):
    """SSE stream of the next turn (plan section 15). Non-streaming execution first,
    streaming layered on top: we generate then re-emit as token-ish chunks."""
    conv = _get_or_404(db, conv_id)
    links = get_ordered_enabled_links(db, conv.group_id)
    if not links:
        raise HTTPException(409, "Group has no enabled models")
    link = turn_manager.get_next_link(db, conv)
    model = db.get(models.LLMModel, link.model_id)

    async def generator():
        yield {"event": "start", "data": json.dumps({"model": model.name})}
        messages, debug = build_context(db, conv, model, link)
        try:
            full = ""
            async for chunk in llm_manager.astream(model, messages):
                full += chunk
                yield {"event": "token", "data": json.dumps({"text": chunk})}
            # Persist after streaming completes.
            from ..services.context_builder import serialize_context
            from ..services.turn_manager import compute_round_turn

            round_number, turn_number = compute_round_turn(conv, len(links))
            turn = models.Turn(
                conversation_id=conv.id,
                model_id=model.id,
                round_number=round_number,
                turn_number=turn_number,
                input_context=serialize_context(debug),
                response=full,
                status="ok",
            )
            db.add(turn)
            conv.current_turn = turn_number
            conv.current_round = round_number
            db.commit()
            yield {"event": "done", "data": json.dumps({"turn_number": turn_number})}
        except Exception as exc:  # noqa: BLE001
            yield {"event": "error", "data": json.dumps({"message": str(exc)})}

    return EventSourceResponse(generator())


@router.get("/{conv_id}/context-preview")
def context_preview(conv_id: int, db: Session = Depends(get_db)):
    """Inspect exactly what the next model would receive (debugging aid)."""
    conv = _get_or_404(db, conv_id)
    link = turn_manager.get_next_link(db, conv)
    if not link:
        raise HTTPException(409, "Group has no enabled models")
    model = db.get(models.LLMModel, link.model_id)
    _, debug = build_context(db, conv, model, link)
    latest = get_latest_summary(db, conv.id)
    return {
        "next_model": model.name,
        "provider": model.provider,
        "summary_used": bool(latest),
        "recent_turns": debug["recent_turn_numbers"],
        "messages": debug["messages"],
        "role_name": debug.get("role_name"),
        "chat_type": debug.get("chat_type"),
        "system_prompt": debug.get("system_prompt"),
    }
