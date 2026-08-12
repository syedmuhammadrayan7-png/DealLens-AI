"""PostgreSQL-backed worker: `python -m backend.worker`."""
from __future__ import annotations

import logging
import signal
import time
from socket import gethostname

from backend.config import get_settings
from backend.persistence.repositories.jobs import JobRepository
from backend.services.cases import get_case_manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("deallens.worker")
_running = True


def _stop(*_args) -> None:
    global _running
    _running = False


def run_worker() -> None:
    settings = get_settings(); jobs = JobRepository(settings); manager = get_case_manager(settings); worker_id = f"{gethostname()}:deallens-worker"
    signal.signal(signal.SIGINT, _stop); signal.signal(signal.SIGTERM, _stop)
    logger.info("DealLens worker started")
    while _running:
        recovered = jobs.recover_stale()
        if recovered: logger.warning("Recovered %s stale job(s)", recovered)
        job = jobs.claim_next(worker_id)
        if job is None:
            time.sleep(settings.worker_poll_seconds); continue
        logger.info("Claimed job=%s case=%s attempt=%s", job.job_id, job.case_id, job.attempts)
        manager.run(job.case_id, job)
    logger.info("DealLens worker stopped")


if __name__ == "__main__":
    run_worker()
