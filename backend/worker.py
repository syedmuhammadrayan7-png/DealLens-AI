"""PostgreSQL-backed worker: `python -m backend.worker`."""
from __future__ import annotations

import logging
import signal
import time
from socket import gethostname
from threading import Event, current_thread, main_thread

from backend.config import get_settings
from backend.persistence.repositories.jobs import JobRepository
from backend.services.cases import get_case_manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("deallens.worker")
_shutdown_requested = Event()


def _stop(*_args) -> None:
    """Request a graceful stop after the current job reaches a safe boundary."""
    _shutdown_requested.set()


def run_worker(stop_event: Event | None = None) -> None:
    """Poll and process durable jobs until *stop_event* is set.

    The callable is intentionally reusable by ``backend.worker_service``.  Job
    claiming and execution stay here, so a web-service deployment has exactly
    the same PostgreSQL locking semantics as the command-line worker.
    """
    shutdown_event = stop_event or _shutdown_requested
    if stop_event is None:
        _shutdown_requested.clear()
    settings = get_settings()
    jobs = JobRepository(settings)
    manager = get_case_manager(settings)
    worker_id = f"{gethostname()}:deallens-worker"

    # Python only permits signal handlers in the main thread.  The worker web
    # service runs this loop in a thread and manages its Event through FastAPI
    # lifespan instead.
    if current_thread() is main_thread():
        signal.signal(signal.SIGINT, _stop)
        signal.signal(signal.SIGTERM, _stop)
    logger.info("DealLens worker started")
    while not shutdown_event.is_set():
        recovered = jobs.recover_stale()
        if recovered: logger.warning("Recovered %s stale job(s)", recovered)
        job = jobs.claim_next(worker_id)
        if job is None:
            shutdown_event.wait(settings.worker_poll_seconds)
            continue
        logger.info("Claimed job=%s case=%s attempt=%s", job.job_id, job.case_id, job.attempts)
        manager.run(job.case_id, job)
    logger.info("DealLens worker stopped")


if __name__ == "__main__":
    run_worker()
