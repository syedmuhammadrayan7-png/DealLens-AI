from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class PermanentExternalError(Exception):
    """An error such as invalid URL/404, which must not be retried."""


class ExternalServiceError(Exception):
    pass


def retry_external(operation: Callable[[], T], max_attempts: int = 3, base_delay_seconds: float = 0.15) -> T:
    last_error: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return operation()
        except PermanentExternalError:
            raise
        except Exception as exc:
            last_error = exc
            if attempt < max_attempts - 1:
                time.sleep(base_delay_seconds * (2 ** attempt))
    raise ExternalServiceError("External service did not respond after the allowed retry limit.") from last_error
