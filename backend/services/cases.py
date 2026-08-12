"""Durable case lifecycle service backed by the case repository."""
from __future__ import annotations

from dataclasses import dataclass

from backend.config import Settings
from backend.crew.schema_validation import StructuredOutputSchemaError
from backend.crew.flow import AGENT_NAMES, DueDiligenceFlow, DueDiligenceState
from backend.persistence.repositories.cases import CaseRepository
from backend.persistence.repositories.jobs import Job, JobRepository
from backend.schemas.case import CaseStatus, DueDiligenceReport, StartupInput


@dataclass
class CaseRecord:
    case: StartupInput
    status: CaseStatus
    report: DueDiligenceReport | None = None


class CaseManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.repository = CaseRepository(settings)
        self.jobs = JobRepository(settings)

    def create(self, case: StartupInput, parent_case_id: str | None = None) -> CaseRecord:
        case_id = self.repository.create_case(case, parent_case_id)
        status = self.repository.get_status(case_id)
        assert status is not None
        return CaseRecord(case=case, status=status)

    def get(self, case_id: str) -> CaseRecord | None:
        status, case = self.repository.get_status(case_id), self.repository.get_case_input(case_id)
        if not status or not case:
            return None
        return CaseRecord(case=case, status=status, report=self.repository.get_report(case_id))

    def _update(self, case_id: str, stage: str, agents: dict[str, str] | None = None, job_id: str | None = None) -> None:
        record = self.get(case_id)
        if record is None:
            return
        status = record.status
        status.status = "running"
        status.current_stage = stage
        if agents:
            status.agent_status.update(agents)
        stages = ["validating", "company_research", "market_analysis", "technical_analysis", "financial_analysis", "evidence_review", "risk_committee", "investment_memo"]
        status.completed_stages = stages[:stages.index(stage)] if stage in stages else stages
        status.completion_percentage = min(95, round((len(status.completed_stages) / len(stages)) * 100))
        self.repository.update_status(case_id, status)
        if job_id: self.jobs.update_stage(job_id, stage)

    @staticmethod
    def _safe_error_code(exc: Exception) -> str:
        message = str(exc).lower()
        if isinstance(exc, StructuredOutputSchemaError) or ("invalid schema" in message and "response_format" in message): return "STRUCTURED_OUTPUT_SCHEMA_ERROR"
        if "401" in message or "403" in message or "authentication" in message: return "OPENAI_AUTHENTICATION_ERROR"
        if "400" in message or "invalid request" in message: return "OPENAI_INVALID_REQUEST"
        return "DILIGENCE_WORKFLOW_ERROR"

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        message = str(exc).lower()
        return any(word in message for word in ("timeout", "connection", "temporar", "rate limit", "503", "502"))

    def run(self, case_id: str, job: Job | None = None) -> None:
        record = self.get(case_id)
        if record is None: return
        case = record.case
        state = DueDiligenceState(case_id=case_id, company_name=case.company_name, website=str(case.website) if case.website else None, industry=case.sector, funding_stage=case.funding_stage, funding_requested=case.funding_requested, github_url=str(case.github_url) if case.github_url else None, financial_inputs=case.financial_inputs.model_dump(), pitch_deck_text=case.pitch_deck_text)
        try:
            report = DueDiligenceFlow(self.settings, lambda stage, agents=None: self._update(case_id, stage, agents, job.job_id if job else None)).run(case, state)
            # Persist report first. A case cannot be completed without durable report storage.
            self.repository.persist_report(report)
            final = self.repository.get_status(case_id)
            assert final is not None
            final.status, final.current_stage, final.completion_percentage = "completed", "completed", 100
            final.completed_stages = ["validating", "company_research", "market_analysis", "technical_analysis", "financial_analysis", "evidence_review", "risk_committee", "investment_memo"]
            final.agent_status = {name: "completed" for name in AGENT_NAMES}
            final.evidence_count = sum(len(items) for items in (report.verified_evidence, report.founder_provided_claims, report.unverified_claims, report.conflicting_evidence, report.unavailable_evidence))
            self.repository.update_status(case_id, final)
            if job: self.jobs.complete(job.job_id)
        except Exception as exc:
            failed = self.repository.get_status(case_id)
            if failed:
                failed.status, failed.current_stage, failed.completion_percentage = "failed", "failed", 100
                failed.agent_status = {name: ("failed" if value == "running" else value) for name, value in failed.agent_status.items()}
                failed.errors = [self._safe_error_code(exc)]
                self.repository.update_status(case_id, failed, "The due-diligence workflow could not complete.")
            if job: self.jobs.fail(job, self._safe_error_code(exc), self._retryable(exc))

    def retry(self, case_id: str) -> CaseRecord | None:
        record = self.get(case_id)
        if record is None or record.status.status not in {"failed", "interrupted"}: return None
        return self.create(record.case, parent_case_id=case_id)

    def enqueue(self, case_id: str) -> Job:
        return self.jobs.enqueue(case_id)


def get_case_manager(settings: Settings) -> CaseManager:
    return CaseManager(settings)
