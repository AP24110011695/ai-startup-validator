"""LangGraph wiring: START → validate_idea → (conditional) → research →
analyze_market → critique → evaluate → END.

The four agent nodes are wrapped with agents.with_retry (progress events +
degrade-on-failure), so one failing agent never aborts the run. Compiled once at
module level; run_validation(idea) is the one-call entry point (Phase 8's API
layer builds on it).
"""
import logging
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from backend import agents
from backend.agents import now_iso, with_retry
from backend.schemas import Critique, FinalEvaluation, MarketAnalysis, ResearchFindings
from backend.state import ValidatorState

logger = logging.getLogger(__name__)

MIN_IDEA_CHARS = 10


def validate_idea_node(state: dict) -> dict:
    """Owner of state["input_rejected"]: rejects unusable ideas before any agent
    runs. The rejection detail lives in state.errors for the API layer (Phase 8)
    to surface as the "need more detail" response.
    """
    idea = (state.get("idea") or "").strip()
    rejected = len(idea) < MIN_IDEA_CHARS or not any(c.isalpha() for c in idea)
    logger.info("validate_idea_node: rejected=%s", bool(rejected))
    if not rejected:
        return {"input_rejected": False}
    return {
        "input_rejected": True,
        "errors": [{"agent": "validator", "type": "invalid_input", "message": "Idea is too vague or too short — please describe it in a sentence or more."}],
        "progress": [{"agent": "validator", "status": "failed", "ts": now_iso()}],
    }


def _route_after_validation(state: dict) -> str:
    return END if state.get("input_rejected") else "research"


def build_graph():
    graph = StateGraph(ValidatorState)
    graph.add_node("validate_idea", validate_idea_node)
    graph.add_node("research", with_retry(agents.research_node, "researcher", "research", ResearchFindings))
    graph.add_node("analyze_market", with_retry(agents.analyze_market_node, "analyst", "market", MarketAnalysis))
    graph.add_node("critique", with_retry(agents.critique_node, "critic", "critique", Critique))
    graph.add_node("evaluate", with_retry(agents.evaluate_node, "evaluator", "evaluation", FinalEvaluation))
    graph.add_edge(START, "validate_idea")
    graph.add_conditional_edges("validate_idea", _route_after_validation, {"research": "research", END: END})
    graph.add_edge("research", "analyze_market")
    graph.add_edge("analyze_market", "critique")
    graph.add_edge("critique", "evaluate")
    graph.add_edge("evaluate", END)
    return graph.compile()


GRAPH = build_graph()


def run_validation(idea: str, run_id: str | None = None) -> dict:
    """Run the full pipeline for one idea and return the final shared state."""
    return GRAPH.invoke({
        "idea": idea,
        "run_id": run_id or uuid4().hex[:12],
        "created_at": now_iso(),
    })
