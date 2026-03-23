from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, scoped_session
from functools import wraps

from prism_inspire.core.config import settings

# ── Primary engine (read-write) ───────────────────────────────────────
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=1800,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
ScopedSession = scoped_session(SessionLocal)

# ── Read replica engine (falls back to primary if not configured) ─────
_replica_url = os.getenv("READ_REPLICA_URL", "")
replica_engine = create_engine(
    _replica_url or settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
) if _replica_url else engine

ReplicaSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=replica_engine)
ReplicaScopedSession = scoped_session(ReplicaSessionLocal)


def with_db(func):
    """
    Decorator that:
      - Creates a new Session on the primary (read-write) database
      - Passes it as the first argument to the wrapped function
      - On exception: rolls back, re-raises
      - Always: closes & removes the session
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        session: Session = ScopedSession()
        try:
            return func(session, *args, **kwargs)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
            ScopedSession.remove()
    return wrapper


def with_read_db(func):
    """
    Decorator for read-only queries routed to the read replica.
    Falls back to the primary database if READ_REPLICA_URL is not set.
    Use this for aggregation queries, reports, and dashboards.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        session: Session = ReplicaScopedSession()
        try:
            return func(session, *args, **kwargs)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
            ReplicaScopedSession.remove()
    return wrapper
