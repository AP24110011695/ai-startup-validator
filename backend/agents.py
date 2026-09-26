"""Agent node functions. Each returns a partial state update and writes ONLY its
own state key (see backend/state.py ownership table).

with_retry is the graph-level safety net: progress events in/out, and a degraded-
but-valid output + errors entry if a node still raises after call_llm's retries.
"""
import contextvars
import logging
from datetime import datetime, timezone

from pydantic import BaseModel

from backend.config import USE_MOCK
from backend.llm import QuotaError, call_llm
from backend.prompts import ANALYST_PROMPT, CRITIC_PROMPT, EVALUATOR_PROMPT, RESEARCHER_PROMPT, RUBRIC_WEIGHTS, VERDICT_BANDS
from backend.schemas import Critique, FinalEvaluation, MarketAnalysis, ResearchFindings
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


def critique_node(state: dict) -> dict:
    """Critic agent. Owner of state["critique"]: devil's-advocate risks, weak
    assumptions, failure modes. Consumes idea + research + market without
    modifying them; no web search — this is a judgment pass over upstream data.
    """
    idea = state["idea"]
    logger.info("critique_node: started (mock_mode=%s)", USE_MOCK)
    user = (
        f"IDEA: {idea}\n\n"
        f"RESEARCHER FINDINGS:\n{_format_research(state.get('research') or {})}\n\n"
        f"MARKET ANALYSIS:\n{_format_market(state.get('market') or {})}"
    )
    critique = call_llm(agent="critic", system=CRITIC_PROMPT, user=user, schema=Critique)
    return {"critique": critique.model_dump()}


def _format_market(market: dict) -> str:
    if not market:
        return "No market analysis available."
    lines = [f"Summary: {market.get('summary', '')}"]
    lines += [f"- Size: {e.get('text', '')} (basis: {e.get('basis', '')}, confidence: {e.get('confidence', '')})" for e in market.get("market_size", [])]
    lines += [f"- Trend: {t}" for t in market.get("trends", [])]
    lines += [f"- Audience: {a}" for a in market.get("target_audience", [])]
    lines.append(f"Verified: {market.get('verified', False)}")
    return "\n".join(lines)


def evaluate_node(state: dict) -> dict:
    """Evaluator/Compiler agent. Owner of state["evaluation"]: synthesizes research +
    market + critique into a 0-100 feasibility score, verdict, and actionable summary.
    The LLM supplies the dimension subscores; the weighted total and verdict band are
    recomputed here from the rubric (backend/prompts.RUBRIC_WEIGHTS / VERDICT_BANDS)
    so the headline number can't be skewed by model arithmetic.
    """
    idea = state["idea"]
    logger.info("evaluate_node: started (mock_mode=%s)", USE_MOCK)
    user = (
        f"IDEA: {idea}\n\n"
        f"RESEARCHER FINDINGS:\n{_format_research(state.get('research') or {})}\n\n"
        f"MARKET ANALYSIS:\n{_format_market(state.get('market') or {})}\n\n"
        f"CRITIQUE:\n{_format_critique(state.get('critique') or {})}"
    )
    evaluation = call_llm(agent="evaluator", system=EVALUATOR_PROMPT, user=user, schema=FinalEvaluation)
    data = evaluation.model_dump()
    data["score"] = _weighted_score(data["subscores"])
    data["verdict"] = _verdict(data["score"])
    return {"evaluation": data}


def _weighted_score(subscores: dict) -> int:
    total = sum(subscores.get(k, 0) * w for k, w in RUBRIC_WEIGHTS.items())
    return max(0, min(100, round(total)))


def _verdict(score: int) -> str:
    for threshold, verdict in VERDICT_BANDS:
        if score >= threshold:
            return verdict
    return "High Risk"


def _format_critique(critique: dict) -> str:
    if not critique:
        return "No critique available."
    lines = ["Risks:"]
    lines += [f"- [{r.get('severity', '')}|{r.get('category', '')}] {r.get('risk', '')}" for r in critique.get("risks", [])]
    lines += [f"Weak assumption: {a}" for a in critique.get("weak_assumptions", [])]
    lines += [f"Failure mode: {f}" for f in critique.get("failure_modes", [])]
    lines.append(f"Hardest question: {critique.get('hardest_question', '')}")
    return "\n".join(lines)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# Optional real-time progress hook, set per run by the API layer (contextvar so
# concurrent runs never cross wires). state.progress stays the durable record
# whether or not a sink is attached.
progress_sink: contextvars.ContextVar = contextvars.ContextVar("progress_sink", default=None)


def _emit(event: dict) -> None:
    sink = progress_sink.get()
    if sink:
        sink(event)


def with_retry(node, agent: str, output_key: str, schema: type[BaseModel]):
    """Graph-level safety net around one agent node.

    Appends progress events (started/finished/failed — feeds Phase 8 SSE) and, if
    the node still raises after call_llm's retries, substitutes a degraded
    schema-valid output plus an errors entry, so the graph never aborts because
    one agent failed.
    """

    def wrapped(state: dict) -> dict:
        updates: dict = {"progress": [{"agent": agent, "status": "started", "ts": now_iso()}]}
        _emit(updates["progress"][0])
        try:
            node_updates = node(state)
        except QuotaError:
            raise  # fatal for the run: the API layer turns it into the paste-a-new-key flow
        except Exception as exc:
            logger.exception("%s_node failed after all LLM retries; degrading", agent)
            degraded = schema().model_dump()
            if "summary" in degraded:
                degraded["summary"] = f"{agent} failed; no output available."
            updates[output_key] = degraded
            updates["errors"] = [{"agent": agent, "type": "llm_error", "message": str(exc)}]
            updates["progress"].append({"agent": agent, "status": "failed", "ts": now_iso()})
            _emit(updates["progress"][-1])
            return updates
        updates.update(node_updates)
        updates["progress"].append({"agent": agent, "status": "finished", "ts": now_iso()})
        _emit(updates["progress"][-1])
        return updates

    return wrapped
