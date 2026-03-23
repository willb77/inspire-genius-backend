from __future__ import annotations

"""
Query optimization utilities — index recommendations, N+1 detection,
pagination helpers, and slow-query logging.
"""

import logging
import time
from contextlib import contextmanager
from typing import Any, Generator

from sqlalchemy.orm import Query, joinedload

logger = logging.getLogger(__name__)

# ── Recommended indexes ─────────────────────────────────────────────────
# Mapping of index name → (table, columns) for all recommended indexes.
# Used by the Phase 6 migration and for documentation/auditing.
RECOMMENDED_INDEXES: dict[str, tuple[str, list[str]]] = {
    "ix_feedback_user_id": ("feedback", ["user_id"]),
    "ix_feedback_agent_id": ("feedback", ["agent_id"]),
    "ix_feedback_type": ("feedback", ["feedback_type"]),
    "ix_feedback_corrections_status": ("feedback_corrections", ["status"]),
    "ix_prompt_templates_name_version": ("prompt_templates", ["name", "version"]),
    "ix_prompt_templates_status": ("prompt_templates", ["status"]),
    "ix_agent_memories_agent": ("agent_memories", ["agent_id"]),
    "ix_reports_user_status": ("reports", ["user_id", "status"]),
    "ix_export_jobs_user": ("export_jobs", ["user_id"]),
    "ix_users_email": ("users", ["email"]),
}

# ── Pagination ──────────────────────────────────────────────────────────

MAX_PAGE_LIMIT = 100


def paginate(
    query: Query,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[Any], int, bool]:
    """
    Standard offset-based pagination.

    Parameters
    ----------
    query : SQLAlchemy Query
        The base query to paginate.
    page : int
        1-based page number (clamped to >= 1).
    limit : int
        Items per page (clamped to 1..MAX_PAGE_LIMIT).

    Returns
    -------
    (items, total, has_more)
        items     — list of ORM objects for the requested page
        total     — total row count (before pagination)
        has_more  — True if there are additional pages
    """
    page = max(1, page)
    limit = max(1, min(limit, MAX_PAGE_LIMIT))
    offset = (page - 1) * limit

    total: int = query.count()
    items: list[Any] = query.offset(offset).limit(limit).all()
    has_more: bool = (page * limit) < total

    return items, total, has_more


# ── Eager loading helpers ───────────────────────────────────────────────


def eager_load_profile(query: Query) -> Query:
    """
    Add ``joinedload`` for the ``profile`` relationship on a User query
    to prevent N+1 select issues when accessing user profiles in a list.
    """
    return query.options(joinedload("profile"))  # type: ignore[arg-type]


# ── Slow query logging ─────────────────────────────────────────────────

DEFAULT_SLOW_THRESHOLD_MS = 100


def log_slow_query(
    query_name: str,
    duration_ms: float,
    threshold_ms: float = DEFAULT_SLOW_THRESHOLD_MS,
) -> None:
    """Log a warning if *duration_ms* exceeds *threshold_ms*."""
    if duration_ms > threshold_ms:
        logger.warning(
            "Slow query detected: %s took %.1fms (threshold: %.0fms)",
            query_name,
            duration_ms,
            threshold_ms,
        )


@contextmanager
def query_timer(
    name: str,
    threshold_ms: float = DEFAULT_SLOW_THRESHOLD_MS,
) -> Generator[None, None, None]:
    """
    Context manager that times the enclosed block and logs a warning
    if execution time exceeds *threshold_ms*.

    Usage::

        with query_timer("get_user_list"):
            users = session.query(User).all()
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        log_slow_query(name, elapsed_ms, threshold_ms)
