"""API-level tests: groups, models, conversations, turns, controls."""
def _make_group_with_models(client, n=2):
    g = client.post("/groups", json={"name": "AI Research", "description": "d"}).json()
    mids = []
    for i in range(n):
        m = client.post("/models", json={
            "name": f"GPT-{i}", "provider": "mock", "model_name": f"mock-{i}",
            "system_prompt": "You are a researcher.",
        }).json()
        mids.append(m["id"])
        client.post(f"/groups/{g['id']}/models", json={"model_id": m["id"], "turn_order": i})
    return g, mids


def test_group_model_crud(client):
    g, mids = _make_group_with_models(client, 2)
    assert g["name"] == "AI Research"
    links = client.get(f"/groups/{g['id']}/models").json()
    assert len(links) == 2
    assert [l["turn_order"] for l in links] == [0, 1]


def test_conversation_single_then_multi_turn(client):
    g, _ = _make_group_with_models(client, 3)
    conv = client.post("/conversations", json={
        "group_id": g["id"], "title": "Dark energy?", "original_prompt": "Is dark energy real?",
    }).json()
    t1 = client.post(f"/conversations/{conv['id']}/turn").json()
    assert t1["turn_number"] == 1 and t1["round_number"] == 1
    t2 = client.post(f"/conversations/{conv['id']}/turn").json()
    t3 = client.post(f"/conversations/{conv['id']}/turn").json()
    t4 = client.post(f"/conversations/{conv['id']}/turn").json()
    assert [t["turn_number"] for t in (t1, t2, t3, t4)] == [1, 2, 3, 4]
    assert [t["round_number"] for t in (t1, t2, t3, t4)] == [1, 1, 1, 2]
    # Distinct models in round 1 (round-robin).
    assert len({t1["model_id"], t2["model_id"], t3["model_id"]}) == 3
    turns = client.get(f"/conversations/{conv['id']}/turns").json()
    assert len(turns) == 4
    assert all(t["input_context"] for t in turns)  # debug payload stored


def test_pause_stop_continue(client):
    g, _ = _make_group_with_models(client, 2)
    conv = client.post("/conversations", json={
        "group_id": g["id"], "original_prompt": "Test controls", "max_rounds": 1,
    }).json()
    cid = conv["id"]
    assert client.post(f"/conversations/{cid}/pause").json()["status"] == "paused"
    assert client.post(f"/conversations/{cid}/continue").json()["status"] in ("active", "completed")
    assert client.post(f"/conversations/{cid}/stop").json()["status"] == "stopped"


def test_context_preview_shows_active_context(client):
    g, _ = _make_group_with_models(client, 2)
    conv = client.post("/conversations", json={
        "group_id": g["id"], "original_prompt": "Preview?", "max_rounds": 3,
    }).json()
    preview = client.get(f"/conversations/{conv['id']}/context-preview").json()
    assert preview["next_model"]
    assert "Original research question" in preview["messages"][1]["content"]


def test_reorder_group_models_persists_order(client):
    g, _ = _make_group_with_models(client, 3)
    links = client.get(f"/groups/{g['id']}/models").json()
    assert [l["turn_order"] for l in links] == [0, 1, 2]
    ids = [l["id"] for l in links]
    reversed_ids = list(reversed(ids))
    r = client.put(f"/groups/{g['id']}/models/reorder", json={"ordered_link_ids": reversed_ids})
    assert r.status_code == 200, r.text
    reordered = r.json()
    assert [l["id"] for l in reordered] == reversed_ids
    assert [l["turn_order"] for l in reordered] == [0, 1, 2]
    # Persistence: refetch keeps the new order.
    refetched = client.get(f"/groups/{g['id']}/models").json()
    assert [l["id"] for l in refetched] == reversed_ids
    # Validation: wrong/missing IDs rejected.
    bad = client.put(f"/groups/{g['id']}/models/reorder", json={"ordered_link_ids": ids[:2]})
    assert bad.status_code == 422
    assert "ordered_link_ids" in bad.text
    # Turn execution follows the new order (first link speaks first).
    conv = client.post("/conversations", json={
        "group_id": g["id"], "original_prompt": "Order check?", "max_rounds": 1,
    }).json()
    t1 = client.post(f"/conversations/{conv['id']}/turn").json()
    assert t1["model_id"] == reordered[0]["model_id"]


def test_add_duplicate_model_to_group_gives_clear_error(client):
    g, mids = _make_group_with_models(client, 1)
    dup = client.post(f"/groups/{g['id']}/models", json={"model_id": mids[0], "turn_order": 1})
    assert dup.status_code == 409
    assert "already assigned" in dup.text


def test_test_connection_valid_and_invalid(client):
    ok = client.post("/models/test-connection", json={
        "provider": "mock", "model_name": "mock-test",
    }).json()
    assert ok["ok"] is True
    assert ok["error_code"] is None

    missing_provider = client.post("/models/test-connection", json={
        "provider": "", "model_name": "mock-test",
    }).json()
    assert missing_provider["ok"] is False
    assert missing_provider["error_code"] == "missing_provider"

    missing_name = client.post("/models/test-connection", json={
        "provider": "mock", "model_name": "",
    }).json()
    assert missing_name["ok"] is False
    assert missing_name["error_code"] == "missing_model_name"

    missing_url = client.post("/models/test-connection", json={
        "provider": "groq", "model_name": "llama3-8b-8192",
    }).json()
    assert missing_url["ok"] is False
    assert missing_url["error_code"] == "missing_base_url"
    assert "base URL" in missing_url["message"]


def test_patch_group_model_system_prompt_override(client):
    g, _ = _make_group_with_models(client, 2)
    links = client.get(f"/groups/{g['id']}/models").json()
    link_id = links[0]["id"]
    prompt = "You are the Skeptic. Challenge every assumption with evidence."
    r = client.patch(
        f"/groups/{g['id']}/models/{link_id}", json={"system_prompt_override": prompt}
    )
    assert r.status_code == 200, r.text
    assert r.json()["system_prompt_override"] == prompt
    # Role flows through to the turn badge + preview context.
    conv = client.post("/conversations", json={
        "group_id": g["id"], "original_prompt": "Is dark energy real?",
        "max_rounds": 1, "chat_type": "research",
    }).json()
    preview = client.get(f"/conversations/{conv['id']}/context-preview").json()
    assert preview["role_name"] == "Skeptic"
    turn = client.post(f"/conversations/{conv['id']}/turn").json()
    assert turn["role_name"] == "Skeptic"


def test_create_conversation_with_chat_type(client):
    g, _ = _make_group_with_models(client, 2)
    debate = client.post("/conversations", json={
        "group_id": g["id"], "original_prompt": "Should AI be regulated?",
        "chat_type": "debate",
    }).json()
    assert debate["chat_type"] == "debate"
    assert client.get(f"/conversations/{debate['id']}").json()["chat_type"] == "debate"

    defaulted = client.post("/conversations", json={
        "group_id": g["id"], "original_prompt": "Defaults to research?",
    }).json()
    assert defaulted["chat_type"] == "research"

    bad = client.post("/conversations", json={
        "group_id": g["id"], "original_prompt": "Bad type", "chat_type": "nope",
    })
    assert bad.status_code == 422
