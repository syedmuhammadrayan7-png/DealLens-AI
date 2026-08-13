"""Deterministic, evidence-sensitive investment scoring.

CrewAI provides evidence-labelled findings.  This module deliberately ignores
model-proposed numeric scores and turns only supplied, inspectable facts into
bounded category scores.
"""
from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any, Iterable

from backend.schemas.case import Recommendation, RiskLevel, ScoreBreakdown, ScoreFactor

# Explicit investment-oriented weighting. Keep in sync with the README.
CATEGORY_WEIGHTS = {"Market": 0.20, "Technology": 0.20, "Traction": 0.25, "Financials": 0.20, "Team": 0.15}


def _clamp(value: float, maximum: int = 100) -> int:
    return max(0, min(maximum, round(value)))


def _factor(label: str, points: int, maximum: int, note: str, refs: list[str] | None = None) -> ScoreFactor:
    return ScoreFactor(label=label, points=_clamp(points, maximum), max_points=maximum, note=note, evidence_refs=refs or [])


def _deduction(label: str, points: int, note: str) -> ScoreFactor:
    return ScoreFactor(label=label, points=-abs(points), max_points=abs(points), note=note, evidence_refs=[])


def _confidence(available: int, expected: int, independent: int = 0) -> str:
    coverage = available / max(1, expected)
    if coverage >= 0.75 and independent >= 1:
        return "High"
    if coverage >= 0.4:
        return "Medium"
    return "Low"


def _breakdown(category: str, factors: list[ScoreFactor], deductions: list[ScoreFactor], available: int, expected: int, independent: int = 0) -> ScoreBreakdown:
    score = _clamp(sum(item.points for item in factors) + sum(item.points for item in deductions))
    return ScoreBreakdown(
        category=category,
        score=score,
        confidence=_confidence(available, expected, independent),
        contributing_factors=factors,
        deductions=deductions,
        evidence_summary=[item.note for item in factors + deductions],
    )


