"""Repository tests use a fake repository; they never touch the live Supabase database."""
from datetime import datetime, timezone

from backend.schemas.case import CaseStatus, DueDiligenceReport, Evidence, EvidenceStatus, Recommendation, RiskLevel, ScoreBreakdown, ScoreFactor, StartupInput
from backend.services.cases import CaseManager
from backend.persistence.repositories.jobs import Job
import logging


class FakeRepository:
    def __init__(self): self.cases={}; self.reports={}; self.order=[]; self.interrupted=0
    def create_case(self, case, parent_case_id=None):
        key=f"case-{len(self.cases)+1}"; self.cases[key]={"case":case,"status":CaseStatus(case_id=key,company_name=case.company_name,status="queued",current_stage="validating",completion_percentage=0),"parent":parent_case_id}; self.order.append(key); return key
    def get_status(self,key): return self.cases.get(key,{}).get("status")
    def get_case_input(self,key): return self.cases.get(key,{}).get("case")
    def update_status(self,key,status,error_message=None): self.cases[key]["status"]=status
    def persist_report(self,report): self.reports[report.case_id]=report
    def get_report(self,key): return self.reports.get(key)
    def list_cases(self,limit,offset,status=None):
        keys=list(reversed(self.order)); return [{"case_id":key,"company_name":self.cases[key]["case"].company_name} for key in keys if not status or self.cases[key]["status"].status==status][offset:offset+limit]
    def mark_running_interrupted(self):
        for value in self.cases.values():
            if value["status"].status=="running": value["status"].status="interrupted"; self.interrupted+=1
        return self.interrupted


class FakeJobs:
    def __init__(self): self.jobs=[]; self.claimed=set(); self.completed=[]; self.failed=[]
    def enqueue(self, case_id):
        from backend.persistence.repositories.jobs import Job
        job=Job(f"job-{len(self.jobs)+1}",case_id,"queued","validating",0,2); self.jobs.append(job); return job
    def claim_next(self, _worker="test"):
        for job in self.jobs:
            if job.status in {"queued","retry_pending"} and job.job_id not in self.claimed:
                self.claimed.add(job.job_id); job.status="running"; job.attempts+=1; return job
        return None
    def update_stage(self,*_): pass
    def complete(self, job_id): self.completed.append(job_id)
    def fail(self, job, code, retryable): self.failed.append((job.job_id,code,retryable)); return "failed"
    def recover_stale(self): return 0


def manager():
    instance=CaseManager.__new__(CaseManager); instance.settings=None; instance.repository=FakeRepository(); instance.jobs=FakeJobs(); return instance


def case(name="Acme"): return StartupInput(company_name=name,sector="SaaS",funding_stage="Seed")


def report(case_id): return DueDiligenceReport(case_id=case_id,company_name="Acme",sector="SaaS",funding_stage="Seed",overall_score=60,market_score=60,technical_score=60,traction_score=60,financial_score=60,team_score=60,risk_level=RiskLevel.MODERATE,confidence_level="Medium",investment_thesis="Evidence-backed thesis.",strengths=[],red_flags=[],verified_evidence=[],unverified_claims=[],investor_questions=[],additional_verification_required=[],recommendation=Recommendation.CONDITIONS,generated_at=datetime.now(timezone.utc))


def test_create_retrieve_update_and_history_persist_in_repository():
    m=manager(); first=m.create(case("First")); second=m.create(case("Second")); assert m.get(first.status.case_id).case.company_name=="First"
    first.status.status="running"; m.repository.update_status(first.status.case_id,first.status)
    assert m.get(first.status.case_id).status.status=="running"
    assert [x["company_name"] for x in m.repository.list_cases(1,0)]==["Second"]


def test_report_survives_manager_recreation_and_cache_is_irrelevant():
    m=manager(); record=m.create(case()); item=report(record.status.case_id); m.repository.persist_report(item)
    recreated=CaseManager.__new__(CaseManager); recreated.settings=None; recreated.repository=m.repository
    assert recreated.get(record.status.case_id).report==item


