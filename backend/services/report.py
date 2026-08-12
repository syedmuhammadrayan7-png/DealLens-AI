from __future__ import annotations

from backend.mcp.clients import FinanceMCPClient, MCPUnavailableError
from backend.schemas.case import DueDiligenceReport, Evidence, EvidenceStatus, Recommendation, RiskLevel, StartupInput


def static_demo_report() -> DueDiligenceReport:
    return DueDiligenceReport(
        case_id="demo-northstar-001", company_name="Northstar Ledger", sector="Vertical SaaS", funding_stage="Pre-seed",
        overall_score=72, market_score=76, technical_score=68, traction_score=70, financial_score=69, team_score=75,
        risk_level=RiskLevel.MODERATE, confidence_level="Demo data — not research", is_demo=True,
        investment_thesis="Demo: a workflow platform for independent logistics operators with a focused initial wedge.",
        strengths=["Demo: clear operator workflow", "Demo: recurring-revenue model"],
        red_flags=["Demo: customer concentration needs validation", "Demo: production security evidence unavailable"],
        verified_evidence=[Evidence(statement="This is a fictional product demonstration, not externally verified diligence.", status=EvidenceStatus.UNAVAILABLE, source="DealLens demo", confidence=0)],
        unverified_claims=[Evidence(statement="All traction statements in this report are illustrative demo data.", status=EvidenceStatus.UNVERIFIED, source="DealLens demo", confidence=0)],
        investor_questions=["Which customer cohort renews at the highest rate?", "What security controls are in production?"],
        additional_verification_required=["Customer references", "Security review", "Cap table"],
        recommendation=Recommendation.VERIFY,
    )


def build_financial_snapshot(case: StartupInput) -> dict[str, float | None]:
    data = case.financial_inputs
    client = FinanceMCPClient()
    try:
        return {
            "runway_months": client.call_tool("calculate_runway", cash_available=data.cash_available, monthly_burn=data.monthly_burn),
            "arpu": client.call_tool("calculate_arpu", monthly_revenue=data.monthly_revenue, customers=data.customers),
            "revenue_growth_pct": client.call_tool("calculate_revenue_growth", current=data.monthly_revenue, previous=data.previous_monthly_revenue),
            "customer_concentration_pct": client.call_tool("calculate_customer_concentration", largest_customer_revenue=data.largest_customer_revenue, monthly_revenue=data.monthly_revenue),
        }
    except MCPUnavailableError:
        return {"runway_months": None, "arpu": None, "revenue_growth_pct": None, "customer_concentration_pct": None}
