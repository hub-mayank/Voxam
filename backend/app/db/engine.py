import os

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine

from .models import Base

DEFAULT_URL = "sqlite:///viva_dev.db"


def normalise_url(url: str) -> str:
    """postgresql:// and postgres:// mean the psycopg v3 driver here (D17); SQLAlchemy would otherwise look for psycopg2."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def make_engine(url: str = None) -> Engine:
    """DATABASE_URL, e.g. postgresql://user@localhost/viva (or postgresql+psycopg://...). Default: a local SQLite file for dev."""
    url = normalise_url(url or os.environ.get("DATABASE_URL") or DEFAULT_URL)
    if url.startswith("postgresql"):
        # Sync endpoints run in a 40-thread pool and the voice server's blocking calls in a 12-thread executor, each holding at most one
        # connection: a pool of at least 52 means no request ever waits for a connection (the T7 load test first hit a deadlock with
        # a pool of 15, see api/deps.py get_db). Mind PostgreSQL's max_connections (default 100) when running several workers.
        engine = create_engine(url, pool_pre_ping=True, pool_size=int(os.environ.get("DB_POOL_SIZE", 10)),
                               max_overflow=int(os.environ.get("DB_MAX_OVERFLOW", 50)), pool_timeout=float(os.environ.get("DB_POOL_TIMEOUT", 30)))
    else:
        engine = create_engine(url)
    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def sqlite_settings(dbapi_connection, record):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")  # SQLite ignores foreign keys unless asked
            dbapi_connection.execute("PRAGMA busy_timeout=10000")  # wait for a competing writer instead of failing
            if engine.url.database not in (None, "", ":memory:"):
                dbapi_connection.execute("PRAGMA journal_mode=WAL")  # readers do not block the writer
    return engine


def init_db(engine: Engine):
    Base.metadata.create_all(engine)
