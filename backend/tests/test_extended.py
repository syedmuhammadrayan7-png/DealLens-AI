from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from backend.config import OpenAIConfigurationError, Settings
from backend.main import app
from backend.mcp.servers.finance_server import PRESEED_FRAMEWORK, RISK_POLICY, SAAS_METRICS
from backend.mcp.clients import FinanceMCPClient
from backend.crew.schema_validation import StructuredOutputSchemaError, crewai_strict_schema, validate_strict_schema
from backend.services.cases import CaseManager
from backend.services.pdf import render_report_pdf
from backend.services.scoring import calculate_score_breakdowns, recommendation_for
from backend.schemas.case import DueDiligenceReport, Evidence, EvidenceStatus, Recommendation, RiskLevel, StartupInput
from backend.services.github import GitHubService
from backend.services.pitch_deck import PitchDeckError, extract_pitch_deck
from backend.utils.cache import TTLCache
from backend.utils.retry import ExternalServiceError, retry_external


def valid_case() -> StartupInput:
    return StartupInput(company_name="Acme", sector="SaaS", funding_stage="Seed")


def settings_without_key() -> Settings:
    # model_construct bypasses the local developer .env intentionally for this negative-path test.
    return Settings.model_construct(openai_api_key=None, openai_model="gpt-4.1-mini", openai_timeout_seconds=45, openai_max_retries=2, cache_ttl_seconds=900, max_pitch_deck_mb=10)


def test_missing_openai_key_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert settings_without_key().openai_model
    with pytest.raises(OpenAIConfigurationError):
        settings_without_key().require_openai()


def test_mcp_resources_and_prompt_content_exist():
    assert "Pre-seed" in PRESEED_FRAMEWORK
    assert "Evidence policy" in RISK_POLICY
    assert "SaaS metrics" in SAAS_METRICS


def test_finance_mcp_client_calls_server_over_stdio():
    assert FinanceMCPClient().call_tool("calculate_runway", cash_available=120_000, monthly_burn=10_000) == 12.0


def test_finance_metrics_only_calculates_available_inputs(monkeypatch):
    client = FinanceMCPClient()
    calls = []
    def call(name, **values):
        calls.append(name)
        return {"arpu": 100, "net_cash_flow": 50} if name == "calculate_basic_unit_economics" else 12.0
    monkeypatch.setattr(client, "call_tool", call)
    metrics = client.financial_metrics({"monthly_revenue": 150, "monthly_burn": 100, "cash_available": 1200, "customers": 2, "previous_monthly_revenue": None, "largest_customer_revenue": None})
    assert metrics["runway_months"] == 12.0
    assert metrics["revenue_growth_pct"] is None and metrics["customer_concentration_pct"] is None
    assert calls == ["calculate_basic_unit_economics", "calculate_runway"]


def test_github_url_parsing_and_unavailable_path():
    service = GitHubService(TTLCache())
    with pytest.raises(Exception):
        service.inspect("https://github.com/not a repo")


def test_retry_stops_after_limit():
    calls = 0
    def transient():
        nonlocal calls
        calls += 1
        raise RuntimeError("network")
    with pytest.raises(ExternalServiceError):
        retry_external(transient, max_attempts=3, base_delay_seconds=0)
    assert calls == 3


def test_pitch_deck_rejects_non_pdf_and_size():
    settings = Settings.model_construct(openai_api_key=None, openai_model="gpt-4.1-mini", openai_timeout_seconds=45, openai_max_retries=2, cache_ttl_seconds=900, max_pitch_deck_mb=1)
    with pytest.raises(PitchDeckError):
        extract_pitch_deck("deck.txt", "text/plain", b"nope", settings)
    with pytest.raises(PitchDeckError):
        extract_pitch_deck("deck.pdf", "application/pdf", b"x" * (1024 * 1024 + 1), settings)


def test_final_report_has_explicit_nonverified_categories():
    report = DueDiligenceReport(company_name="Acme", sector="SaaS", funding_stage="Seed", overall_score=50, market_score=50, technical_score=50, traction_score=50, financial_score=50, team_score=50, risk_level=RiskLevel.MODERATE, confidence_level="Low", investment_thesis="Evidence is limited.", strengths=[], red_flags=[], verified_evidence=[], unverified_claims=[], unavailable_evidence=[Evidence(statement="Public data unavailable", status=EvidenceStatus.UNAVAILABLE, confidence=0)], investor_questions=[], additional_verification_required=[], recommendation=Recommendation.VERIFY)
    assert report.unavailable_evidence[0].status == EvidenceStatus.UNAVAILABLE
    assert not report.verified_evidence


def test_public_company_claim_has_distinct_taxonomy_and_provenance():
    evidence = Evidence(statement="Company website describes a developer platform.", status=EvidenceStatus.PUBLIC_COMPANY_CLAIM, source_name="Acme", source_type="company_website", source_url="https://example.com", confidence=70)
    assert evidence.status == EvidenceStatus.PUBLIC_COMPANY_CLAIM
    assert evidence.source_url == "https://example.com"
    assert evidence.status != EvidenceStatus.FOUNDER_PROVIDED


