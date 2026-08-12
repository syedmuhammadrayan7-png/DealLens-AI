"""Deterministic, auditable scoring applied after CrewAI evidence synthesis."""
from __future__ import annotations

from typing import Any

from backend.schemas.case import Recommendation, RiskLevel, ScoreBreakdown, ScoreFactor


def _confidence(sources: int, gaps: int) -> str:
    if sources >= 3 and gaps == 0:
        return "High"
    if sources >= 1:
        return "Medium" if gaps <= 1 else "Low"
    return "Low"


def _breakdown(category: str, factors: list[ScoreFactor], deductions: list[ScoreFactor], sources: int, gaps: int) -> ScoreBreakdown:
    score = max(0, min(100, 30 + sum(item.points for item in factors) - sum(abs(item.points) for item in deductions)))
    return ScoreBreakdown(category=category, score=score, confidence=_confidence(sources, gaps), contributing_factors=factors, deductions=deductions, evidence_summary=[item.note for item in factors + deductions])


def calculate_score_breakdowns(context: dict[str, Any]) -> list[ScoreBreakdown]:
    website, github, finance = context["website_research"], context["github"], context["finance_mcp"]
    market_factors, market_deductions = [], []
    if website.get("status") != "unavailable":
        market_factors.append(ScoreFactor(label="Public product and positioning evidence", points=25, note="Company website was reachable and supplied public positioning.", evidence_refs=[str(website.get("url"))]))
        if website.get("description"):
            market_factors.append(ScoreFactor(label="Published market context", points=10, note="A public website description provides limited market-context evidence.", evidence_refs=[str(website.get("url"))]))
    else:
        market_deductions.append(ScoreFactor(label="Public market evidence gap", points=-15, note="No accessible public company website evidence was available.", evidence_refs=[]))
    market_deductions.append(ScoreFactor(label="Competitor evidence gap", points=-10, note="No independently sourced competitor dataset is connected in this MVP.", evidence_refs=[]))

    tech_factors, tech_deductions = [], []
    if github.get("status") != "unavailable":
        tech_factors.append(ScoreFactor(label="Public repository metadata", points=20, note="Repository metadata was retrieved directly from GitHub.", evidence_refs=[str(context.get("github_url") or "GitHub")]))
        if (github.get("recent_commit_count") or 0) > 0: tech_factors.append(ScoreFactor(label="Recent commit activity", points=15, note="Recent commits are visible in the public repository.", evidence_refs=[]))
        if (github.get("contributor_count") or 0) >= 2: tech_factors.append(ScoreFactor(label="Contributor activity", points=12, note="Multiple public contributors are visible.", evidence_refs=[]))
        if (github.get("release_count") or 0) > 0: tech_factors.append(ScoreFactor(label="Release activity", points=10, note="Published releases are visible.", evidence_refs=[]))
        if github.get("language"): tech_factors.append(ScoreFactor(label="Technology stack visibility", points=5, note="A primary repository language is identified.", evidence_refs=[]))
        if (github.get("open_issues_count") or 0) > 50: tech_deductions.append(ScoreFactor(label="Open-issue classification required", points=-5, note="Large open-issue volume may reflect adoption, features, bugs, or support backlog; it is not treated as a quality failure.", evidence_refs=[]))
    else:
        tech_deductions.append(ScoreFactor(label="Repository evidence unavailable", points=-25, note="Technical maturity cannot be assessed from public repository evidence.", evidence_refs=[]))

    traction_factors, traction_deductions = [], []
    fin = context["financial_inputs"]
    if fin.get("monthly_revenue") is not None: traction_factors.append(ScoreFactor(label="Founder-provided revenue", points=12, note="Monthly revenue was supplied by the case creator; it is not independently verified.", evidence_refs=[]))
    if fin.get("customers") is not None: traction_factors.append(ScoreFactor(label="Founder-provided customer count", points=10, note="Customer count was supplied by the case creator; references are still required.", evidence_refs=[]))
    if not traction_factors: traction_deductions.append(ScoreFactor(label="Traction evidence unavailable", points=-20, note="No revenue, customer, or independently verified adoption evidence was supplied.", evidence_refs=[]))

    financial_factors, financial_deductions = [], []
    if fin.get("monthly_revenue") is not None: financial_factors.append(ScoreFactor(label="Revenue input available", points=10, note="Monthly revenue input is available for deterministic analysis.", evidence_refs=[]))
    if fin.get("monthly_burn") is not None: financial_factors.append(ScoreFactor(label="Burn input available", points=10, note="Monthly burn input is available for deterministic analysis.", evidence_refs=[]))
    if fin.get("cash_available") is not None and fin.get("monthly_burn") not in (None, 0): financial_factors.append(ScoreFactor(label="Runway inputs available", points=15, note="Cash and burn inputs permit a runway calculation.", evidence_refs=[]))
    if finance.get("status") != "unavailable": financial_factors.append(ScoreFactor(label="Finance MCP output", points=8, note="Deterministic Finance MCP output is available.", evidence_refs=[]))
    if not financial_factors: financial_deductions.append(ScoreFactor(label="Financial evidence unavailable", points=-25, note="No revenue, burn, cash, or customer inputs were supplied.", evidence_refs=[]))

    team_deductions = [ScoreFactor(label="Team evidence gap", points=-20, note="No independently verifiable founder or team history source is connected for this case.", evidence_refs=[])]
    team_factors = [ScoreFactor(label="Public company presence", points=8, note="A public company website is available." , evidence_refs=[str(website.get("url"))])] if website.get("status") != "unavailable" else []
    return [
        _breakdown("Market", market_factors, market_deductions, int(website.get("status") != "unavailable"), 1),
        _breakdown("Technology", tech_factors, tech_deductions, int(github.get("status") != "unavailable"), int(github.get("status") == "unavailable")),
        _breakdown("Traction", traction_factors, traction_deductions, len(traction_factors), int(not traction_factors)),
        _breakdown("Financials", financial_factors, financial_deductions, len(financial_factors), int(not financial_factors)),
        _breakdown("Team", team_factors, team_deductions, len(team_factors), 1),
    ]


def recommendation_for(breakdowns: list[ScoreBreakdown], unavailable_count: int) -> tuple[Recommendation, RiskLevel, str, int, str]:
    overall = round(sum(item.score for item in breakdowns) / len(breakdowns))
    low_confidence = sum(item.confidence == "Low" for item in breakdowns)
    if overall < 40 or low_confidence >= 4:
        return Recommendation.HOLD, RiskLevel.HIGH, "Low evidence coverage and/or weak auditable inputs require a hold until core diligence gaps are addressed.", overall, "Low"
    if unavailable_count >= 2 or low_confidence >= 2:
        return Recommendation.VERIFY, RiskLevel.MODERATE, "The score is constrained by material evidence gaps; verify missing financial, team, traction, or technical evidence before advancing.", overall, "Low"
    if overall >= 70:
        return Recommendation.PARTNER_REVIEW, RiskLevel.LOW, "Multiple evidence-backed dimensions support further partner review, subject to normal confirmatory diligence.", overall, "Medium"
    return Recommendation.CONDITIONS, RiskLevel.MODERATE, "The evidence supports progress only with conditions that close the documented diligence gaps.", overall, "Medium"
