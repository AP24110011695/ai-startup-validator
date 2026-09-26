"""Web search tool: Tavily -> SerpAPI REST -> mock (USE_MOCK). Every failure is logged.

Returns [{title, url, snippet}]; an empty list means "no live results — use LLM
knowledge", which callers must treat as unverified data.
"""
import logging

import httpx

from backend.config import API_KEYS, USE_MOCK

logger = logging.getLogger(__name__)
SEARCH_TIMEOUT = 15  # seconds, explicit per the error-handling rules


def web_search(query: str) -> list[dict]:
    """Try providers in order (mock -> Tavily -> SerpAPI); [] on total failure."""
    if USE_MOCK:
        return mock_search(query)
    for provider in (_tavily_search, _serpapi_search):
        try:
            results = provider(query)
            if results:
                return results
        except Exception:
            logger.exception("search provider failed: %s", provider.__name__)
    logger.warning("web_search: all providers failed or empty for %r", query)
    return []


def _tavily_search(query: str) -> list[dict]:
    key = API_KEYS["TAVILY_API_KEY"]
    if not key:
        raise RuntimeError("no Tavily API key configured")
    resp = httpx.post(
        "https://api.tavily.com/search",
        json={"api_key": key, "query": query, "max_results": 5},
        timeout=SEARCH_TIMEOUT,
    )
    resp.raise_for_status()
    return [{"title": r["title"], "url": r["url"], "snippet": r.get("content", "")} for r in resp.json().get("results", [])]


def _serpapi_search(query: str) -> list[dict]:
    key = API_KEYS["SERPAPI_API_KEY"]
    if not key:
        raise RuntimeError("no SerpAPI key configured")
    resp = httpx.get(
        "https://serpapi.com/search",
        params={"q": query, "api_key": key},
        timeout=SEARCH_TIMEOUT,
    )
    resp.raise_for_status()
    return [
        {"title": r["title"], "url": r["link"], "snippet": r.get("snippet", "")}
        for r in resp.json().get("organic_results", [])[:5]
    ]


def mock_search(query: str) -> list[dict]:
    """MOCK_MODE: canned results, independent of the query."""
    logger.info("MOCK_MODE: mock search for %r", query)
    return [
        {"title": "The 5 best startup idea validation tools in 2026", "url": "https://example.com/validation-tools", "snippet": "Comparison of AI tools that score and stress-test startup ideas before you build."},
        {"title": "How VCs really evaluate early-stage ideas", "url": "https://example.com/vc-evaluation", "snippet": "Investors weigh market size, moat, timing and founder fit when scoring raw ideas."},
        {"title": "Market research for first-time founders: a practical guide", "url": "https://example.com/market-research-guide", "snippet": "Cheap, fast ways to size a market and find competitors without paid databases."},
    ]