def test_deterministic_scoring_is_bounded_and_explainable():
    context = {"website_research": {"status": "supported", "url": "https://example.com", "description": "Product"}, "github": {"status": "available", "recent_commit_count": 2, "contributor_count": 3, "release_count": 1, "language": "Python", "open_issues_count": 500}, "finance_mcp": {"arpu": 100}, "financial_inputs": {"monthly_revenue": 1000, "monthly_burn": 500, "cash_available": 5000, "customers": 2}}
    scores = calculate_score_breakdowns(context)
    assert len(scores) == 5
    assert all(0 <= score.score <= 100 and score.evidence_summary for score in scores)
    technology = next(score for score in scores if score.category == "Technology")
    assert any("classification" in item.label.lower() for item in technology.deductions)


def test_missing_financial_data_reduces_confidence_and_recommendation_is_reasoned():
    context = {"website_research": {"status": "unavailable"}, "github": {"status": "unavailable"}, "finance_mcp": {"status": "unavailable"}, "financial_inputs": {}}
    scores = calculate_score_breakdowns(context)
    financial = next(score for score in scores if score.category == "Financials")
    recommendation, _risk, reason, _overall, confidence = recommendation_for(scores, unavailable_count=3)
    assert financial.confidence == "Low"
    assert reason and confidence == "Low"
    assert recommendation in Recommendation


def test_pdf_contains_printable_header_timestamp_and_full_sections():
    report = DueDiligenceReport(company_name="Acme", sector="SaaS", funding_stage="Seed", overall_score=50, market_score=50, technical_score=50, traction_score=50, financial_score=50, team_score=50, risk_level=RiskLevel.MODERATE, confidence_level="Low", investment_thesis="Long thesis " * 100, strengths=["Strength " * 20], red_flags=["Risk " * 20], verified_evidence=[], unverified_claims=[], investor_questions=["Question " * 40], additional_verification_required=[], recommendation=Recommendation.VERIFY)
    payload = render_report_pdf(report)
    assert payload.startswith(b"%PDF")
    from pypdf import PdfReader
    reader = PdfReader(BytesIO(payload))
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert "DealLens AI - Investment Memo" in text
    assert "Decision support only - not investment advice." in text
    assert "Market: 50 / 100" not in text or len(reader.pages) >= 1
    assert "? Investment Memo" not in text


def test_crewai_strict_report_schema_is_internally_consistent():
    schema = crewai_strict_schema(DueDiligenceReport)
    assert "agent_status" not in schema["properties"]
    assert "agent_status" not in schema["required"]


def test_schema_validator_rejects_phantom_required_key():
    with pytest.raises(StructuredOutputSchemaError):
        validate_strict_schema({"type": "object", "properties": {}, "required": ["agent_status"], "additionalProperties": False})


def test_case_becomes_terminal_failed_on_schema_error(monkeypatch):
    from backend.tests.test_persistence import manager
    manager = manager()
    manager.settings = settings_without_key()
    record = manager.create(valid_case())
    def fail(*_args, **_kwargs):
        raise StructuredOutputSchemaError("bad schema")
    monkeypatch.setattr("backend.services.cases.DueDiligenceFlow.run", fail)
    manager.run(record.status.case_id)
    status = manager.get(record.status.case_id).status
    assert status.status == "failed"
    assert status.errors == ["STRUCTURED_OUTPUT_SCHEMA_ERROR"]
    assert status.completion_percentage == 100


def test_openai_invalid_schema_response_is_terminal_and_not_generic():
    assert CaseManager._safe_error_code(RuntimeError("OpenAI 400 Invalid schema for response_format")) == "STRUCTURED_OUTPUT_SCHEMA_ERROR"


def test_terminal_failed_status_is_exposed_safely():
    from backend.tests.test_persistence import manager
    manager = manager()
    record = manager.create(valid_case())
    record.status.status = "failed"
    record.status.current_stage = "failed"
    record.status.errors = ["STRUCTURED_OUTPUT_SCHEMA_ERROR"]
    assert manager.get(record.status.case_id).status.model_dump()["errors"] == ["STRUCTURED_OUTPUT_SCHEMA_ERROR"]


def test_case_status_and_report_endpoints(monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr("backend.api.routes.get_settings", settings_without_key)
    from backend.tests.test_persistence import manager
    isolated_manager = manager()
    monkeypatch.setattr("backend.api.routes.get_case_manager", lambda _settings: isolated_manager)
    response = client.post("/api/cases", json=valid_case().model_dump(mode="json"))
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "OPENAI_CONFIGURATION_ERROR"

    record = isolated_manager.create(valid_case())
    status_response = client.get(f"/api/cases/{record.status.case_id}/status")
    report_response = client.get(f"/api/cases/{record.status.case_id}/report")
    assert status_response.status_code == 200
    assert report_response.status_code == 202


def test_status_unknown_case_is_404():
    from backend.tests.test_persistence import manager
    from unittest.mock import patch
    with patch("backend.api.routes.get_case_manager", lambda _settings: manager()):
        assert TestClient(app).get("/api/cases/missing/status").status_code == 404
