from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from socket import gethostname
from uuid import uuid4

from backend.config import Settings
from backend.persistence.database import connection


@dataclass
class Job:
    job_id: str
    case_id: str
    status: str
    current_stage: str
    attempts: int
    max_attempts: int


class JobRepository:
    def __init__(self, settings: Settings): self.settings = settings

    def enqueue(self, case_id: str) -> Job:
        job_id = str(uuid4())
        with connection(self.settings) as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO deallens_jobs (job_id,case_id,status,current_stage,max_attempts) VALUES (%s,%s,'queued','validating',%s)", (job_id, case_id, self.settings.job_max_attempts))
        return Job(job_id, case_id, "queued", "validating", 0, self.settings.job_max_attempts)

    def claim_next(self, worker_id: str | None = None) -> Job | None:
        worker_id = worker_id or f"{gethostname()}:{id(self)}"
        with connection(self.settings) as conn:
            with conn.cursor() as cur:
                cur.execute("""WITH candidate AS (SELECT job_id FROM deallens_jobs WHERE status IN ('queued','retry_pending') AND attempts < max_attempts ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1) UPDATE deallens_jobs j SET status='running', attempts=j.attempts+1, locked_at=NOW(), locked_by=%s, started_at=COALESCE(j.started_at,NOW()), updated_at=NOW() FROM candidate WHERE j.job_id=candidate.job_id RETURNING j.*""", (worker_id,))
                row = cur.fetchone()
        return Job(str(row["job_id"]), str(row["case_id"]), row["status"], row["current_stage"], row["attempts"], row["max_attempts"]) if row else None

    def update_stage(self, job_id: str, stage: str) -> None:
        with connection(self.settings) as conn:
            with conn.cursor() as cur: cur.execute("UPDATE deallens_jobs SET current_stage=%s,updated_at=NOW() WHERE job_id=%s AND status='running'", (stage, job_id))

    def complete(self, job_id: str) -> None:
        with connection(self.settings) as conn:
            with conn.cursor() as cur: cur.execute("UPDATE deallens_jobs SET status='completed', current_stage='completed', completed_at=NOW(), updated_at=NOW(), locked_at=NULL WHERE job_id=%s", (job_id,))

    def fail(self, job: Job, error_code: str, retryable: bool) -> str:
        next_status = "retry_pending" if retryable and job.attempts < job.max_attempts else "failed"
        with connection(self.settings) as conn:
            with conn.cursor() as cur: cur.execute("UPDATE deallens_jobs SET status=%s,error_code=%s,error_message='The due-diligence workflow could not complete.',locked_at=NULL,locked_by=NULL,completed_at=CASE WHEN %s='failed' THEN NOW() ELSE NULL END,updated_at=NOW() WHERE job_id=%s", (next_status,error_code,next_status,job.job_id))
        return next_status

    def recover_stale(self) -> int:
        with connection(self.settings) as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE deallens_jobs SET status=CASE WHEN attempts < max_attempts THEN 'retry_pending' ELSE 'interrupted' END, locked_at=NULL, locked_by=NULL, error_code='WORKER_INTERRUPTED', error_message='Worker execution was interrupted; retry is required.', updated_at=NOW(), completed_at=CASE WHEN attempts >= max_attempts THEN NOW() ELSE NULL END WHERE status='running' AND locked_at < NOW() - (%s * INTERVAL '1 minute')", (self.settings.job_stale_minutes,))
                return cur.rowcount
