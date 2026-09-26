"""LLM access. USE_MOCK=true routes to canned per-agent responses; the real Gemini
call (plus quota/error mapping) lands in Phase 8 behind the same signature.

call_llm implements the error-handling rules: on any failure it retries up to
MAX_LLM_RETRIES times with an adjusted prompt, then raises LLMError — the graph's
node wrapper turns that into a degraded-but-valid output so the pipeline continues.
"""
import json
import logging

from pydantic import BaseModel

from backend.config import USE_MOCK

logger = logging.getLogger(__name__)

MAX_LLM_RETRIES = 2


class LLMError(RuntimeError):
    """Raised when an agent's LLM call fails on the initial attempt and all retries."""


def call_llm(agent: str, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
    """One agent turn: returns schema-validated output. Retries with an adjusted
    prompt on failure; raises LLMError once all attempts are exhausted.
    """
    prompt = user
    last_error: Exception | None = None
    for attempt in range(1 + MAX_LLM_RETRIES):
        try:
            if USE_MOCK:
                return schema.model_validate(_mock_response(agent, prompt))
            raise NotImplementedError("real LLM calls are wired in Phase 8")
        except NotImplementedError:
            raise
        except Exception as exc:
            last_error = exc
            logger.warning(
                "call_llm: attempt %d/%d for agent=%s failed: %s",
                attempt + 1, 1 + MAX_LLM_RETRIES, agent, exc,
            )
            prompt = _adjusted_prompt(user, schema)
    raise LLMError(f"{agent}: LLM failed after {1 + MAX_LLM_RETRIES} attempts") from last_error


def _adjusted_prompt(user: str, schema: type[BaseModel]) -> str:
    return f"{user}\n\nIMPORTANT: Respond ONLY with valid JSON matching this schema: {json.dumps(schema.model_json_schema())}"


def _mock_response(agent: str, user: str) -> dict:
    """MOCK_MODE: canned, realistic JSON per agent; builders are added per phase."""
    logger.info("MOCK_MODE: canned LLM response for agent=%s", agent)
    builders = {"researcher": _mock_researcher, "analyst": _mock_analyst, "critic": _mock_critic, "evaluator": _mock_evaluator}
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


def _mock_evaluator(idea: str) -> dict:
    # Subscores are consistent with the canned upstream mock data; the node
    # recomputes score/verdict from them, so 70/45/75/60/55 lands at 62 = "Needs Rework".
    return {
        "score": 62,
        "subscores": {
            "market_opportunity": 70,
            "differentiation": 45,
            "feasibility": 75,
            "business_viability": 60,
            "timing": 55,
        },
        "verdict": "Needs Rework",
        "executive_summary": f"Mock evaluation for: {idea}. A real and growing market, but the MOCK_MODE sample shows a crowded space with a thin moat and weak retention economics.",
        "strengths": [
            "Large, growing market with clear demand signal",
            "Low build cost — an MVP is cheap to ship and test",
        ],
        "recommendation": "Promising direction that needs a sharper wedge: niche down to one underserved founder segment and add a recurring reason to return before scaling spend.",
        "next_steps": [
            "Interview 20 first-time founders about their current validation process",
            "Ship a one-page MVP scoring a single niche and measure completion rate",
            "Test willingness to pay at $19 versus a free tool with paid upgrades",
        ],
    }
