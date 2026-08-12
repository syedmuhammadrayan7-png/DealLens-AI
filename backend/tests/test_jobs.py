from threading import Event

from backend.persistence.repositories.jobs import Job
from backend.services.cases import CaseManager
from backend import worker


def test_permanent_error_is_not_retryable():
    assert not CaseManager._retryable(RuntimeError("OpenAI 400 invalid schema"))


def test_transient_error_is_retryable():
    assert CaseManager._retryable(RuntimeError("temporary connection timeout"))


def test_job_value_carries_bounded_attempts():
    job = Job("j", "c", "queued", "validating", 0, 2)
    assert job.attempts < job.max_attempts


def test_worker_loop_claims_a_queued_job_once(monkeypatch):
    stop_event = Event()
    queued_job = Job("job-1", "case-1", "queued", "validating", 0, 2)

    class Settings:
        worker_poll_seconds = 0

    class Jobs:
        def __init__(self, _settings):
            self.claims = 0
        def recover_stale(self): return 0
        def claim_next(self, _worker_id):
            self.claims += 1
            return queued_job if self.claims == 1 else None

    class Manager:
        def __init__(self): self.runs = []
        def run(self, case_id, job):
            self.runs.append((case_id, job.job_id))
            stop_event.set()

    manager = Manager()
    monkeypatch.setattr(worker, "get_settings", lambda: Settings())
    monkeypatch.setattr(worker, "JobRepository", Jobs)
    monkeypatch.setattr(worker, "get_case_manager", lambda _settings: manager)
    worker.run_worker(stop_event)
    assert manager.runs == [("case-1", "job-1")]
