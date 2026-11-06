"""
Database configuration and session management for Web Data Forge.
Configures SQLAlchemy engine and thread-safe session factories.
"""

from contextlib import contextmanager
import os
from pathlib import Path
from typing import Generator, Optional
from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

DEFAULT_DB_URL = "sqlite:///./data/web_data_forge.db"

Base = declarative_base()


def get_database_url() -> str:
    """Retrieve database URL from environment or fallback to local SQLite default."""
    return os.environ.get("DATABASE_URL", DEFAULT_DB_URL)


def ensure_sqlite_dir_exists(db_url: str) -> None:
    """Ensure parent directory exists when using SQLite."""
    if db_url.startswith("sqlite:///") and not db_url.startswith("sqlite:///:memory:"):
        db_path = db_url.replace("sqlite:///", "")
        parent = Path(db_path).parent
        if parent and not parent.exists():
            parent.mkdir(parents=True, exist_ok=True)


def get_engine(db_url: Optional[str] = None) -> Engine:
    """Create and return a configured SQLAlchemy Engine."""
    url = db_url or get_database_url()
    ensure_sqlite_dir_exists(url)

    connect_args = {}
    if url.startswith("sqlite:"):
        connect_args["check_same_thread"] = False

    return create_engine(url, connect_args=connect_args)


def init_db(engine: Optional[Engine] = None) -> None:
    """Initialize database tables according to defined ORM models."""
    eng = engine or get_engine()
    Base.metadata.create_all(bind=eng)


@contextmanager
def get_db_session(db_url: Optional[str] = None, engine: Optional[Engine] = None) -> Generator[Session, None, None]:
    """
    Context manager providing a transactional database session.
    Commits on success, rolls back on exception, and closes on exit.
    """
    eng = engine or get_engine(db_url)
    session_factory = sessionmaker(bind=eng, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
