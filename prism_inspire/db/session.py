from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from prism_inspire.core.config import settings
from sqlalchemy.orm import scoped_session
from functools import wraps

#SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL
# For Docker, you might use:
# SQLALCHEMY_DATABASE_URL = "postgresql://user:password@db/mydatabase"
# Ensure this matches the one in alembic.ini for consistency if not using env vars

engine = create_engine(
    settings.DATABASE_URL,
    # connect_args={"check_same_thread": False} # Only for SQLite
    pool_pre_ping=True # Good for production to check connections before use
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
ScopedSession = scoped_session(SessionLocal)
        
        
def with_db(func):
    """
    Decorator that:
      - Creates a new Session (ScopedSession())
      - Passes it as the first argument to the wrapped function
      - On exception: rolls back, re‐raises
      - Always: closes & removes the session
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # 1. Grab a session (equivalent to next(get_db()))
        session: Session = ScopedSession()
        try:
            # 2. Call the original function, injecting `db` as the first positional argument
            return func(session, *args, **kwargs)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
            ScopedSession.remove()
    return wrapper
