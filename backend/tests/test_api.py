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
