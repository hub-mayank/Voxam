import os

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine

from .models import Base

DEFAULT_URL = "sqlite:///viva_dev.db"


def make_engine(url: str = None) -> Engine:
    """DATABASE_URL, e.g. postgresql+psycopg://user:pw@host/viva. Default: a local SQLite file for dev."""
    engine = create_engine(url or os.environ.get("DATABASE_URL") or DEFAULT_URL)
    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def foreign_keys_on(dbapi_connection, record):  # SQLite ignores foreign keys unless asked
            dbapi_connection.execute("PRAGMA foreign_keys=ON")
    return engine


def init_db(engine: Engine):
    Base.metadata.create_all(engine)
