"""Phase 6 acceptance: full 4-node mock pipeline produces a complete schema-valid
report; the weighted score and verdict bands are enforced in code; all upstream
outputs survive the evaluator.
"""
from backend.agents import analyze_market_node, critique_node, evaluate_node, research_node
from backend.prompts import EVALUATOR_PROMPT
from backend.schemas import (
    Critique,
    FinalEvaluation,
    MarketAnalysis,
    Report,
    ResearchFindings,
)

IDEA = "AI-powered meal planning app"


def _run_pipeline():
    research_out = research_node({"idea": IDEA})
    market_out = analyze_market_node({"idea": IDEA, **research_out})
    critique_out = critique_node({"idea": IDEA, **research_out, **market_out})
    evaluation_out = evaluate_node({"idea": IDEA, **research_out, **market_out, **critique_out})
    return research_out, market_out, critique_out, evaluation_out


def test_full_pipeline_produces_complete_report():
    research_out, market_out, critique_out, evaluation_out = _run_pipeline()
    merged = {"idea": IDEA, "mock_mode": True, **research_out, **market_out, **critique_out, **evaluation_out}
    report = Report.model_validate(merged)
    assert report.evaluation.score == 62  # 70/45/75/60/55 under 25/20/20/20/15 weights
    assert report.evaluation.verdict == "Needs Rework"
    assert report.evaluation.executive_summary
    assert report.evaluation.strengths and report.evaluation.next_steps
    assert report.research.competitors and report.market.market_size and report.critique.risks


def test_node_overrides_llm_score_and_verdict(monkeypatch):
    """Even if the LLM returns a wrong total/verdict, the node enforces the rubric."""

    def fake_llm(agent, system, user, schema):
        return schema.model_validate({
            "score": 99,
            "subscores": {"market_opportunity": 0, "differentiation": 0, "feasibility": 0, "business_viability": 0, "timing": 0},
            "verdict": "Promising",
        })

    monkeypatch.setattr("backend.agents.call_llm", fake_llm)
    result = evaluate_node({"idea": IDEA})
    assert result["evaluation"]["score"] == 0
    assert result["evaluation"]["verdict"] == "High Risk"


def test_upstream_outputs_survive_evaluation_node():
    research_out, market_out, critique_out, evaluation_out = _run_pipeline()
    assert list(evaluation_out.keys()) == ["evaluation"]  # writes only its own key
    merged = {"idea": IDEA, **research_out, **market_out, **critique_out, **evaluation_out}
    assert merged["research"] == research_out["research"]
    assert merged["market"] == market_out["market"]
    assert merged["critique"] == critique_out["critique"]
    assert Critique.model_validate(merged["critique"])
    assert ResearchFindings.model_validate(merged["research"])
    assert MarketAnalysis.model_validate(merged["market"])
    assert FinalEvaluation.model_validate(merged["evaluation"])


def test_rubric_documented_in_prompt_and_weights_match():
    from backend.prompts import RUBRIC_WEIGHTS

    assert RUBRIC_WEIGHTS == {
        "market_opportunity": 0.25,
        "differentiation": 0.20,
        "feasibility": 0.20,
        "business_viability": 0.20,
        "timing": 0.15,
    }
    assert sum(RUBRIC_WEIGHTS.values()) == 1.0
    for needle in ("0.25", "0.15", "75", "50", "Promising", "Needs Rework", "High Risk"):
        assert needle in EVALUATOR_PROMPT
