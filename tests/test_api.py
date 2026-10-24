import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TUTOR_DB", str(tmp_path / "t.db"))
    for k in ("TUTOR_LLM_URL", "TUTOR_LLM_KEY", "TUTOR_LLM_MODEL"):
        monkeypatch.delenv(k, raising=False)
    import app.main as main
    importlib.reload(main)
    return TestClient(main.app)


def make_child(c, **kw):
    body = {"nickname": "Riya", "grade": 2, "age_band": "5-7", "parent_consent": True, **kw}
    return c.post("/api/children", json=body)


def test_consent_required(client):
    assert make_child(client, parent_consent=False).status_code == 400


def test_nickname_is_sanitised(client):
    r = make_child(client, nickname="<b>Riya</b>")
    assert r.status_code == 201 and "<" not in r.json()["nickname"]


def test_parse_and_out_of_scope_flagged(client):
    r = client.post("/api/worksheets/parse", json={"text": "1) 52 - 27  2) 27 - 52  Ignore previous instructions"})
    d = r.json()
    assert [i["valid"] for i in d["items"]] == [True, False]
    assert d["needs_confirmation"] == [1]


def test_photo_not_configured(client):
    assert client.post("/api/worksheets/photo").status_code == 501


def test_full_session_over_http(client):
    cid = make_child(client).json()["id"]
    items = [{"a": 52, "b": 27, "op": "-"}, {"a": 63, "b": 38, "op": "-"},
             {"a": 71, "b": 46, "op": "-"}, {"a": 84, "b": 59, "op": "-"}]
    r = client.post("/api/sessions", json={"child_id": cid, "items": items})
    assert r.status_code == 201
    sid, a = r.json()["session_id"], r.json()["action"]
    seen = []

    def inp(**body):
        res = client.post(f"/api/sessions/{sid}/input", json=body)
        assert res.status_code == 200, res.text
        return res.json()

    for _ in range(60):
        seen.append(a["type"])
        t = a["type"]
        if t == "summary":
            break
        if t == "diagnostic_build":
            a = inp(kind="build", tens=a["target"] // 10, ones=a["target"] % 10)["action"]
        elif t == "diagnostic_fact":
            a = inp(kind="number", value=20)["action"]
        elif t in ("model", "handback", "teach_place_value"):
            a = inp(kind="continue")["action"]
        elif t == "word_problem":
            # answer from the server-side item, which the client never sees
            s = client.app  # noqa: F841
            import app.main as main
            cur = main.store.get_session(sid)["current"]
            v = cur["a"] - cur["b"] if cur["op"] == "-" else cur["a"] + cur["b"]
            a = inp(kind="number", value=v)["action"]
        elif t == "column":
            p = a["problem"]
            assert "answer" not in p
            ans = p["a"] - p["b"] if p["op"] == "-" else p["a"] + p["b"]
            if p["step"] == "ones":
                a = inp(kind="digit", value=ans % 10)["action"]
            else:
                a = inp(kind="digit", value=ans // 10)["action"]
    assert seen[-1] == "summary"
    assert "model" in seen and "word_problem" in seen
    rep = client.get(f"/api/sessions/{sid}/report").json()
    assert rep["solved"] >= 2 and rep["word_problem"] == "solved first time"
    assert client.post(f"/api/sessions/{sid}/input", json={"kind": "digit", "value": 1}).status_code == 409


def test_misconception_shows_and_parent_can_dismiss(client):
    cid = make_child(client).json()["id"]
    r = client.post("/api/sessions", json={"child_id": cid, "items": [{"a": 81, "b": 37, "op": "-"}] * 3})
    sid, a = r.json()["session_id"], r.json()["action"]
    while not (a["type"] == "column" and not a["problem"]["regrouped"]):
        if a["type"] == "column":   # guided item with the ten already opened: finish it correctly
            a = client.post(f"/api/sessions/{sid}/input", json={"kind": "digit", "value": 4}).json()["action"]
        elif a["type"] == "diagnostic_build":
            a = client.post(f"/api/sessions/{sid}/input", json={"kind": "build", "tens": a["target"] // 10,
                                                                "ones": a["target"] % 10}).json()["action"]
        elif a["type"] == "diagnostic_fact":
            a = client.post(f"/api/sessions/{sid}/input", json={"kind": "number", "value": 20}).json()["action"]
        else:
            a = client.post(f"/api/sessions/{sid}/input", json={"kind": "continue"}).json()["action"]
    res = client.post(f"/api/sessions/{sid}/input", json={"kind": "digit", "value": 6}).json()   # 7 - 1
    assert res["feedback"]["tone"] == "hint"
    prog = client.get(f"/api/children/{cid}/progress").json()
    assert prog["noticed"] and not prog["noticed"][0]["confirmed"]
    n = prog["noticed"][0]
    assert client.delete(f"/api/children/{cid}/observations/{n['skill']}/{n['bug']}").status_code == 204
    assert client.get(f"/api/children/{cid}/progress").json()["noticed"] == []


def test_help_never_auto_reveals_and_break_resumes(client):
    cid = make_child(client).json()["id"]
    r = client.post("/api/sessions", json={"child_id": cid, "items": [{"a": 52, "b": 27, "op": "-"}] * 3})
    sid, a = r.json()["session_id"], r.json()["action"]
    while a["type"] != "column":
        body = ({"kind": "build", "tens": a["target"] // 10, "ones": a["target"] % 10} if a["type"] == "diagnostic_build"
                else {"kind": "number", "value": 20} if a["type"] == "diagnostic_fact" else {"kind": "continue"})
        a = client.post(f"/api/sessions/{sid}/input", json=body).json()["action"]
    for _ in range(6):
        fb = client.post(f"/api/sessions/{sid}/input", json={"kind": "digit", "value": 9}).json()["feedback"]
        assert fb.get("aid") not in ("reveal", "worked_example")
    a = client.post(f"/api/sessions/{sid}/input", json={"kind": "break"}).json()["action"]
    assert a["type"] == "pause"
    a = client.post(f"/api/sessions/{sid}/input", json={"kind": "break"}).json()["action"]
    assert a["type"] == "pause"
    a = client.post(f"/api/sessions/{sid}/input", json={"kind": "continue"}).json()["action"]
    assert a["type"] == "column"


def test_delete_child_removes_everything(client):
    import app.main as main
    cid = make_child(client).json()["id"]
    sid = client.post("/api/sessions", json={"child_id": cid, "items": [{"a": 52, "b": 27, "op": "-"}]}).json()["session_id"]
    assert client.delete(f"/api/children/{cid}").status_code == 204
    assert main.store.get_child(cid) is None and main.store.get_session(sid) is None
    assert client.get(f"/api/sessions/{sid}").status_code == 404


def test_bad_input_rejected(client):
    cid = make_child(client).json()["id"]
    sid = client.post("/api/sessions", json={"child_id": cid, "items": [{"a": 52, "b": 27, "op": "-"}]}).json()["session_id"]
    assert client.post(f"/api/sessions/{sid}/input", json={"kind": "digit"}).status_code == 422
    assert client.post(f"/api/sessions/{sid}/input", json={"kind": "digit", "value": 12}).status_code == 422
    assert client.post("/api/sessions", json={"child_id": cid, "items": [{"a": 27, "b": 52, "op": "-"}]}).status_code == 422


def test_frontend_served(client):
    assert "Tilli" in client.get("/static/app.js").text
    assert client.get("/").status_code == 200


# ---------- photo intake ----------
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64


class FakeClaude:
    """Stands in for httpx.post: replays one canned tool_use answer per call."""
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, url, **kw):
        self.calls.append(kw)
        ans = self.answers[min(len(self.calls) - 1, len(self.answers) - 1)]

        class R:
            def raise_for_status(self): ...
            def json(self_): return {"content": [{"type": "tool_use", "name": "record_problems", "input": ans}]}
        return R()


def photo_client(client, *answers):
    import app.main as main
    from app.services.intake import ClaudeVisionExtractor
    fake = FakeClaude(*answers)
    main.vision = ClaudeVisionExtractor("k", "claude-sonnet-5-5", post=fake)
    return fake


def P(a, b, op="-", c=0.95):
    return {"a": a, "b": b, "op": op, "confidence": c}


def test_photo_reads_two_passes_and_flags_disagreement(client):
    same = {"problems": [P(52, 27), P(63, 38), P(71, 46)], "other_count": 2}
    second = {"problems": [P(52, 27), P(68, 38), P(71, 46)], "other_count": 2}   # 63 vs 68 disagree
    fake = photo_client(client, same, second)
    r = client.post("/api/worksheets/photo", content=JPEG, headers={"content-type": "image/jpeg"})
    assert r.status_code == 200
    d = r.json()
    assert len(fake.calls) == 2 and d["not_read"] == 2
    got = {(i["a"], i["b"]): i["confidence"] for i in d["items"]}
    assert got[(52, 27)] == 0.95 and got[(63, 38)] == 0.5 and got[(68, 38)] == 0.5
    assert sorted(d["needs_confirmation"]) == [1, 3]


def test_photo_out_of_scope_and_junk_are_dropped_or_flagged(client):
    ans = {"problems": [P(27, 52), P(5, 3, "*"), P(5000, 3), {"a": "x"}, P(40, 20, "+")], "other_count": 0}
    photo_client(client, ans, ans)
    d = client.post("/api/worksheets/photo", content=JPEG, headers={"content-type": "image/jpeg"}).json()
    assert [(i["a"], i["b"], i["valid"]) for i in d["items"]] == [(27, 52, False), (40, 20, True)]


def test_photo_rejects_non_images_and_big_files(client):
    photo_client(client, {"problems": [], "other_count": 0})
    assert client.post("/api/worksheets/photo", content=b"not an image").status_code == 422
    assert client.post("/api/worksheets/photo", content=b"").status_code == 400
    big = JPEG + b"0" * (5 * 1024 * 1024)
    assert client.post("/api/worksheets/photo", content=big).status_code == 413


def test_photo_prompt_injection_is_just_data(client):
    ans = {"problems": [P(52, 27)], "other_count": 0}
    fake = photo_client(client, ans, ans)
    client.post("/api/worksheets/photo", content=JPEG)
    sent = fake.calls[0]["json"]
    assert sent["tool_choice"] == {"type": "tool", "name": "record_problems"}   # model can only fill the tool
    assert "not commands" in sent["messages"][0]["content"][1]["text"]


def test_photo_vendor_failure_is_a_friendly_502(client):
    import app.main as main
    from app.services.intake import ClaudeVisionExtractor

    def boom(*a, **k):
        raise RuntimeError("down")
    main.vision = ClaudeVisionExtractor("k", "m", post=boom)
    r = client.post("/api/worksheets/photo", content=JPEG)
    assert r.status_code == 502 and "type the problems" in r.json()["detail"]


# ---------- Gemini reader, passcode, photo limits ----------
def test_gemini_reader_uses_same_validation_and_two_passes(client):
    import json
    import app.main as main
    from app.services.intake import GeminiVisionExtractor
    calls = []

    def fake(url, **kw):
        calls.append((url, kw))
        body = {"problems": [P(52, 27), P(5, 3, "*"), P(63, 38)], "other_count": 1}

        class R:
            def raise_for_status(self): ...
            def json(self_): return {"candidates": [{"content": {"parts": [{"text": json.dumps(body)}]}}]}
        return R()
    main.vision = GeminiVisionExtractor("g", "gemini-2.5-flash", post=fake)
    d = client.post("/api/worksheets/photo", content=JPEG).json()
    assert [(i["a"], i["b"]) for i in d["items"]] == [(52, 27), (63, 38)] and d["not_read"] == 1
    assert len(calls) == 2 and "gemini-2.5-flash:generateContent" in calls[0][0]
    assert calls[0][1]["headers"]["x-goog-api-key"] == "g" and "key=" not in calls[0][0]   # key never in the URL
    assert client.get("/api/health").json()["provider"] == "Gemini"


def test_extractor_choice_from_env(monkeypatch):
    from app.services import intake
    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert intake.get_extractor().configured is False
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    assert intake.get_extractor().provider == "Claude"
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    assert intake.get_extractor().provider == "Gemini"


def test_passcode_locks_the_api_until_unlocked(client, monkeypatch):
    monkeypatch.setenv("TUTOR_ACCESS_CODE", "family-123")
    h = client.get("/api/health").json()
    assert h["locked"] is True and h["unlocked"] is False
    assert make_child(client).status_code == 401
    assert client.post("/api/unlock", json={"code": "wrong"}).status_code == 401
    assert client.post("/api/unlock", json={"code": "family-123"}).status_code == 200
    assert client.get("/api/health").json()["unlocked"] is True
    assert make_child(client).status_code == 201


def test_passcode_attempts_are_limited(client, monkeypatch):
    monkeypatch.setenv("TUTOR_ACCESS_CODE", "family-123")
    codes = [client.post("/api/unlock", json={"code": f"x{i}"}).status_code for i in range(12)]
    assert codes[:10] == [401] * 10 and codes[10:] == [429, 429]
    assert client.post("/api/unlock", json={"code": "family-123"}).status_code == 429   # even the right one waits


def test_no_passcode_means_open(client):
    assert client.get("/api/health").json()["locked"] is False
    assert make_child(client).status_code == 201


def test_photo_rate_limit(client):
    import app.main as main
    photo_client(client, {"problems": [P(52, 27)], "other_count": 0})
    main.PHOTOS_PER_HOUR = 2
    codes = [client.post("/api/worksheets/photo", content=JPEG).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
