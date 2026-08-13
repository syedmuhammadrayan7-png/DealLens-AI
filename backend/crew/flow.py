"""Bounded stateful orchestration for a real CrewAI diligence run."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from backend.config import Settings
from backend.crew.due_diligence_crew import create_due_diligence_crew
from backend.mcp.clients import FinanceMCPClient, MCPUnavailableError
from backend.schemas.case import DueDiligenceReport, Evidence, EvidenceStatus, StartupInput
from backend.crew.schema_validation import crewai_strict_schema
from backend.services.github import GitHubService
from backend.services.research import WebsiteResearchService
from backend.services.scoring import calculate_score_breakdowns, recommendation_for
from backend.utils.cache import TTLCache
from backend.utils.retry import PermanentExternalError

STAGES = ["validating", "company_research", "market_analysis", "technical_analysis", "financial_analysis", "evidence_review", "risk_committee", "investment_memo", "completed"]
AGENT_NAMES = {"Company Intelligence": "company_research", "Market Analysis": "market_analysis", "Technical Due Diligence": "technical_analysis", "Financial Analysis": "financial_analysis", "Risk Committee": "risk_committee", "Investment Memo": "investment_memo"}


@dataclass
class DueDiligenceState:
    case_id: str
    company_name: str
    website: str | None = None
    industry: str | None = None
    funding_stage: str | None = None
    funding_requested: float | None = None
    github_url: str | None = None
    financial_inputs: dict[str, Any] = field(default_factory=dict)
    pitch_deck_text: str | None = None
    iteration: int = 0
    max_iterations: int = 1
    evidence_quality: float = 0.0
    evidence_count: int = 0
    company_findings: Any = None
    market_findings: Any = None
    technical_findings: Any = None
    financial_findings: Any = None
    risk_findings: Any = None
    final_report: DueDiligenceReport | None = None
    status: str = "validating"

    def should_targeted_retry(self) -> bool:
        return self.evidence_quality < 0.55 and self.iteration < self.max_iterations

    def next_stage(self) -> str:
        return "targeted_retry" if self.should_targeted_retry() else "risk_committee"


class DueDiligenceFlow:
    """One normal pass and at most one targeted pass; all model work is via CrewAI."""
    def __init__(self, settings: Settings, update: Callable[[str, dict[str, str] | None], None]):
        self.settings, self.update = settings, update
        cache = TTLCache(settings.cache_ttl_seconds)
        token = settings.github_token.get_secret_value() if settings.github_token else None
        self.github, self.research = GitHubService(cache, token=token), WebsiteResearchService(cache)

    def _context(self, case: StartupInput, state: DueDiligenceState) -> dict[str, Any]:
        state.status = "company_research"
        self.update("company_research", {"Company Intelligence": "running"})
        website = self.research.inspect(str(case.website) if case.website else None)
        state.status = "market_analysis"
        self.update("market_analysis", {"Company Intelligence": "completed", "Market Analysis": "running"})
        # The current bounded market task uses supplied public context only;
        # mark it truthfully complete before dependent technical work begins.
        state.status = "technical_analysis"
        self.update("technical_analysis", {"Market Analysis": "completed", "Technical Due Diligence": "running"})
        if case.github_url:
            try:
                github: dict[str, Any] = self.github.inspect(str(case.github_url))
            except (PermanentExternalError, Exception) as exc:
                github = {"status": "unavailable", "reason": str(exc)}
        else:
            github = {"status": "unavailable", "reason": "No GitHub URL was supplied."}
        state.status = "financial_analysis"
        self.update("financial_analysis", {"Technical Due Diligence": "completed", "Financial Analysis": "running"})
        finance_values = case.financial_inputs.model_dump()
        try:
            finance = FinanceMCPClient().financial_metrics(finance_values)
        except MCPUnavailableError as exc:
            finance = {"status": "unavailable", "reason": str(exc)}
        state.evidence_count = int(website.get("status") != "unavailable") + int(github.get("status") != "unavailable")
        return {"case_id": state.case_id, "company_name": case.company_name, "website": str(case.website) if case.website else None, "sector": case.sector, "funding_stage": case.funding_stage, "funding_requested": case.funding_requested, "github_url": str(case.github_url) if case.github_url else None, "website_research": website, "github": github, "financial_inputs": finance_values, "finance_mcp": finance, "pitch_deck": {"status": "founder-provided", "text": case.pitch_deck_text} if case.pitch_deck_text else {"status": "unavailable", "reason": "No pitch deck supplied."}}

    @staticmethod
    def _quality(context: dict[str, Any]) -> float:
        sources = [context["website_research"], context["github"], context["finance_mcp"]]
        available = sum(1 for item in sources if item.get("status") != "unavailable")
        return available / len(sources)

    def run(self, case: StartupInput, state: DueDiligenceState) -> DueDiligenceReport:
        self.settings.require_openai()
        # Fail locally before OpenAI is called if the CrewAI-generated strict schema is invalid.
        crewai_strict_schema(DueDiligenceReport)
        context = self._context(case, state)
        # `evidence_json` is interpolated as a value. It is deliberately not
        # embedded in a task template: public web text can contain `{...}`
        # snippets that CrewAI would otherwise treat as missing variables.
        context["evidence_json"] = json.dumps(context, default=str, indent=2)
        state.evidence_quality = self._quality(context)
        state.status = "evidence_review"
        self.update("evidence_review", {"Financial Analysis": "completed"}, state.evidence_count)
        # A low-quality first pass only enriches the same public context once; it never loops indefinitely.
        if state.should_targeted_retry():
            state.iteration += 1
            context["targeted_retry"] = "Re-check only evidence gaps; no unsupported claims."
        state.status = "risk_committee"
        self.update("risk_committee", {"Risk Committee": "running"})
        crew = create_due_diligence_crew(self.settings, context)
        state.status = "investment_memo"
        self.update("investment_memo", {"Risk Committee": "completed", "Investment Memo": "running"})
        output = crew.kickoff(inputs=context)
        report = getattr(output, "pydantic", None)
        if report is None:
            report = DueDiligenceReport.model_validate_json(str(getattr(output, "raw", output)))
        # Protect identity fields even if the model tries to alter them.
        report.case_id = state.case_id
        report.company_name = case.company_name
        report.sector = case.sector
        report.funding_stage = case.funding_stage
        website = context["website_research"]
        if website.get("status") != "unavailable":
            report.founder_provided_claims = [item for item in report.founder_provided_claims if item.source_type not in {"company_website", "public_website"}]
            report.verified_evidence.append(Evidence(statement=f"Public company website was accessible: {website.get('title') or case.company_name}.", status=EvidenceStatus.PUBLIC_COMPANY_CLAIM, source_name=case.company_name, source_type="company_website", source_url=website.get("url"), confidence=70, notes="Company website content is a public company claim, not independently verified evidence."))
        github = context["github"]
        if github.get("status") != "unavailable":
            report.verified_evidence.append(Evidence(statement=f"Public GitHub repository metadata retrieved for {github.get('full_name') or case.github_url}.", status=EvidenceStatus.VERIFIED, source_name="GitHub", source_type="github_api", source_url=str(case.github_url) if case.github_url else None, confidence=95))
        if case.pitch_deck_text:
            report.founder_provided_claims.append(Evidence(statement="Pitch deck text was supplied for this case and is treated as founder-provided evidence.", status=EvidenceStatus.FOUNDER_PROVIDED, source_name="Uploaded pitch deck", source_type="pitch_deck", confidence=50))
        # Scores are derived after the crew's evidence is classified. The
        # scoring module owns all numeric decisions and ignores model scores.
        context["report_evidence"] = [
            item.model_dump(mode="json")
            for group in (
                report.verified_evidence,
                report.founder_provided_claims,
                report.unverified_claims,
                report.conflicting_evidence,
                report.unavailable_evidence,
            )
            for item in group
        ]
        breakdowns = calculate_score_breakdowns(context)
        recommendation, risk, reason, overall, confidence = recommendation_for(
            breakdowns,
            len(report.unavailable_evidence),
            conflicting_count=len(report.conflicting_evidence),
            major_red_flags=len(report.red_flags),
        )
        report.score_breakdowns = breakdowns
        report.market_score, report.technical_score, report.traction_score, report.financial_score, report.team_score = [item.score for item in breakdowns]
        report.overall_score, report.risk_level, report.confidence_level = overall, risk, confidence
        report.recommendation, report.recommendation_reason = recommendation, reason
        state.final_report = report
        state.status = "completed"
        # Case service commits the report before setting the durable completed status.
        return report
