import pytest
from pydantic import ValidationError

from backend.crew.flow import DueDiligenceState
from backend.mcp.clients import DealLensMCPClient
from backend.schemas.case import Evidence, EvidenceStatus, StartupInput
from backend.utils.cache import TTLCache
from backend.utils.retry import PermanentExternalError, retry_external


def test_tool_discovery_includes_mcp_primitives():
    discovery = DealLensMCPClient().discover()[0]
    assert "calculate_runway" in discovery.tools
    assert "deallens://risk-policy" in discovery.resources
    assert "investment_committee_memo" in discovery.prompts


def test_cache_reuses_value():
    calls = 0
    def factory():
        nonlocal calls
        calls += 1
        return calls
    cache = TTLCache(60)
    assert cache.get_or_set("a", factory) == 1
    assert cache.get_or_set("a", factory) == 1
    assert calls == 1


def test_permanent_errors_do_not_retry():
    calls = 0
    def unavailable():
        nonlocal calls
        calls += 1
        raise PermanentExternalError("gone")
    with pytest.raises(PermanentExternalError):
        retry_external(unavailable)
    assert calls == 1


def test_input_validation_and_evidence_labels():
    with pytest.raises(ValidationError):
        StartupInput(company_name="A", sector="AI", funding_stage="Seed")
    evidence = Evidence(statement="Deck says $1m ARR", status=EvidenceStatus.FOUNDER_PROVIDED, confidence=25)
    assert evidence.status == EvidenceStatus.FOUNDER_PROVIDED


def test_flow_is_strictly_bounded():
    flow = DueDiligenceState(case_id="x", company_name="Acme", evidence_quality=0.2)
    assert flow.next_stage() == "targeted_retry"
    flow.iteration = 1
    assert flow.next_stage() == "risk_committee"
