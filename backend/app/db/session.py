from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.logging import get_logger
from app.core.settings import settings

logger = get_logger(__name__)

_IS_SQLITE = settings.DATABASE_URL.startswith("sqlite")
_IS_SQLITE_MEMORY = _IS_SQLITE and (
    settings.DATABASE_URL in ("sqlite://", "sqlite:///:memory:") or ":memory:" in settings.DATABASE_URL
)


def _build_engine() -> Engine:
    if _IS_SQLITE:
        kwargs: dict = {"connect_args": {"check_same_thread": False}}
        if _IS_SQLITE_MEMORY:
            kwargs["poolclass"] = StaticPool
        engine = create_engine(settings.DATABASE_URL, **kwargs)

        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine

    return create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )


engine: Engine = _build_engine()

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session that is always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for code running outside a request (workflow nodes, seeding)."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Database transaction rolled back")
        raise
    finally:
        session.close()


def check_connection() -> bool:
    """Returns True when the database answers a trivial query."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.exception("Database connectivity check failed")
        return False
