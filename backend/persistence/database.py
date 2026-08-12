from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator

import psycopg
from psycopg.rows import dict_row

from backend.config import Settings


class PersistenceError(RuntimeError):
    """Safe error boundary; database details never leave the backend logs."""


@contextmanager
def connection(settings: Settings) -> Iterator[psycopg.Connection]:
    try:
        with psycopg.connect(settings.require_database(), connect_timeout=settings.database_connect_timeout_seconds, row_factory=dict_row) as conn:
            yield conn
    except psycopg.Error as exc:
        raise PersistenceError("Database operation could not be completed.") from exc
