"""Agent node functions. Each returns a partial state update and writes ONLY its
own state key (see backend/state.py ownership table).

LLM exceptions propagate: the graph-level retry wrapper (Phase 7) handles
retry-then-degrade uniformly for every node.
"""
import logging

from backend.config import USE_MOCK
from backend.llm import call_llm
from backend.prompts import ANALYST_PROMPT, RESEARCHER_PROMPT
from backend.schemas import MarketAnalysis, ResearchFindings
from backend.tools import web_search

logger = logging.getLogger(__name__)


def research_node(state: dict) -> dict:
    """Researcher agent. Owner of state["research"]: finds competitors and similar
    products via web search. If all search fails, the LLM answers from its own
    knowledge and the output is flagged unverified.
    """
    idea = state["idea"]
    logger.info("research_node: started (mock_mode=%s)", USE_MOCK)

    results: list[dict] = []
    for query in _research_queries(idea):
        results.extend(web_search(query))
    verified = bool(results)

    if verified:
        search_block = "\n".join(f"- {r['title']} ({r['url']}): {r['snippet']}" for r in results)
    else:
        logger.warning("research_node: no search results; falling back to LLM knowledge (unverified)")
        search_block = "No live search results available — use your own knowledge and set verified=false."

    user = f"IDEA: {idea}\n\nSEARCH RESULTS:\n{search_block}"
    findings = call_llm(agent="researcher", system=RESEARCHER_PROMPT, user=user, schema=ResearchFindings)
    data = findings.model_dump()
    data["verified"] = verified  # deterministic: we know whether search actually succeeded

    if verified:
        return {"research": data}
    return {
        "research": data,
        "data_flags": ["research_unverified"],
        "errors": [{"agent": "researcher", "type": "search_unavailable", "message": "all web search providers failed; findings are LLM-knowledge only"}],
    }


def _research_queries(idea: str) -> list[str]:
    """2-4 targeted search queries derived from the idea (heuristic — no extra LLM call)."""
    base = " ".join(idea.split()).rstrip(".")
    return [f"{base} competitors", f"{base} alternatives", f"{base} market analysis"]


def analyze_market_node(state: dict) -> dict:
    """Market Analyst agent. Owner of state["market"]: market size, trends, target
    audience. Reads the researcher's findings without modifying them; when the
    research is thin (unverified or source-less) it runs 1-2 targeted searches of
    its own. Unverified output is flagged like the researcher's.
    """
    idea = state["idea"]
    research = state.get("research") or {}
    research_verified = bool(research.get("verified"))
    logger.info("analyze_market_node: started (mock_mode=%s)", USE_MOCK)

    findings_block = _format_research(research)
    extra: list[dict] = []
    if not research_verified or not research.get("sources"):
        logger.warning("analyze_market_node: thin research; running targeted market searches")
        for query in _market_queries(idea):
            extra.extend(web_search(query))
    if extra:
        block = "\n".join(f"- {r['title']} ({r['url']}): {r['snippet']}" for r in extra)
        findings_block += f"\n\nSUPPLEMENTARY SEARCH RESULTS:\n{block}"

    user = f"IDEA: {idea}\n\nRESEARCHER FINDINGS:\n{findings_block}"
    analysis = call_llm(agent="analyst", system=ANALYST_PROMPT, user=user, schema=MarketAnalysis)
    data = analysis.model_dump()
    data["verified"] = research_verified or bool(extra)  # deterministic, like research_node

    if data["verified"]:
        return {"market": data}
    return {
        "market": data,
        "data_flags": ["market_unverified"],
        "errors": [{"agent": "analyst", "type": "data_unverified", "message": "market analysis lacks live data: research unverified and supplementary searches returned nothing"}],
    }


def _market_queries(idea: str) -> list[str]:
    base = " ".join(idea.split()).rstrip(".")
    return [f"{base} market size TAM", f"{base} industry trends"]


def _format_research(research: dict) -> str:
    if not research:
        return "No research findings available — rely on your own knowledge and any supplementary search results."
    lines = [f"Summary: {research.get('summary', '')}", "Competitors:"]
    lines += [f"- {c.get('name')}: {c.get('description', '')}" for c in research.get("competitors", [])]
    lines += [f"Sources: {', '.join(research.get('sources', []))}", f"Verified: {research.get('verified', False)}"]
    return "\n".join(lines)
