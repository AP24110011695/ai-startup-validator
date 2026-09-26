"""Phase 10 edge cases: vague input still completes, very long input, total search
failure at graph level, LLM timeouts, malformed LLM output, concurrent runs.
All mock-mode via conftest.
"""
import json

from fastapi.testclient import TestClient

from backend import llm
from backend.graph import run_validation
from backend.main import app

IDEA = "AI-powered meal planning app"


def test_vague_input_still_completes_gracefully():
    """Semantic vagueness ('make money') is not rejected by the heuristic validator —
    the pipeline handles it: agents produce generic-but-valid output, no crash."""
    state = run_validation("make money")
    assert state["evaluation"]["score"] >= 0
    assert state["research"]["competitors"] == [] or state["research"]["summary"]


def test_very_long_input_completes():
    state = run_validation(IDEA + " " + "with lots of details " * 250)  # ~5.5k chars
    assert state["evaluation"]["score"] == 62


def test_total_search_failure_flags_unverified(monkeypatch):
    from backend import agents

    monkeypatch.setattr(agents, "web_search", lambda query: [])
    state = run_validation(IDEA)
    assert state["research"]["verified"] is False
    assert "research_unverified" in state["data_flags"]
    assert any(e["type"] == "search_unavailable" for e in state["errors"])
    # the pipeline still delivered a complete report — degraded, not dead
    assert state["evaluation"]["score"] == 62


def test_llm_timeout_retries_then_degrades(monkeypatch):
    def timing_out(agent, user):
        raise TimeoutError("request timed out after 60s")

    monkeypatch.setattr(llm, "_mock_response", timing_out)
    state = run_validation(IDEA)
    assert len([e for e in state["errors"] if e["type"] == "llm_error"]) == 4
    assert state["research"]["summary"].startswith("researcher failed")
    assert state["evaluation"]["verdict"] == "High Risk"  # degraded defaults


def test_malformed_llm_output_retries_then_degrades(monkeypatch):
    calls = {"n": 0}

    def garbage(agent, user):
        calls["n"] += 1
        return "this is not a JSON object at all"

    monkeypatch.setattr(llm, "_mock_response", garbage)
    state = run_validation(IDEA)
    assert calls["n"] == 12  # every attempt made, every attempt failed validation
    assert state["research"]["competitors"] == []


def test_concurrent_runs_are_independent():
    client = TestClient(app)
    ids = []
    for idea in (IDEA, "A marketplace for vintage synthesizers"):
        resp = client.post("/api/validate", json={"idea": idea})
        assert resp.status_code == 200
        ids.append(resp.json()["run_id"])
    assert len(set(ids)) == 2
    reports = []
    for run_id in ids:
        events = []
        with client.stream("GET", f"/api/runs/{run_id}/events") as response:
            current = None
            for line in response.iter_lines():
                if line.startswith("event: "):
                    current = line[7:]
                elif line.startswith("data: ") and current:
                    events.append((current, json.loads(line[6:])))
                    current = None
        assert events[-1][0] == "report"
        reports.append(events[-1][1])
    assert reports[0]["idea"] != reports[1]["idea"]
    assert all(r["evaluation"]["score"] == 62 for r in reports)
