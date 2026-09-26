"""LLM access. USE_MOCK=true routes to canned per-agent responses; the real Gemini
call (with retry + quota/error mapping) lands in Phase 8 behind the same signature.
"""
import logging

from pydantic import BaseModel

from backend.config import USE_MOCK

logger = logging.getLogger(__name__)


def call_llm(agent: str, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
    """One agent turn: returns schema-validated output. Raises on failure —
    the graph-level retry wrapper (Phase 7) decides whether to retry or degrade.
    """
    if USE_MOCK:
        return schema.model_validate(_mock_response(agent, user))
    raise NotImplementedError("real LLM calls are wired in Phase 8")


def _mock_response(agent: str, user: str) -> dict:
    """MOCK_MODE: canned, realistic JSON per agent; builders are added per phase."""
    logger.info("MOCK_MODE: canned LLM response for agent=%s", agent)
    builders = {"researcher": _mock_researcher, "analyst": _mock_analyst, "critic": _mock_critic}
    if agent not in builders:
        raise KeyError(f"no mock builder registered for agent={agent!r}")
    return builders[agent](_extract_idea(user))


def _extract_idea(user: str) -> str:
    return user[5:].split("\n", 1)[0].strip() if user.startswith("IDEA:") else "the submitted idea"


def _mock_researcher(idea: str) -> dict:
    return {
        "competitors": [
            {"name": "ValidateMyIdea", "url": "https://example.com/validatemyidea", "description": "AI tool that scores startup ideas against live market signals.", "similarity": "direct"},
            {"name": "FounderLens", "url": "https://example.com/founderlens", "description": "Investor-style diligence reports generated for early-stage founders.", "similarity": "direct"},
            {"name": "IdeaCheck.io", "url": "https://example.com/ideacheck", "description": "Community feedback plus basic market stats for raw ideas.", "similarity": "adjacent"},
        ],
        "summary": f"Mock research for: {idea}. The AI idea-validation space is active with a few direct tools; no dominant player is visible in this MOCK_MODE sample.",
        "sources": ["https://example.com/validation-tools", "https://example.com/vc-evaluation"],
        "verified": True,
    }


def _mock_analyst(idea: str) -> dict:
    return {
        "market_size": [
            {"text": "$4.2B global market for startup-idea validation and market-research tooling", "basis": "MOCK_MODE sample figure", "confidence": "low"},
            {"text": "$850M serviceable segment among first-time founders in English-speaking markets", "basis": "MOCK_MODE sample figure", "confidence": "low"},
        ],
        "trends": [
            "Founders increasingly use AI tooling instead of paid consultants for early diligence",
            "Investors now expect data-backed validation before pre-seed pitches",
        ],
        "target_audience": [
            "First-time founders validating an idea before building",
            "Indie hackers and solo entrepreneurs choosing between ideas",
            "Startup accelerators screening applicant ideas",
        ],
        "summary": f"Mock market analysis for: {idea}. Validation-tooling demand is growing; figures in this MOCK_MODE sample are illustrative.",
        "verified": True,
    }


def _mock_critic(idea: str) -> dict:
    return {
        "risks": [
            {"risk": "Established AI assistants can bolt this on as a feature overnight", "severity": "high", "category": "competitive"},
            {"risk": "One-time validation purchase — little reason to return, so lifetime value is tiny", "severity": "high", "category": "business model"},
            {"risk": "AI-generated market data can be confidently wrong, and wrong validation is worse than none", "severity": "medium", "category": "product"},
            {"risk": "Acquisition cost of first-time founders exceeds what a low-priced product repays", "severity": "medium", "category": "financial"},
        ],
        "weak_assumptions": [
            "Founders will pay before building rather than after",
            "LLM output is credible enough to base real decisions on",
        ],
        "failure_modes": [
            "Free alternatives (a general AI assistant with a good prompt) capture the casual segment",
            "Positioning collapses into generic 'AI business tools' and acquisition costs explode",
        ],
        "hardest_question": f"Why would a founder pay for '{idea}' instead of prompting a general AI assistant for free?",
    }
