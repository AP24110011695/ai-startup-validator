"""Phase 2 acceptance: schemas and prompts import, and every schema round-trips."""
from backend import prompts
from backend.schemas import (
    Competitor,
    Critique,
    FinalEvaluation,
    MarketAnalysis,
    Report,
    ResearchFindings,
)

FULL_REPORT = {
    "idea": "AI-powered meal planning app",
    "generated_at": "2026-09-27T00:00:00",
    "mock_mode": True,
    "research": {
        "competitors": [
            {"name": "MealPrepPro", "url": "https://example.com", "description": "Paid meal planner", "similarity": "direct"}
        ],
        "summary": "Crowded market.",
        "sources": ["https://example.com"],
        "verified": True,
    },
    "market": {
        "market_size": [{"text": "$5B TAM", "basis": "industry reports", "confidence": "medium"}],
        "trends": ["rising demand for personalized nutrition"],
        "target_audience": ["busy professionals 25-40"],
        "summary": "Growing market.",
        "verified": True,
    },
    "critique": {
        "risks": [{"risk": "Crowded space", "severity": "high", "category": "competitive"}],
        "weak_assumptions": ["users will pay for convenience"],
        "failure_modes": ["retention collapse after week 2"],
        "hardest_question": "Why you instead of the incumbents?",
    },
    "evaluation": {
        "score": 62,
        "subscores": {
            "market_opportunity": 70,
            "differentiation": 45,
            "feasibility": 75,
            "business_viability": 60,
            "timing": 55,
        },
        "verdict": "Needs Rework",
        "executive_summary": "Real market, weak moat.",
        "strengths": ["large market"],
        "recommendation": "Niche down.",
        "next_steps": ["Interview 20 users"],
    },
    "warnings": [],
}


def test_report_round_trip():
    report = Report.model_validate(FULL_REPORT)
    assert report.evaluation.score == 62
    assert report.evaluation.verdict == "Needs Rework"
    assert report.research.competitors[0].name == "MealPrepPro"


def test_each_schema_round_trips_its_own_payload():
    assert Competitor.model_validate(FULL_REPORT["research"]["competitors"][0])
    assert ResearchFindings.model_validate(FULL_REPORT["research"])
    assert MarketAnalysis.model_validate(FULL_REPORT["market"])
    assert Critique.model_validate(FULL_REPORT["critique"])
    assert FinalEvaluation.model_validate(FULL_REPORT["evaluation"])


def test_degraded_mode_defaults_are_valid():
    empty = Report.model_validate({"idea": "x"})
    assert empty.evaluation.score == 0
    assert empty.evaluation.verdict == "High Risk"
    assert empty.research.verified is False
    assert empty.warnings == []


def test_all_agent_prompts_defined():
    for name in ("RESEARCHER_PROMPT", "ANALYST_PROMPT", "CRITIC_PROMPT", "EVALUATOR_PROMPT"):
        prompt = getattr(prompts, name)
        assert len(prompt) > 200
        assert "ONLY valid JSON" in prompt
