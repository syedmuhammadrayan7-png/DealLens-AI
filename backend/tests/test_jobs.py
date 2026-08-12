from backend.persistence.repositories.jobs import Job
from backend.services.cases import CaseManager


def test_permanent_error_is_not_retryable():
    assert not CaseManager._retryable(RuntimeError("OpenAI 400 invalid schema"))


def test_transient_error_is_retryable():
    assert CaseManager._retryable(RuntimeError("temporary connection timeout"))


def test_job_value_carries_bounded_attempts():
    job = Job("j", "c", "queued", "validating", 0, 2)
    assert job.attempts < job.max_attempts