def test_retry_creates_new_case_without_destroying_old_history():
    m=manager(); old=m.create(case()); old.status.status="interrupted"; m.repository.update_status(old.status.case_id,old.status)
    retry=m.retry(old.status.case_id); assert retry and retry.status.case_id!=old.status.case_id
    assert m.repository.cases[retry.status.case_id]["parent"]==old.status.case_id


def test_running_case_is_marked_interrupted_on_restart_simulation():
    m=manager(); running=m.create(case()); running.status.status="running"; m.repository.update_status(running.status.case_id,running.status)
    assert m.repository.mark_running_interrupted()==1
    assert m.get(running.status.case_id).status.status=="interrupted"


def test_job_enqueue_claim_and_duplicate_prevention():
    m=manager(); record=m.create(case()); job=m.enqueue(record.status.case_id)
    assert m.jobs.claim_next().job_id == job.job_id
    assert m.jobs.claim_next() is None


def test_manual_retry_has_fresh_case_and_fresh_job():
    m=manager(); old=m.create(case()); old.status.status="failed"; m.repository.update_status(old.status.case_id,old.status)
    retry=m.retry(old.status.case_id); job=m.enqueue(retry.status.case_id)
    assert retry.status.case_id != old.status.case_id and job.case_id == retry.status.case_id


def test_public_evidence_count_updates_before_final_memo():
    m = manager(); record = m.create(case())
    m._update(record.status.case_id, "evidence_review", {"Market Analysis": "completed"}, evidence_count=2)
    assert m.get(record.status.case_id).status.evidence_count == 2
    assert m.get(record.status.case_id).status.agent_status["Market Analysis"] == "completed"


def test_workflow_failure_logs_diagnostics_but_persists_safe_error(monkeypatch, caplog):
    m = manager(); record = m.create(case())
    class FailingFlow:
        def __init__(self, *_args, **_kwargs): pass
        def run(self, *_args, **_kwargs): raise ValueError("internal interpolation failure")
    monkeypatch.setattr("backend.services.cases.DueDiligenceFlow", FailingFlow)
    with caplog.at_level(logging.ERROR, logger="deallens.cases"):
        m.run(record.status.case_id, Job("job-1", record.status.case_id, "running", "investment_memo", 1, 2))
    status = m.get(record.status.case_id).status
    assert status.errors == ["DILIGENCE_WORKFLOW_ERROR"]
    assert "case_id=" in caplog.text and "exception_type=ValueError" in caplog.text
    assert "internal interpolation failure" not in status.errors[0]


def test_wandb_like_workflow_completes_with_evidence_and_granular_scorecards(monkeypatch):
    m = manager(); record = m.create(case("Weights & Biases"))
    completed_report = report(record.status.case_id)
    completed_report.verified_evidence = []
    completed_report.unavailable_evidence = []
    completed_report.founder_provided_claims = []
    completed_report.verified_evidence.extend([
        Evidence(statement="Public website was accessible.", status=EvidenceStatus.PUBLIC_COMPANY_CLAIM, confidence=70),
        Evidence(statement="GitHub metadata was retrieved.", status=EvidenceStatus.VERIFIED, confidence=95),
    ])
    completed_report.score_breakdowns = [ScoreBreakdown(category="Technology", score=93, confidence="High", contributing_factors=[ScoreFactor(label="Commit recency", points=18, max_points=18, note="Recent activity.")])]
    class SuccessfulFlow:
        def __init__(self, _settings, update): self.update = update
        def run(self, _case, _state):
            self.update("market_analysis", {"Market Analysis": "completed"}, 2)
            return completed_report
    monkeypatch.setattr("backend.services.cases.DueDiligenceFlow", SuccessfulFlow)
    m.run(record.status.case_id, Job("job-1", record.status.case_id, "running", "investment_memo", 1, 2))
    saved = m.get(record.status.case_id)
    assert saved and saved.status.status == "completed"
    assert saved.status.evidence_count == 2
    assert all(value == "completed" for value in saved.status.agent_status.values())
    assert saved.report and saved.report.score_breakdowns[0].contributing_factors[0].max_points == 18
