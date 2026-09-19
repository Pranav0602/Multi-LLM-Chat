"""Tests for ContextBuilder sliding-window rule + TurnManager round-robin."""
import pytest

from app import models
from app.services import context_builder, turn_manager
from app.llm.mock_provider import MockProvider
from app.llm.manager import LLMManager


def _seed(db_session, n_models=3, n_turns=0):
    g = models.Group(name="Physics", description="test")
    db_session.add(g)
    db_session.flush()
    mods = []
    for i in range(n_models):
        m = models.LLMModel(
            name=f"M{i}", provider="mock", model_name=f"mock-{i}",
            system_prompt=f"You are researcher {i}",
        )
        db_session.add(m)
        db_session.flush()
        mods.append(m)
        db_session.add(models.GroupModel(group_id=g.id, model_id=m.id, turn_order=i, is_enabled=True))
    conv = models.Conversation(group_id=g.id, title="t", original_prompt="Is dark energy real?")
    db_session.add(conv)
    db_session.flush()
    for t in range(1, n_turns + 1):
        m = mods[(t - 1) % n_models]
        rnd = (t - 1) // n_models + 1
        db_session.add(models.Turn(
            conversation_id=conv.id, model_id=m.id, round_number=rnd, turn_number=t,
            input_context="{}", response=f"Response {t} from {m.name}",
        ))
    db_session.commit()
    return g, mods, conv


def test_sliding_window_keeps_only_recent_complete_turns(db_session):
    _, _, conv = _seed(db_session, n_models=2, n_turns=12)
    model = db_session.query(models.LLMModel).first()
    messages, debug = context_builder.build_context(db_session, conv, model, max_turns=8)
    assert debug["recent_turn_numbers"] == [5, 6, 7, 8, 9, 10, 11, 12]
    # Full transcript retained in DB.
    assert db_session.query(models.Turn).filter_by(conversation_id=conv.id).count() == 12
    # Active context contains original question + 8 complete responses.
    user_text = messages[1]["content"]
    assert "Is dark energy real?" in user_text
    assert "Response 12" in user_text
    assert "Response 4" not in user_text  # outside window


def test_next_model_uses_turn_order_not_hardcoded(db_session):
    g, mods, conv = _seed(db_session, n_models=3)
    # Reorder: reverse turn_order.
    links = db_session.query(models.GroupModel).order_by(models.GroupModel.id).all()
    for link, order in zip(links, [2, 1, 0]):
        link.turn_order = order
    db_session.commit()
    conv.current_turn = 0
    first = turn_manager.get_next_link(db_session, conv)
    assert first.model_id == mods[2].id  # turn_order 0
    conv.current_turn = 1
    second = turn_manager.get_next_link(db_session, conv)
    assert second.model_id == mods[1].id


@pytest.mark.asyncio
async def test_execute_turn_round_robin_and_counters(db_session):
    _, mods, conv = _seed(db_session, n_models=2)
    mgr = LLMManager()
    t1 = await turn_manager.execute_turn(db_session, conv, mgr)
    t2 = await turn_manager.execute_turn(db_session, conv, mgr)
    t3 = await turn_manager.execute_turn(db_session, conv, mgr)
    assert [t.model_id for t in (t1, t2, t3)] == [mods[0].id, mods[1].id, mods[0].id]
    assert [(t.round_number, t.turn_number) for t in (t1, t2, t3)] == [(1, 1), (1, 2), (2, 3)]
    assert t1.input_context and "original_prompt" in t1.input_context
    assert conv.current_turn == 3 and conv.current_round == 2


@pytest.mark.asyncio
async def test_error_turn_does_not_kill_conversation(db_session):
    from app import models as m

    _, mods, conv = _seed(db_session, n_models=2)

    class Flaky:
        async def generate(self, model, messages):
            if model.name == mods[0].name:
                raise TimeoutError("API timeout")
            res = await MockProvider().generate(messages, {"name": model.name})
            return res

        async def astream(self, model, messages):
            yield (await self.generate(model, messages)).text

    class FlakyManager(LLMManager):
        async def generate(self, model, messages):
            return await Flaky().generate(model, messages)

    flaky = FlakyManager()
    t1 = await turn_manager.execute_turn(db_session, conv, flaky)
    assert t1.status == "error" and "Timeout" in t1.error_message
    t2 = await turn_manager.execute_turn(db_session, conv, flaky)
    assert t2.status == "ok"  # conversation continued to next model


@pytest.mark.asyncio
async def test_summarization_preserves_transcript(db_session, monkeypatch):
    from app.services import summarizer
    from app import config as config_module

    monkeypatch.setattr(config_module.settings, "MAX_CONTEXT_TURNS", 4)
    monkeypatch.setattr(config_module.settings, "SUMMARIZE_AFTER_TURNS", 5)
    monkeypatch.setattr(config_module.settings, "SUMMARY_CHUNK_SIZE", 10)
    _, _, conv = _seed(db_session, n_models=2, n_turns=12)
    mgr = LLMManager()
    assert summarizer.needs_summarization(db_session, conv) is True
    row = await summarizer.summarize_old_history(db_session, conv, mgr)
    assert row is not None and row.up_to_turn_number > 0
    # Nothing deleted.
    assert db_session.query(models.Turn).filter_by(conversation_id=conv.id).count() == 12
