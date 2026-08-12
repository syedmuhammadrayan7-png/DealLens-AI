from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response

from backend.config import OpenAIConfigurationError, get_settings
from backend.mcp.clients import DealLensMCPClient
from backend.schemas.case import CaseAccepted, CaseStatus, DueDiligenceReport, StartupInput, ToolDiscovery
from backend.services.cases import get_case_manager
from backend.services.pdf import render_report_pdf
from backend.services.pitch_deck import PitchDeckError, extract_pitch_deck
from backend.services.report import static_demo_report

router = APIRouter(prefix="/api", tags=["due-diligence"])


@router.get("/health")
def health() -> dict[str, object]:
    settings = get_settings()
    database = "connected"
    try:
        from backend.persistence.database import connection
        with connection(settings): pass
    except Exception: database = "unavailable"
    return {"status": "ok" if database == "connected" else "degraded", "database": database, "openai_configured": bool(settings.openai_api_key and settings.openai_api_key.get_secret_value()), "model": settings.openai_model}


@router.get("/ready")
def ready() -> dict[str, str]:
    from backend.persistence.database import connection
    try:
        with connection(get_settings()): pass
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable.") from exc
    return {"status": "ready", "database": "connected"}


@router.get("/mcp/discovery", response_model=list[ToolDiscovery])
def mcp_discovery() -> list[ToolDiscovery]:
    return DealLensMCPClient().discover()


@router.get("/cases/demo", response_model=DueDiligenceReport)
def demo_case() -> DueDiligenceReport:
    return static_demo_report()


def _start_case(case: StartupInput, background_tasks: BackgroundTasks) -> CaseAccepted:
    settings = get_settings()
    try:
        settings.require_openai()
    except OpenAIConfigurationError as exc:
        raise HTTPException(status_code=503, detail={"code": "OPENAI_CONFIGURATION_ERROR", "message": str(exc)}) from exc
    manager = get_case_manager(settings)
    record = manager.create(case)
    manager.enqueue(record.status.case_id)
    return CaseAccepted(case_id=record.status.case_id, status="queued", detail="Due diligence workflow queued.")


@router.post("/cases", response_model=CaseAccepted, status_code=status.HTTP_202_ACCEPTED)
def create_case(case: StartupInput, background_tasks: BackgroundTasks) -> CaseAccepted:
    return _start_case(case, background_tasks)


@router.post("/cases/with-pitch-deck", response_model=CaseAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_case_with_pitch_deck(
    background_tasks: BackgroundTasks,
    payload: str = Form(...),
    pitch_deck: UploadFile | None = File(default=None),
) -> CaseAccepted:
    try:
        case = StartupInput.model_validate_json(payload)
        if pitch_deck:
            case.pitch_deck_text = extract_pitch_deck(pitch_deck.filename or "pitch-deck.pdf", pitch_deck.content_type, await pitch_deck.read(), get_settings())
    except PitchDeckError as exc:
        raise HTTPException(status_code=422, detail={"code": "INVALID_PITCH_DECK", "message": str(exc)}) from exc
    return _start_case(case, background_tasks)


@router.get("/cases/{case_id}/status", response_model=CaseStatus)
def case_status(case_id: str) -> CaseStatus:
    record = get_case_manager(get_settings()).get(case_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Case not found.")
    return record.status


@router.get("/cases/{case_id}/report", response_model=DueDiligenceReport)
def case_report(case_id: str) -> DueDiligenceReport:
    record = get_case_manager(get_settings()).get(case_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Case not found.")
    if record.status.status == "failed":
        raise HTTPException(status_code=409, detail="Case failed; no report was generated.")
    if record.report is None:
        raise HTTPException(status_code=202, detail="Report is not ready.")
    return record.report


@router.get("/cases")
def case_history(limit: int = 20, offset: int = 0, status: str | None = None) -> list[dict]:
    limit = max(1, min(limit, 100)); offset = max(0, offset)
    return get_case_manager(get_settings()).repository.list_cases(limit, offset, status)


@router.get("/cases/{case_id}")
def case_detail(case_id: str) -> dict:
    record = get_case_manager(get_settings()).get(case_id)
    if record is None: raise HTTPException(status_code=404, detail="Case not found.")
    return {"case_id": record.status.case_id, "input": record.case.model_dump(mode="json", exclude={"pitch_deck_text"}), "status": record.status, "report_available": record.report is not None, "summary": {"overall_score": record.report.overall_score, "risk_level": record.report.risk_level, "confidence_level": record.report.confidence_level, "recommendation": record.report.recommendation} if record.report else None}


@router.post("/cases/{case_id}/retry", response_model=CaseAccepted, status_code=status.HTTP_202_ACCEPTED)
def retry_case(case_id: str, background_tasks: BackgroundTasks) -> CaseAccepted:
    settings = get_settings(); manager = get_case_manager(settings); record = manager.retry(case_id)
    if record is None: raise HTTPException(status_code=409, detail="Only failed or interrupted cases can be retried.")
    manager.enqueue(record.status.case_id)
    return CaseAccepted(case_id=record.status.case_id, status="queued", detail=f"Retry created from case {case_id}.")


@router.get("/cases/{case_id}/memo.pdf")
def case_memo_pdf(case_id: str) -> Response:
    report = case_report(case_id)
    return Response(content=render_report_pdf(report), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="deallens-{case_id}.pdf"'})
