"""Phase 3 acceptance: research_node mock happy path, search-failure fallback,
key ownership, and logged provider failures.
"""
import logging

from backend.agents import research_node
from backend.schemas import ResearchFindings


def test_research_mock_happy_path():
    result = research_node({"idea": "AI-powered meal planning app"})
    findings = ResearchFindings.model_validate(result["research"])
    assert findings.verified is True
    assert len(findings.competitors) >= 2
    assert findings.summary  # non-empty
    assert "data_flags" not in result and "errors" not in result


def test_research_search_failure_falls_back_to_llm_knowledge(monkeypatch, caplog):
    monkeypatch.setattr("backend.agents.web_search", lambda query: [])
    with caplog.at_level(logging.WARNING):
        result = research_node({"idea": "AI-powered meal planning app"})
    findings = ResearchFindings.model_validate(result["research"])
    assert findings.verified is False
    assert "research_unverified" in result["data_flags"]
    assert result["errors"][0]["type"] == "search_unavailable"
    assert "falling back" in caplog.text


def test_research_node_writes_only_its_own_keys(monkeypatch):
    monkeypatch.setattr("backend.agents.web_search", lambda query: [])
    result = research_node({"idea": "anything", "market": {"preexisting": True}})
    assert not ({"market", "critique", "evaluation", "progress"} & result.keys())


def test_web_search_all_providers_fail_is_logged(monkeypatch, caplog):
    from backend import config
    from backend.tools import web_search

    monkeypatch.setattr(config, "API_KEYS", {"TAVILY_API_KEY": "", "SERPAPI_API_KEY": ""})
    token = config.mock_override.set(False)  # force the real-provider path
    try:
        with caplog.at_level(logging.WARNING):
            assert web_search("competitors for X") == []
    finally:
        config.mock_override.reset(token)
    assert "search provider failed" in caplog.text
