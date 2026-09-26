"""Phase 4 acceptance: analyst chained after researcher (state passing), schema-valid
output, research preserved intact, mock + degraded modes, supplemental-search logic.
"""
import logging

from backend.agents import analyze_market_node, research_node
from backend.schemas import MarketAnalysis, ResearchFindings

IDEA = "AI-powered meal planning app"


def test_analyst_chained_after_research():
    research_out = research_node({"idea": IDEA})
    result = analyze_market_node({"idea": IDEA, **research_out})
    analysis = MarketAnalysis.model_validate(result["market"])
    assert analysis.verified is True
    assert analysis.market_size and analysis.trends and analysis.target_audience
    assert "data_flags" not in result and "errors" not in result


def test_analyst_preserves_research_in_state():
    research_out = research_node({"idea": IDEA})
    result = analyze_market_node({"idea": IDEA, **research_out})
    assert "research" not in result  # node only writes its own key
    merged = {"idea": IDEA, **research_out, **result}  # LangGraph-style merge
    assert merged["research"] == research_out["research"]  # append/merge: research intact


def test_analyst_degraded_without_research(monkeypatch, caplog):
    calls = []

    def fake_search(query):
        calls.append(query)
        return []

    monkeypatch.setattr("backend.agents.web_search", fake_search)
    with caplog.at_level(logging.WARNING):
        result = analyze_market_node({"idea": IDEA})
    analysis = MarketAnalysis.model_validate(result["market"])
    assert analysis.verified is False
    assert "market_unverified" in result["data_flags"]
    assert result["errors"][0]["agent"] == "analyst"
    assert len(calls) == 2  # ran its own targeted searches when research was missing
    assert "thin research" in caplog.text


def test_analyst_skips_supplemental_search_when_research_is_solid(monkeypatch):
    research_out = research_node({"idea": IDEA})  # real mock search => verified, sources

    calls = []

    def fake_search(query):
        calls.append(query)
        return []

    monkeypatch.setattr("backend.agents.web_search", fake_search)
    analyze_market_node({"idea": IDEA, **research_out})
    assert calls == []  # verified, source-rich research => no extra searches
