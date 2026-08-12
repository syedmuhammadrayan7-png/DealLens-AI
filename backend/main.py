from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router
from backend.config import get_settings
from backend.persistence.repositories.cases import CaseRepository

app = FastAPI(title="DealLens AI", version="0.1.0", description="Multi-agent startup due-diligence and venture intelligence platform.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().frontend_origin],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.include_router(router)

@app.on_event("startup")
def recover_interrupted_cases() -> None:
    """A restart never silently repeats an expensive CrewAI run."""
    try:
        # API never executes CrewAI; the worker handles stale job recovery.
        pass
    except Exception:
        # Database errors are returned safely by request handlers; do not prevent diagnostics startup.
        pass
