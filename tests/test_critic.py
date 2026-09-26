"""Phase 5 acceptance: 3-node chained run, schema-valid critique with severities,
upstream findings actually fed to the critic, state holding all outputs at once.
"""
from backend.agents import analyze_market_node, critique_node, research_node
from backend.schemas import Critique, FinalEvaluation, MarketAnalysis, ResearchFindings

IDEA = "AI-powered meal planning app"
VALID_SEVERITIES = {"high", "medium", "low"}


def _run_pipeline():
    research_out = research_node({"idea": IDEA})
    market_out = analyze_market_node({"idea": IDEA, **research_out})
    critique_out = critique_node({"idea": IDEA, **research_out, **market_out})
    return research_out, market_out, critique_out


def test_critic_chained_after_research_and_market():
    _, _, critique_out = _run_pipeline()
    assert list(critique_out.keys()) == ["critique"]  # writes only its own key
    critique = Critique.model_validate(critique_out["critique"])
    assert len(critique.risks) >= 3
    assert all(r.severity in VALID_SEVERITIES for r in critique.risks)
    assert any(r.severity == "high" for r in critique.risks)
    assert critique.weak_assumptions and critique.failure_modes
    assert critique.hardest_question


def test_critic_prompt_includes_upstream_findings(monkeypatch):
    research_out = research_node({"idea": IDEA})
    market_out = analyze_market_node({"idea": IDEA, **research_out})

    captured = {}

    def fake_llm(agent, system, user, schema):
        captured["user"] = user
        return schema.model_validate({"risks": [{"risk": "x", "severity": "low", "category": "market"}]})

    monkeypatch.setattr("backend.agents.call_llm", fake_llm)
    critique_node({"idea": IDEA, **research_out, **market_out})
    # spot-check grounding: the critic's prompt carries the upstream facts it judges
    assert "ValidateMyIdea" in captured["user"]  # from mock research
    assert "Mock market analysis" in captured["user"]  # from mock market analysis
    assert IDEA in captured["user"]


def test_pipeline_state_holds_all_outputs_simultaneously():
    research_out, market_out, critique_out = _run_pipeline()
    merged = {"idea": IDEA, **research_out, **market_out, **critique_out}
    assert merged["research"] == research_out["research"]  # nothing overwritten downstream
    assert merged["market"] == market_out["market"]
    assert Critique.model_validate(merged["critique"])
    assert ResearchFindings.model_validate(merged["research"])
    assert MarketAnalysis.model_validate(merged["market"])
    assert FinalEvaluation.model_validate({"idea": IDEA})  # evaluator not run yet — degraded default fine
