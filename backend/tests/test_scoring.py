from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.schemas.case import Recommendation
from backend.services.scoring import CATEGORY_WEIGHTS, calculate_score_breakdowns, recommendation_for


def _github(**overrides):
    now = datetime.now(UTC)
    value = {
        "status": "available", "pushed_at": (now - timedelta(days=14)).isoformat(),
        "created_at": (now - timedelta(days=900)).isoformat(), "recent_commit_count_90d": 8,
        "contributor_count": 12, "release_count": 4,
        "latest_release_at": (now - timedelta(days=45)).isoformat(),
        "stargazers_count": 2_500, "forks_count": 220, "open_issues_count": 18,
        "language": "Python", "license": "Apache-2.0",
    }
    value.update(overrides)
    return value


def _context(**overrides):
    value = {
        "github_url": "https://github.com/acme/project",
        "website_research": {"status": "supported", "url": "https://acme.example", "description": "Platform", "excerpt": "A" * 300},
        "github": _github(), "finance_mcp": {"status": "available", "arpu": None, "net_cash_flow": None},
        "financial_inputs": {}, "report_evidence": [],
    }
    value.update(overrides)
    return value


def _score(context, category):
    return next(item for item in calculate_score_breakdowns(context) if item.category == category)


def _by_category(context):
    return {item.category: item.score for item in calculate_score_breakdowns(context)}


def test_contributor_tiers_are_granular_not_boolean():
    low = _score(_context(github=_github(contributor_count=3)), "Technology")
    deep = _score(_context(github=_github(contributor_count=42)), "Technology")
    assert deep.score > low.score
    assert next(x for x in deep.contributing_factors if x.label == "Contributor depth").points == 9


def test_commit_recency_and_release_cadence_change_technology_score():
    stale = _score(_context(github=_github(pushed_at=(datetime.now(UTC) - timedelta(days=500)).isoformat(), release_count=0, latest_release_at=None)), "Technology")
    active = _score(_context(), "Technology")
    assert active.score > stale.score
    assert next(x for x in active.contributing_factors if x.label == "Release cadence").points > 0


def test_missing_financial_data_and_mcp_availability_do_not_inflate_score():
    with_mcp = _score(_context(finance_mcp={"status": "available", "arpu": None, "net_cash_flow": None}), "Financials")
    without_mcp = _score(_context(finance_mcp={"status": "unavailable"}), "Financials")
    assert with_mcp.score == without_mcp.score == 0
    assert with_mcp.confidence == "Low"


def test_traction_and_team_evidence_tiers_are_distinct():
    weak = _context()
    strong = _context(report_evidence=[
        {"statement": "Independent customer case study confirms paying customers and retention growth.", "status": "verified", "source_type": "third_party"},
        {"statement": "Founder previously built and operated a technical product team.", "status": "supported", "source_type": "professional_profile"},
        {"statement": "Technical and commercial co-founders cover product and go-to-market.", "status": "supported", "source_type": "professional_profile"},
    ])
    assert _score(strong, "Traction").score > _score(weak, "Traction").score
    assert _score(strong, "Team").score > _score(weak, "Team").score
    assert _score(strong, "Team").confidence in {"Medium", "High"}


def test_scores_are_bounded_and_weighted_overall_is_explicit():
    scores = calculate_score_breakdowns(_context(financial_inputs={"monthly_revenue": 100_000, "monthly_burn": 10_000, "cash_available": 200_000, "customers": 80, "previous_monthly_revenue": 80_000, "largest_customer_revenue": 12_000}, finance_mcp={"arpu": 1250, "runway_months": 20, "revenue_growth_pct": 25, "customer_concentration_pct": 12, "net_cash_flow": 90_000}))
    assert sum(CATEGORY_WEIGHTS.values()) == 1
    assert all(0 <= item.score <= 100 for item in scores)
    assert all(factor.max_points >= 0 for item in scores for factor in item.contributing_factors + item.deductions)
    _, _, _, overall, _ = recommendation_for(scores, unavailable_count=0)
    expected = round(sum(item.score * CATEGORY_WEIGHTS[item.category] for item in scores))
    assert overall == expected


def test_critical_evidence_gaps_change_recommendation_even_when_technology_is_strong():
    scores = calculate_score_breakdowns(_context(
        github=_github(contributor_count=110, recent_commit_count_90d=10, stargazers_count=30_000, forks_count=2_000, release_count=12),
        financial_inputs={"monthly_revenue": 200_000, "monthly_burn": 70_000, "cash_available": 1_400_000, "customers": 100, "previous_monthly_revenue": 150_000, "largest_customer_revenue": 20_000},
        finance_mcp={"arpu": 2000, "runway_months": 20, "revenue_growth_pct": 33, "customer_concentration_pct": 10, "net_cash_flow": 130_000},
    ))
    recommendation, _risk, reason, _overall, _confidence = recommendation_for(scores, unavailable_count=2)
    assert recommendation == Recommendation.VERIFY
    assert "Verification" in reason


def test_contrasting_startup_fixtures_produce_meaningfully_different_vectors():
    # Startup A: exceptional public engineering evidence, but no commercial,
    # financial, or independently corroborated team evidence.
    startup_a = _context(github=_github(contributor_count=110, recent_commit_count_90d=10, stargazers_count=35_000, forks_count=4_000, release_count=12))
    # Startup B: less public engineering depth but commercial, financial, and
    # independently supported team evidence.
    startup_b = _context(
        github=_github(contributor_count=8, recent_commit_count_90d=3, stargazers_count=300, forks_count=35, release_count=2),
        financial_inputs={"monthly_revenue": 150_000, "monthly_burn": 60_000, "cash_available": 900_000, "customers": 120, "previous_monthly_revenue": 110_000, "largest_customer_revenue": 25_000},
        finance_mcp={"arpu": 1250, "runway_months": 15, "revenue_growth_pct": 36, "customer_concentration_pct": 16.7, "net_cash_flow": 90_000},
        report_evidence=[
            {"statement": "Independent customer case study confirms paying customer retention and revenue growth.", "status": "verified", "source_type": "third_party"},
            {"statement": "Founder previously led engineering and commercial operations.", "status": "supported", "source_type": "professional_profile"},
            {"statement": "Technical and business co-founders provide complementary coverage.", "status": "supported", "source_type": "professional_profile"},
        ],
    )
    vector_a, vector_b = _by_category(startup_a), _by_category(startup_b)
    assert vector_a != vector_b
    assert vector_a["Technology"] > vector_b["Technology"]
    assert vector_b["Traction"] > vector_a["Traction"]
    assert vector_b["Financials"] > vector_a["Financials"]
    assert vector_b["Team"] > vector_a["Team"]
