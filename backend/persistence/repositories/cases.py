from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import Any

from backend.config import Settings
from backend.persistence.database import connection
from backend.schemas.case import CaseStatus, DueDiligenceReport, StartupInput


class CaseRepository:
    def __init__(self, settings: Settings): self.settings = settings

    def create_case(self, case: StartupInput, parent_case_id: str | None = None) -> str:
        case_id = str(uuid4()); fin = case.financial_inputs
        sql = """INSERT INTO deallens_cases (case_id,parent_case_id,company_name,website,industry,funding_stage,funding_requested,github_url,monthly_revenue,monthly_burn,cash_available,customers,previous_monthly_revenue,largest_customer_revenue,pitch_deck_extracted,status,current_stage,agent_status,completed_stages,completion_percentage) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'queued','validating',%s,%s,0)"""
        args = (case_id, parent_case_id, case.company_name, str(case.website) if case.website else None, case.sector, case.funding_stage, case.funding_requested, str(case.github_url) if case.github_url else None, fin.monthly_revenue, fin.monthly_burn, fin.cash_available, fin.customers, fin.previous_monthly_revenue, fin.largest_customer_revenue, bool(case.pitch_deck_text), json.dumps({name:"queued" for name in ("Company Intelligence","Market Analysis","Technical Due Diligence","Financial Analysis","Risk Committee","Investment Memo")}), json.dumps([]))
        with connection(self.settings) as conn:
            with conn.cursor() as cur: cur.execute(sql, args)
        return case_id

    def get_case_input(self, case_id: str) -> StartupInput | None:
        with connection(self.settings) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM deallens_cases WHERE case_id=%s", (case_id,)); row = cur.fetchone()
        if not row: return None
        return StartupInput.model_validate({"company_name":row["company_name"],"website":row["website"],"sector":row["industry"],"funding_stage":row["funding_stage"],"funding_requested":row["funding_requested"],"github_url":row["github_url"],"financial_inputs":{key:row[key] for key in ("monthly_revenue","monthly_burn","cash_available","customers","previous_monthly_revenue","largest_customer_revenue")}})

    def get_status(self, case_id: str) -> CaseStatus | None:
        with connection(self.settings) as conn:
            with conn.cursor() as cur: cur.execute("SELECT * FROM deallens_cases WHERE case_id=%s", (case_id,)); row = cur.fetchone()
        if not row: return None
        return CaseStatus(case_id=str(row["case_id"]), company_name=row["company_name"], status=row["status"], current_stage=row["current_stage"], completed_stages=row["completed_stages"], agent_status=row["agent_status"], evidence_count=row["evidence_count"], errors=[row["error_code"]] if row["error_code"] else [], completion_percentage=row["completion_percentage"])

    def update_status(self, case_id: str, status: CaseStatus, error_message: str | None = None) -> None:
        error_code = status.errors[0] if status.errors else None
        completed_at = datetime.now(timezone.utc) if status.status in {"completed","failed","interrupted"} else None
        with connection(self.settings) as conn:
            with conn.cursor() as cur: cur.execute("UPDATE deallens_cases SET status=%s,current_stage=%s,agent_status=%s,completed_stages=%s,completion_percentage=%s,evidence_count=%s,error_code=%s,error_message=%s,updated_at=NOW(),completed_at=COALESCE(%s,completed_at) WHERE case_id=%s", (status.status,status.current_stage,json.dumps(status.agent_status),json.dumps(status.completed_stages),status.completion_percentage,status.evidence_count,error_code,error_message,completed_at,case_id))

    def persist_report(self, report: DueDiligenceReport) -> None:
        report_id = str(uuid4())
        with connection(self.settings) as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO deallens_reports (report_id,case_id,overall_score,market_score,technical_score,traction_score,financial_score,team_score,risk_level,confidence_level,recommendation,recommendation_reason,investment_thesis,report_json,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (report_id,report.case_id,report.overall_score,report.market_score,report.technical_score,report.traction_score,report.financial_score,report.team_score,report.risk_level.value,report.confidence_level,report.recommendation.value,report.recommendation_reason,report.investment_thesis,json.dumps(report.model_dump(mode="json")),report.generated_at))
                for score in report.score_breakdowns:
                    cur.execute("INSERT INTO deallens_score_breakdowns VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", (str(uuid4()),report_id,score.category,score.score,score.confidence,json.dumps([x.model_dump() for x in score.contributing_factors]),json.dumps([x.model_dump() for x in score.deductions]),json.dumps(score.evidence_summary)))
                groups = [("verified",report.verified_evidence),("founder_provided",report.founder_provided_claims),("unverified",report.unverified_claims),("conflicting",report.conflicting_evidence),("unavailable",report.unavailable_evidence)]
                for _, items in groups:
                    for item in items: cur.execute("INSERT INTO deallens_evidence VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (str(uuid4()),report_id,item.statement,item.status.value,item.source_type,item.source_name,item.source_url,item.confidence,item.observed_at,item.notes))
                lists = [("strength",report.strengths),("red_flag",report.red_flags),("investor_question",report.investor_questions),("verification_required",report.additional_verification_required)]
                for kind, entries in lists:
                    for index, value in enumerate(entries): cur.execute("INSERT INTO deallens_report_lists VALUES (%s,%s,%s,%s,%s)", (str(uuid4()),report_id,kind,value,index))

    def get_report(self, case_id: str) -> DueDiligenceReport | None:
        with connection(self.settings) as conn:
            with conn.cursor() as cur: cur.execute("SELECT report_json FROM deallens_reports WHERE case_id=%s", (case_id,)); row=cur.fetchone()
        return DueDiligenceReport.model_validate(row["report_json"]) if row else None

    def list_cases(self, limit: int, offset: int, status: str | None = None) -> list[dict[str, Any]]:
        clause, args = ("WHERE c.status=%s", [status]) if status else ("", [])
        query = f"SELECT c.case_id,c.company_name,c.industry,c.funding_stage,c.status,c.current_stage,c.created_at,c.completed_at,r.overall_score,r.risk_level,r.confidence_level,r.recommendation FROM deallens_cases c LEFT JOIN deallens_reports r ON r.case_id=c.case_id {clause} ORDER BY c.created_at DESC LIMIT %s OFFSET %s"
        with connection(self.settings) as conn:
            with conn.cursor() as cur: cur.execute(query, tuple(args+[limit,offset])); return cur.fetchall()

    def mark_running_interrupted(self) -> int:
        with connection(self.settings) as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE deallens_cases SET status='interrupted', current_stage='interrupted', error_code='EXECUTION_INTERRUPTED', error_message='Execution was interrupted by a backend restart.', completion_percentage=100, updated_at=NOW() WHERE status='running'")
                return cur.rowcount
