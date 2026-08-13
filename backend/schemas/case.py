from __future__ import annotations

from enum import Enum
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field, HttpUrl, field_validator


class EvidenceStatus(str, Enum):
    VERIFIED = "verified"
    SUPPORTED = "supported"
    PUBLIC_COMPANY_CLAIM = "public_company_claim"
    FOUNDER_PROVIDED = "founder-provided"
    UNVERIFIED = "unverified"
    CONFLICTING = "conflicting"
    UNAVAILABLE = "unavailable"


class Evidence(BaseModel):
    statement: str = Field(min_length=3, max_length=1000)
    status: EvidenceStatus
    source: str | None = None
    source_type: str | None = None
    source_name: str | None = None
    source_url: str | None = None
    confidence: int = Field(ge=0, le=100)
    observed_at: datetime | None = None
    notes: str | None = None


class ScoreFactor(BaseModel):
    label: str
    points: int
    max_points: int = Field(default=0, ge=0)
    note: str
    evidence_refs: list[str] = Field(default_factory=list)


class ScoreBreakdown(BaseModel):
    category: str
    score: int = Field(ge=0, le=100)
    confidence: str
    contributing_factors: list[ScoreFactor] = Field(default_factory=list)
    deductions: list[ScoreFactor] = Field(default_factory=list)
    evidence_summary: list[str] = Field(default_factory=list)


class FinancialInputs(BaseModel):
    monthly_revenue: float | None = Field(default=None, ge=0)
    monthly_burn: float | None = Field(default=None, ge=0)
    cash_available: float | None = Field(default=None, ge=0)
    customers: int | None = Field(default=None, ge=0)
    previous_monthly_revenue: float | None = Field(default=None, ge=0)
    largest_customer_revenue: float | None = Field(default=None, ge=0)


class StartupInput(BaseModel):
    company_name: str = Field(min_length=2, max_length=120)
    website: HttpUrl | None = None
    sector: str = Field(min_length=2, max_length=80)
    funding_stage: str = Field(min_length=2, max_length=60)
    funding_requested: float | None = Field(default=None, ge=0)
    github_url: HttpUrl | None = None
    financial_inputs: FinancialInputs = Field(default_factory=FinancialInputs)
    pitch_deck_path: str | None = None
    pitch_deck_text: str | None = Field(default=None, max_length=50_000)

    @field_validator("github_url")
    @classmethod
    def public_github_repo_only(cls, value: HttpUrl | None) -> HttpUrl | None:
        if value and value.host not in {"github.com", "www.github.com"}:
            raise ValueError("GitHub URL must use github.com")
        return value


class RiskLevel(str, Enum):
    LOW = "Low"
    MODERATE = "Moderate"
    HIGH = "High"


class Recommendation(str, Enum):
    PARTNER_REVIEW = "Proceed to Partner Review"
    CONDITIONS = "Proceed with Conditions"
    VERIFY = "Additional Verification Required"
    HOLD = "High Risk / Hold"


class DueDiligenceReport(BaseModel):
    case_id: str = Field(default_factory=lambda: str(uuid4()))
    company_name: str
    sector: str
    funding_stage: str
    overall_score: int = Field(ge=0, le=100)
    market_score: int = Field(ge=0, le=100)
    technical_score: int = Field(ge=0, le=100)
    traction_score: int = Field(ge=0, le=100)
    financial_score: int = Field(ge=0, le=100)
    team_score: int = Field(ge=0, le=100)
    risk_level: RiskLevel
    confidence_level: str
    investment_thesis: str
    strengths: list[str]
    red_flags: list[str]
    verified_evidence: list[Evidence]
    unverified_claims: list[Evidence]
    founder_provided_claims: list[Evidence] = Field(default_factory=list)
    conflicting_evidence: list[Evidence] = Field(default_factory=list)
    unavailable_evidence: list[Evidence] = Field(default_factory=list)
    investor_questions: list[str]
    additional_verification_required: list[str]
    recommendation: Recommendation
    recommendation_reason: str = ""
    score_breakdowns: list[ScoreBreakdown] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CaseAccepted(BaseModel):
    case_id: str
    status: str = "queued"
    detail: str = "Due diligence case accepted."


class CaseStatus(BaseModel):
    case_id: str
    company_name: str
    status: str
    current_stage: str
    completed_stages: list[str] = Field(default_factory=list)
    agent_status: dict[str, str] = Field(default_factory=dict)
    evidence_count: int = 0
    errors: list[str] = Field(default_factory=list)
    completion_percentage: int = Field(ge=0, le=100)


class ToolDiscovery(BaseModel):
    server: str
    tools: list[str]
    resources: list[str]
    prompts: list[str]
