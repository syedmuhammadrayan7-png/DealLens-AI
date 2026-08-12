"""HTTP wrapper for running the durable DealLens worker on Render Web Services.

Run with ``python -m backend.worker_service``.  The HTTP server exists only to
meet hosts that require a listening port; durable job claiming remains in
``backend.worker``.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from threading import Event, Thread
from typing import Callable

import uvicorn
from fastapi import FastAPI

from backend.worker import run_worker

logger = logging.getLogger("deallens.worker_service")
LOCAL_PORT_DEFAULT = 10000
SHUTDOWN_WAIT_SECONDS = 10


def configured_port() -> int:
    """Read Render's port with a useful, valid default for local execution."""
    raw_port = os.getenv("PORT", str(LOCAL_PORT_DEFAULT))
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise RuntimeError("PORT must be a valid TCP port number.") from exc
    if not 1 <= port <= 65535:
        raise RuntimeError("PORT must be between 1 and 65535.")
    return port


def create_worker_app(worker_loop: Callable[[Event], None] = run_worker) -> FastAPI:
    """Create the tiny health app and run the existing worker beside it."""
    stop_event = Event()
    worker_thread: Thread | None = None

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        nonlocal worker_thread
        stop_event.clear()
        worker_thread = Thread(
            target=worker_loop,
            args=(stop_event,),
            name="deallens-postgres-worker",
            # Render can end the process after its shutdown grace period.  A
            # daemon thread lets Uvicorn exit then; the durable running job is
            # deliberately left for stale-job recovery instead of being
            # falsely completed during process teardown.
            daemon=True,
        )
        worker_thread.start()
        logger.info("DealLens worker web service started")
        try:
            yield
        finally:
            # Do not complete or alter an active job here.  If Render stops the
            # process while CrewAI is running, its durable running job remains
            # recoverable by the existing stale-job recovery policy.
            stop_event.set()
            if worker_thread is not None:
                worker_thread.join(timeout=SHUTDOWN_WAIT_SECONDS)
                if worker_thread.is_alive():
                    logger.warning("Worker is still finishing an active job; it remains recoverable after shutdown.")
            logger.info("DealLens worker web service stopped")

    app = FastAPI(title="DealLens AI Worker", version="0.1.0", lifespan=lifespan)

    @app.get("/")
    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "deallens-worker"}

    return app


app = create_worker_app()


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=configured_port())


if __name__ == "__main__":
    main()
