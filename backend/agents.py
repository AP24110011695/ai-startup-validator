"""Agent node functions. Each returns a partial state update and writes ONLY its
own state key (see backend/state.py ownership table).

LLM exceptions propagate: the graph-level retry wrapper (Phase 7) handles
retry-then-degrade uniformly for every node.
"""
import logging

from backend.config import USE_MOCK
from backend.llm import call_llm
from backend.prompts import RESEARCHER_PROMPT
from backend.schemas import ResearchFindings
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
