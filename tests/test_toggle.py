"""Per-request live/mock toggle: the request's use_live flag overrides the
server-level USE_MOCK default for that run only. All tests avoid real API calls
(the "live" path is proven with a faked _real_completion).
"""
import json

from fastapi.testclient import TestClient

from backend import config, llm
from backend.main import app
from backend.schemas import ResearchFindings

client = TestClient(app)
IDEA = "AI-powered meal planning app"


def _collect(run_id: str) -> list[tuple[str, dict]]:
    events = []
    with client.stream("GET", f"/api/runs/{run_id}/events") as response:
        current = None
        for line in response.iter_lines():
            if line.startswith("event: "):
                current = line[7:]
            elif line.startswith("data: ") and current:
                events.append((current, json.loads(line[6:])))
                current = None
    return events


def _start_and_collect(payload: dict) -> list[tuple[str, dict]]:
    resp = client.post("/api/validate", json=payload)
    assert resp.status_code == 200
    return _collect(resp.json()["run_id"])


def test_use_mock_resolution_priority():
    """Override wins over the env default; absent override falls back to it."""
    token = config.mock_override.set(None)
    try:
        config_use_mock_default = config.USE_MOCK  # test env: True
        config.mock_override.set(True)
        assert config.use_mock() is True
        config.mock_override.set(False)
        assert config.use_mock() is False
        config.mock_override.set(None)
        assert config.use_mock() is config_use_mock_default
    finally:
        config.mock_override.reset(token)


def test_call_llm_obeys_per_request_override(monkeypatch):
    """On a real-mode server (USE_MOCK=False): override False routes to mocks,
    override True routes to the real provider (faked here), no network."""
    monkeypatch.setattr(config, "USE_MOCK", False)  # server default: real mode
    real_calls = []

    def fake_real(agent, system, user, schema):
        real_calls.append(agent)
        return schema().model_dump()  # degraded-but-valid "live" output

    monkeypatch.setattr(llm, "_real_completion", fake_real)

    token = config.mock_override.set(True)  # True = force mock
    try:
        r = llm.call_llm(agent="researcher", system="", user="IDEA: x", schema=ResearchFindings)
        assert real_calls == []  # mock branch taken despite real-mode default
        assert r.summary.startswith("Mock")
    finally:
        config.mock_override.reset(token)

    token = config.mock_override.set(False)  # False = force live
    try:
        llm.call_llm(agent="researcher", system="", user="IDEA: x", schema=ResearchFindings)
        assert real_calls == ["researcher"]  # live branch taken
    finally:
        config.mock_override.reset(token)


def test_api_toggle_off_forces_mock_on_real_default_server(monkeypatch):
    """Core requirement: use_live=false runs mock even when the server defaults
    to real mode (USE_MOCK=False), with no API calls."""
    monkeypatch.setattr(config, "USE_MOCK", False)
    monkeypatch.setattr(llm, "_real_completion", lambda a, s, u, schema: (_ for _ in ()).throw(AssertionError("real path must not be used")))
    events = _start_and_collect({"idea": IDEA, "use_live": False})
    report = events[-1][1]
    assert events[-1][0] == "report"
    assert report["mock_mode"] is True
    assert any("MOCK MODE" in w for w in report["warnings"])
    assert report["evaluation"]["score"] == 62  # canned mock data


def test_api_toggle_on_uses_live_pipeline(monkeypatch):
    """use_live=true on a real-default server takes the real path (faked) and the
    report is NOT flagged as mock."""
    monkeypatch.setattr(config, "USE_MOCK", False)
    agents_called = []

    def fake_real(agent, system, user, schema):
        agents_called.append(agent)
        return schema().model_dump()

    monkeypatch.setattr(llm, "_real_completion", fake_real)
    events = _start_and_collect({"idea": IDEA, "use_live": True})
    report = events[-1][1]
    assert events[-1][0] == "report"
    assert report["mock_mode"] is False
    assert not any("MOCK MODE" in w for w in report["warnings"])
    assert agents_called == ["researcher", "analyst", "critic", "evaluator"]


def test_api_missing_field_uses_server_default(monkeypatch):
    """No use_live field -> server-level USE_MOCK decides (here: real, faked)."""
    monkeypatch.setattr(config, "USE_MOCK", False)
    agents_called = []

    def fake_real(agent, system, user, schema):
        agents_called.append(agent)
        return schema().model_dump()

    monkeypatch.setattr(llm, "_real_completion", fake_real)
    events = _start_and_collect({"idea": IDEA})
    report = events[-1][1]
    assert agents_called == ["researcher", "analyst", "critic", "evaluator"]
    assert report["mock_mode"] is False
