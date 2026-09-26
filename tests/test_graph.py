"""Phase 7 acceptance: compiled graph runs end-to-end in mock; progress events for
all 4 agents; invalid input exits early; forced LLM failure proves retry-then-degrade;
transient failure recovers on the adjusted-prompt retry.
"""
from backend import llm
from backend.graph import run_validation

IDEA = "AI-powered meal planning app"
AGENTS = ("researcher", "analyst", "critic", "evaluator")


def test_graph_end_to_end_mock():
    state = run_validation(IDEA)
    assert state["run_id"] and state["created_at"]
    assert state["evaluation"]["score"] == 62
    statuses = {(e["agent"], e["status"]) for e in state["progress"]}
    for agent in AGENTS:
        assert (agent, "started") in statuses
        assert (agent, "finished") in statuses
    assert state["research"]["verified"] is True
    assert state["errors"] == [] and state["data_flags"] == []


def test_invalid_input_ends_early():
    for bad in ("hi", "1234567890"):
        state = run_validation(bad)
        assert state["input_rejected"] is True
        assert "research" not in state and "evaluation" not in state
        assert state["errors"][0]["type"] == "invalid_input"
        assert state["errors"][0]["message"]  # the "need more detail" payload


def test_forced_llm_failure_retries_then_degrades(monkeypatch):
    calls = {"n": 0}

    def failing(agent, user):
        calls["n"] += 1
        raise RuntimeError("boom")

    monkeypatch.setattr(llm, "_mock_response", failing)
    state = run_validation(IDEA)
    assert calls["n"] == 12  # 4 agents x (1 attempt + 2 retries)
    for key in ("research", "market", "critique", "evaluation"):
        assert state.get(key)  # degraded-but-valid outputs present; pipeline completed
    assert state["research"]["summary"].startswith("researcher failed")
    assert len([e for e in state["errors"] if e["type"] == "llm_error"]) == 4
    statuses = {(e["agent"], e["status"]) for e in state["progress"]}
    for agent in AGENTS:
        assert (agent, "failed") in statuses


def test_transient_llm_failure_recovers_on_retry(monkeypatch):
    original = llm._mock_response
    seen_prompts = []
    attempts = {"researcher": 0}

    def flaky(agent, user):
        if agent == "researcher":
            attempts["researcher"] += 1
            seen_prompts.append(user)
            if attempts["researcher"] <= 2:
                raise RuntimeError("transient")
        return original(agent, user)

    monkeypatch.setattr(llm, "_mock_response", flaky)
    state = run_validation(IDEA)
    assert attempts["researcher"] == 3  # two failures, success on the 3rd attempt
    assert "Respond ONLY with valid JSON" in seen_prompts[1]  # retries use adjusted prompt
    assert state["research"]["competitors"]  # real mock output, not the degraded empty one
    assert not [e for e in state["errors"] if e["agent"] == "researcher"]  # recovered: no error entry