def _date(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _age_days(value: Any) -> int | None:
    parsed = _date(value)
    return None if parsed is None else max(0, (datetime.now(UTC) - parsed).days)


def _tier(value: int | float | None, ranges: list[tuple[float, int]]) -> int:
    if value is None:
        return 0
    return next((points for ceiling, points in ranges if value <= ceiling), ranges[-1][1])


def _log_points(value: int | float | None, maximum: int, scale: float) -> int:
    if value is None or value <= 0:
        return 0
    return _clamp(maximum * math.log1p(float(value)) / math.log1p(scale), maximum)


def _evidence(context: dict[str, Any]) -> list[dict[str, Any]]:
    raw = context.get("report_evidence", [])
    return [item for item in raw if isinstance(item, dict)]


def _keyword_evidence(items: Iterable[dict[str, Any]], keywords: tuple[str, ...], independent_only: bool = False) -> list[dict[str, Any]]:
    selected = []
    for item in items:
        text = str(item.get("statement", "")).lower()
        status = str(item.get("status", ""))
        independent = status in {"verified", "supported"} and item.get("source_type") not in {"company_website", "public_website", "pitch_deck"}
        if any(word in text for word in keywords) and (not independent_only or independent):
            selected.append(item)
    return selected


def _technology(context: dict[str, Any]) -> ScoreBreakdown:
    github = context.get("github", {})
    if github.get("status") == "unavailable":
        return _breakdown("Technology", [], [_deduction("Repository evidence unavailable", 10, "No public repository evidence was available; technical maturity cannot be assessed.")], 0, 6)
    factors: list[ScoreFactor] = []
    deductions: list[ScoreFactor] = []
    ref = str(context.get("github_url") or "GitHub")
    factors.append(_factor("Repository metadata", 8, 8, "Public repository metadata was retrieved directly from GitHub.", [ref]))

    pushed_days = _age_days(github.get("pushed_at") or github.get("updated_at"))
    recency = _tier(pushed_days, [(7, 18), (30, 16), (90, 13), (180, 9), (365, 5), (10_000, 1)])
    if pushed_days is not None:
        factors.append(_factor("Commit recency", recency, 18, f"Latest public repository activity was {pushed_days} day(s) ago."))
    recent_commits = github.get("recent_commit_count_90d", github.get("recent_commit_count"))
    commit_points = _tier(recent_commits, [(0, 0), (1, 3), (3, 6), (10, 9), (10_000, 10)])
    if recent_commits is not None:
        factors.append(_factor("Recent commit depth", commit_points, 10, f"{recent_commits} public commit(s) were observed in the available recent window."))
    contributors = github.get("contributor_count")
    contributor_points = _tier(contributors, [(0, 0), (5, 3), (20, 6), (50, 9), (100, 11), (10_000, 12)])
    if contributors is not None:
        factors.append(_factor("Contributor depth", contributor_points, 12, f"Repository exposes {contributors} public contributor(s); this measures resilience, not code quality alone."))
    releases = github.get("release_count")
    release_points = _tier(releases, [(0, 0), (1, 3), (2, 5), (5, 8), (10_000, 10)])
    latest_release_days = _age_days(github.get("latest_release_at"))
    if latest_release_days is not None:
        release_points = min(12, release_points + _tier(latest_release_days, [(90, 2), (365, 1), (10_000, 0)]))
    if releases is not None:
        detail = f"{releases} public release(s)"
        if latest_release_days is not None:
            detail += f"; latest was {latest_release_days} day(s) ago"
        factors.append(_factor("Release cadence", release_points, 12, detail + "."))
    age_days = _age_days(github.get("created_at"))
    if age_days is not None:
        factors.append(_factor("Repository maturity", _tier(age_days, [(90, 2), (365, 5), (730, 8), (10_000, 12)]), 12, f"Repository age is approximately {age_days} day(s)."))
    adoption = _log_points((github.get("stargazers_count") or 0) + 2 * (github.get("forks_count") or 0), 14, 10_000)
    factors.append(_factor("Public adoption signals", adoption, 14, f"GitHub exposes {github.get('stargazers_count') or 0} stars and {github.get('forks_count') or 0} forks; logarithmic scaling limits large projects."))
    if github.get("language") or github.get("languages"):
        factors.append(_factor("Technology stack visibility", 4, 4, "A public primary language or language breakdown is available."))
    if github.get("license"):
        factors.append(_factor("License visibility", 4, 4, "A public repository license is declared."))
    issues, stars = github.get("open_issues_count"), github.get("stargazers_count")
    if isinstance(issues, int) and issues >= 100 and issues / max(100, (stars or 0) + 100) >= 0.75:
        deductions.append(_deduction("Open-issue classification required", 6, f"{issues} open issues are high relative to visible adoption. This is a contextual diligence flag, not an automatic quality failure."))
    available = sum(value is not None for value in (pushed_days, recent_commits, contributors, releases, age_days)) + 1
    return _breakdown("Technology", factors, deductions, available, 6, independent=1)


def _market(context: dict[str, Any]) -> ScoreBreakdown:
    website = context.get("website_research", {})
    evidence = _evidence(context)
    factors: list[ScoreFactor] = []
    deductions: list[ScoreFactor] = []
    if website.get("status") != "unavailable":
        if website.get("description"):
            factors.append(_factor("Clear product/category positioning", 12, 12, "A reachable company website publishes a product description; it is weighted as a company claim." , [str(website.get("url"))]))
        if len(str(website.get("excerpt") or "")) >= 180:
            factors.append(_factor("Published market context", 6, 8, "The public website contains enough descriptive context to identify a stated category and audience." , [str(website.get("url"))]))
    else:
        deductions.append(_deduction("Public market evidence gap", 8, "No accessible public company website evidence was available."))
    independent = [item for item in evidence if str(item.get("status")) in {"verified", "supported"} and item.get("source_type") not in {"company_website", "public_website"}]
    market_sources = _keyword_evidence(independent, ("market", "competitor", "competition", "category", "customer", "industry"))
    competitor_sources = _keyword_evidence(independent, ("competitor", "competition", "alternative"))
    differentiation = _keyword_evidence(evidence, ("differenti", "moat", "unique", "advantage"))
    if market_sources:
        factors.append(_factor("Independent market evidence", min(24, 12 + 6 * len(market_sources)), 24, f"{len(market_sources)} independently supported market signal(s) were classified in the report."))
    else:
        deductions.append(_deduction("Independent market evidence gap", 8, "Public company positioning is not a substitute for independent market validation."))
    if competitor_sources:
        factors.append(_factor("Competitor evidence", min(18, 8 + 5 * len(competitor_sources)), 18, f"{len(competitor_sources)} independently supported competitor or alternative signal(s) were recorded."))
    else:
        deductions.append(_deduction("Competitor evidence gap", 6, "No independently sourced competitor dataset or comparison was available."))
    if differentiation:
        factors.append(_factor("Differentiation evidence", min(12, 4 + 4 * len(differentiation)), 12, "Differentiation language is present; company-sourced claims receive limited weight."))
    return _breakdown("Market", factors, deductions, int(website.get("status") != "unavailable") + len(market_sources) + len(competitor_sources), 4, len(independent))


def _traction(context: dict[str, Any]) -> ScoreBreakdown:
    fin = context.get("financial_inputs", {})
    evidence = _evidence(context)
    factors: list[ScoreFactor] = []
    deductions: list[ScoreFactor] = []
    revenue, customers = fin.get("monthly_revenue"), fin.get("customers")
    if revenue is not None:
        factors.append(_factor("Founder-provided revenue", _log_points(revenue, 14, 1_000_000), 14, "Monthly revenue was supplied by the case creator and remains founder-provided until independently corroborated."))
    if customers is not None:
        factors.append(_factor("Founder-provided customer count", _log_points(customers, 12, 10_000), 12, "Customer count was supplied by the case creator and is not treated as verified demand."))
    public_adoption = _keyword_evidence(evidence, ("github", "developer", "download", "adoption", "community"))
    commercial = _keyword_evidence(evidence, ("customer", "case study", "contract", "revenue", "paying", "logo"), independent_only=True)
    growth = _keyword_evidence(evidence, ("growth", "retention", "renewal", "expansion"), independent_only=True)
    if public_adoption:
        factors.append(_factor("Public adoption signals", min(10, 3 + 2 * len(public_adoption)), 10, "Public adoption can support traction but is capped below commercial validation."))
    if commercial:
        factors.append(_factor("Independent commercial validation", min(36, 14 + 7 * len(commercial)), 36, f"{len(commercial)} independently supported customer, case-study, or revenue signal(s) were recorded."))
    if growth:
        factors.append(_factor("Independent growth or retention evidence", min(20, 8 + 6 * len(growth)), 20, "Independently supported growth or retention evidence was recorded."))
    if not factors:
        deductions.append(_deduction("Traction evidence unavailable", 10, "No customer, revenue, adoption, or independently validated traction evidence was supplied."))
    return _breakdown("Traction", factors, deductions, int(revenue is not None) + int(customers is not None) + len(public_adoption) + len(commercial) + len(growth), 5, len(commercial) + len(growth))


def _financials(context: dict[str, Any]) -> ScoreBreakdown:
    fin, metrics = context.get("financial_inputs", {}), context.get("finance_mcp", {})
    factors: list[ScoreFactor] = []
    deductions: list[ScoreFactor] = []
    revenue, burn, cash, customers = fin.get("monthly_revenue"), fin.get("monthly_burn"), fin.get("cash_available"), fin.get("customers")
    if revenue is not None:
        factors.append(_factor("Revenue evidence available", _log_points(revenue, 18, 1_000_000), 18, "A founder-provided monthly revenue input is available for diligence; it is not independently verified."))
    if burn is not None:
        factors.append(_factor("Burn visibility", 12, 12, "A monthly burn input is available."))
    runway = metrics.get("runway_months")
    if cash is not None and burn not in (None, 0):
        runway_points = _tier(runway, [(3, 4), (6, 8), (12, 12), (18, 14), (10_000, 16)])
        factors.append(_factor("Runway", runway_points, 16, f"Cash and burn inputs yield {runway if runway is not None else 'an unavailable'} month(s) of runway through Finance MCP."))
    growth = metrics.get("revenue_growth_pct")
    if fin.get("previous_monthly_revenue") is not None and revenue is not None:
        factors.append(_factor("Revenue growth", _tier(growth, [(-1_000, 0), (0, 3), (10, 7), (30, 11), (10_000, 14)]), 14, f"Finance MCP calculated {growth if growth is not None else 'unavailable'}% monthly revenue growth."))
    if customers not in (None, 0) and revenue is not None:
        factors.append(_factor("ARPU visibility", 8, 8, f"Finance MCP calculated ARPU of {metrics.get('arpu') if metrics.get('arpu') is not None else 'unavailable'} from supplied revenue and customers."))
    concentration = metrics.get("customer_concentration_pct")
    if fin.get("largest_customer_revenue") is not None and revenue not in (None, 0):
        factors.append(_factor("Customer concentration", _tier(concentration, [(20, 10), (40, 8), (60, 5), (80, 2), (10_000, 0)]), 10, f"Finance MCP calculated customer concentration of {concentration if concentration is not None else 'unavailable'}%."))
    if metrics.get("net_cash_flow") is not None:
        factors.append(_factor("Net cash-flow visibility", 6 if metrics["net_cash_flow"] >= 0 else 2, 6, "Finance MCP calculated net cash flow from supplied revenue and burn."))
    if revenue is None and burn is None and cash is None and customers is None:
        deductions.append(_deduction("Financial evidence unavailable", 12, "No revenue, burn, cash, customer, or unit-economics inputs were supplied. Finance MCP availability does not increase this score."))
    # A successful MCP call is deliberately not a factor. It only produces calculations when inputs exist.
    available = sum(value is not None for value in (revenue, burn, cash, customers, fin.get("previous_monthly_revenue"), fin.get("largest_customer_revenue")))
    return _breakdown("Financials", factors, deductions, available, 6)


def _team(context: dict[str, Any]) -> ScoreBreakdown:
    website = context.get("website_research", {})
    evidence = _evidence(context)
    factors: list[ScoreFactor] = []
    deductions: list[ScoreFactor] = []
    team = _keyword_evidence(evidence, ("founder", "co-founder", "ceo", "team", "leadership"))
    independent = [item for item in team if str(item.get("status")) in {"verified", "supported"} and item.get("source_type") not in {"company_website", "public_website", "pitch_deck"}]
    experience = _keyword_evidence(independent, ("previous", "formerly", "experience", "founded", "engineer", "operator"))
    complement = _keyword_evidence(team, ("technical", "commercial", "business", "product", "engineering"))
    if website.get("status") != "unavailable":
        factors.append(_factor("Public company presence", 4, 4, "A public company website is available; this alone does not substantiate team quality."))
    if team:
        factors.append(_factor("Named team evidence", min(16, 5 + 3 * len(team)), 16, f"{len(team)} founder or team-related evidence item(s) were classified."))
    if independent:
        factors.append(_factor("Independently verifiable background", min(28, 10 + 6 * len(independent)), 28, f"{len(independent)} team item(s) have independent support or verification."))
    if experience:
        factors.append(_factor("Relevant prior experience", min(24, 8 + 5 * len(experience)), 24, "Independent evidence describes relevant prior operating or technical experience."))
    if complement:
        factors.append(_factor("Team complementarity evidence", min(12, 3 + 3 * len(complement)), 12, "The available evidence describes technical, product, or commercial coverage."))
    if not team:
        deductions.append(_deduction("Team evidence gap", 10, "No named founder, professional history, or independently verifiable team evidence was available."))
    return _breakdown("Team", factors, deductions, int(website.get("status") != "unavailable") + len(team) + len(independent) + len(experience), 4, len(independent))


def calculate_score_breakdowns(context: dict[str, Any]) -> list[ScoreBreakdown]:
    """Return five immutable scorecards from research facts and labelled evidence."""
    return [_market(context), _technology(context), _traction(context), _financials(context), _team(context)]


def recommendation_for(
    breakdowns: list[ScoreBreakdown],
    unavailable_count: int,
    conflicting_count: int = 0,
    major_red_flags: int = 0,
) -> tuple[Recommendation, RiskLevel, str, int, str]:
    """Calibrate recommendation from weighted quality, confidence, and core gaps."""
    by_category = {item.category: item for item in breakdowns}
    overall = _clamp(sum(by_category[name].score * weight for name, weight in CATEGORY_WEIGHTS.items()))
    low_confidence = sum(item.confidence == "Low" for item in breakdowns)
    critical_gaps = [name for name in ("Traction", "Financials", "Team") if by_category[name].score < 20 and by_category[name].confidence == "Low"]
    confidence = "High" if low_confidence == 0 else "Medium" if low_confidence <= 2 else "Low"
    if overall < 35 or len(critical_gaps) == 3 or unavailable_count >= 5 or major_red_flags >= 4:
        return Recommendation.HOLD, RiskLevel.HIGH, "High Risk / Hold because the weighted score is low or commercial, financial, and team diligence are all materially incomplete.", overall, "Low"
    if len(critical_gaps) >= 2 or unavailable_count >= 2 or conflicting_count >= 2 or low_confidence >= 3:
        gaps = ", ".join(name.lower() for name in critical_gaps) or "material evidence"
        return Recommendation.VERIFY, RiskLevel.MODERATE, f"Additional Verification Required because {gaps} remain materially incomplete despite the available positive signals.", overall, confidence
    if overall >= 75 and confidence in {"High", "Medium"}:
        return Recommendation.PARTNER_REVIEW, RiskLevel.LOW, "Proceed to Partner Review because the weighted evidence is strong across core categories with no material critical-evidence gap.", overall, confidence
    if overall >= 55:
        return Recommendation.CONDITIONS, RiskLevel.MODERATE, "Proceed with Conditions: the evidence supports progress, provided the documented diligence gaps are closed before an investment decision.", overall, confidence
    return Recommendation.VERIFY, RiskLevel.MODERATE, "Additional Verification Required because the weighted evidence remains insufficient for an intuitive advance decision.", overall, confidence
