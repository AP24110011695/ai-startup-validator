"""Phase 8 acceptance: SSE stream end-to-end in mock (agent_status → report), quota
simulation surfaces a structured quota_exceeded error, /api/key hot-swap works
without a restart and persists to .env.
"""
import json

from fastapi.testclient import TestClient

from backend import config
from backend.main import app

client = TestClient(app)
IDEA = "AI-powered meal planning app"


def _start(idea: str) -> str:
    resp = client.post("/api/validate", json={"idea": idea})
    assert resp.status_code == 200
    return resp.json()["run_id"]


def _collect(run_id: str) -> list[tuple[str, dict]]:
    events = []
    with client.stream("GET", f"/api/runs/{run_id}/events") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        current = None
        for line in response.iter_lines():
            if line.startswith("event: "):
                current = line[len("event: "):]
            elif line.startswith("data: ") and current:
                events.append((current, json.loads(line[len("data: "):])))
                current = None
    return events


def test_health():
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["mock_mode"] is True


def test_full_flow_streams_status_then_report():
    run_id = _start(IDEA)
    events = _collect(run_id)
    types = [t for t, _ in events]
    assert types == ["agent_status"] * 8 + ["report"]
    statuses = [(e["agent"], e["status"]) for t, e in events if t == "agent_status"]
    for agent in ("researcher", "analyst", "critic", "evaluator"):
        assert (agent, "started") in statuses
        assert (agent, "finished") in statuses
    report = events[-1][1]
    assert report["idea"] == IDEA
    assert report["evaluation"]["score"] == 62
    assert report["evaluation"]["verdict"] == "Needs Rework"
    assert report["mock_mode"] is True
    assert any("MOCK MODE" in w for w in report["warnings"])
    fetched = client.get(f"/api/runs/{run_id}").json()
    assert fetched["status"] == "done"
    assert fetched["report"]["evaluation"]["score"] == 62


def test_unknown_run_404():
    assert client.get("/api/runs/nope").status_code == 404
    assert client.get("/api/runs/nope/events").status_code == 404


def test_missing_idea_422():
    assert client.post("/api/validate", json={"idea": "   "}).status_code == 422


def test_invalid_idea_streams_error():
    run_id = _start("hi")
    events = _collect(run_id)
    assert events[-1][0] == "run_error"
    assert events[-1][1]["code"] == "invalid_input"
    assert events[-1][1]["message"]
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "error"


def test_quota_simulation_streams_quota_exceeded(monkeypatch):
    # The simulation models the real provider: it aborts LIVE runs (use_live=true)
    # and leaves mock runs untouched (regression covered in test_toggle.py).
    monkeypatch.setattr(config, "FAKE_QUOTA_ERROR", True)
    resp = client.post("/api/validate", json={"idea": IDEA, "use_live": True})
    assert resp.status_code == 200
    events = _collect(resp.json()["run_id"])
    assert events[-1][0] == "run_error"
    assert events[-1][1]["code"] == "quota_exceeded"
    assert client.get(f"/api/runs/{resp.json()['run_id']}").json()["status"] == "error"


def test_set_key_swaps_in_memory_without_restart(monkeypatch):
    monkeypatch.setattr(config, "_persist_to_env", lambda name, value: None)
    monkeypatch.setitem(config.API_KEYS, "GEMINI_API_KEY", "")
    resp = client.post("/api/key", json={"api_key": "test-key-123"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert config.API_KEYS["GEMINI_API_KEY"] == "test-key-123"


def test_key_persisted_to_env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setitem(config.API_KEYS, "GEMINI_API_KEY", "")
    config.set_api_key("GEMINI_API_KEY", "persisted-key")
    content = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "GEMINI_API_KEY=persisted-key" in content
    config.set_api_key("GEMINI_API_KEY", "updated-key")  # replaces the existing line
    content = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "GEMINI_API_KEY=updated-key" in content
    assert content.count("GEMINI_API_KEY=") == 1
