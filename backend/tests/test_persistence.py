"""Repository tests use a fake repository; they never touch the live Supabase database."""
from datetime import datetime, timezone

from backend.schemas.case import CaseStatus, DueDiligenceReport, Recommendation, RiskLevel, StartupInput
from backend.services.cases import CaseManager


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
