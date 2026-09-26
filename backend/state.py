"""LangGraph shared state. Nodes return partial updates; the graph merges them.

Append-only lists (progress, errors, data_flags) use Annotated[..., operator.add]
reducers so updates merge by appending — no node can wipe another's entries.

Ownership (each key written exactly once by its owning node; nothing else touches it):
    validate_idea_node  -> input_rejected
    research_node       -> research
    analyze_market_node -> market
    critique_node       -> critique
    evaluate_node       -> evaluation
    any node            -> progress / errors / data_flags (append-only)
"""
import operator
from typing import Annotated, TypedDict


class ValidatorState(TypedDict, total=False):
    # inputs
    idea: str
    run_id: str
    created_at: str

    # append-only feeds (merged by concatenation)
    progress: Annotated[list[dict], operator.add]   # [{agent, status: started|finished, ts}]
    errors: Annotated[list[dict], operator.add]     # [{agent, type, message}]
    data_flags: Annotated[list[str], operator.add]  # e.g. "mock_mode", "research_unverified"

    # agent outputs (dicts matching backend.schemas models)
    research: dict    # ResearchFindings
    market: dict      # MarketAnalysis
    critique: dict    # Critique
    evaluation: dict  # FinalEvaluation

    # set by validate_idea; True routes the graph to END before any agent runs
    input_rejected: bool
