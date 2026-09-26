"""Pydantic I/O shapes for every agent — the only place response shapes are defined.

Every model must validate even in degraded mode (upstream data missing, search failed):
fields default to empty/neutral values, and `verified` flags mark unverified data.
"""
from pydantic import BaseModel, Field


class Competitor(BaseModel):
    name: str
    url: str | None = None
    description: str = ""
    similarity: str = ""  # "direct" | "adjacent" | "partial"


class ResearchFindings(BaseModel):
    competitors: list[Competitor] = Field(default_factory=list)
    summary: str = ""
    sources: list[str] = Field(default_factory=list)
    verified: bool = False  # False => LLM knowledge only (search failed), shown as "unverified"


class MarketEstimate(BaseModel):
    text: str
    basis: str = ""          # where the number comes from
    confidence: str = "low"  # "low" | "medium" | "high"


class MarketAnalysis(BaseModel):
    market_size: list[MarketEstimate] = Field(default_factory=list)
    trends: list[str] = Field(default_factory=list)
    target_audience: list[str] = Field(default_factory=list)
    summary: str = ""
    verified: bool = False


class Risk(BaseModel):
    risk: str
    severity: str = "medium"  # "high" | "medium" | "low"
    category: str = ""        # e.g. "market", "technical", "regulatory"


class Critique(BaseModel):
    risks: list[Risk] = Field(default_factory=list)
    weak_assumptions: list[str] = Field(default_factory=list)
    failure_modes: list[str] = Field(default_factory=list)
    hardest_question: str = ""


class Subscores(BaseModel):
    market_opportunity: int = Field(0, ge=0, le=100)  # weight 25
    differentiation: int = Field(0, ge=0, le=100)     # weight 20
    feasibility: int = Field(0, ge=0, le=100)         # weight 20
    business_viability: int = Field(0, ge=0, le=100)  # weight 20
    timing: int = Field(0, ge=0, le=100)              # weight 15


class FinalEvaluation(BaseModel):
    score: int = Field(0, ge=0, le=100)  # 0.25*market + 0.20*diff + 0.20*feas + 0.20*viable + 0.15*timing
    subscores: Subscores = Field(default_factory=Subscores)
    verdict: str = "High Risk"  # "Promising" | "Needs Rework" | "High Risk"  (>=75 / 50-74 / <50)
    executive_summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    recommendation: str = ""
    next_steps: list[str] = Field(default_factory=list)


class Report(BaseModel):
    """Final assembled report returned to the UI (assembled in Phase 8)."""
    idea: str
    generated_at: str = ""
    mock_mode: bool = False
    research: ResearchFindings = Field(default_factory=ResearchFindings)
    market: MarketAnalysis = Field(default_factory=MarketAnalysis)
    critique: Critique = Field(default_factory=Critique)
    evaluation: FinalEvaluation = Field(default_factory=FinalEvaluation)
    warnings: list[str] = Field(default_factory=list)  # degraded-mode notes, e.g. unverified research
