import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.schema import CreateIndex, CreateTable

from app.api.schemas import faculty
from app.db import models as m
from app.db.ddl import postgres_ddl
from app.db.engine import init_db, make_engine
from app.session_state import SessionStatus
from harness import db_url_for

ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]
TABLES = {"vivas", "questions", "roster", "access_codes", "sessions", "turns", "scores", "overrides",
          "reviews", "integrity_events", "jobs"}
NOW = datetime(2026, 10, 12, 5, 30, 12, tzinfo=timezone.utc)


@pytest.fixture()
def engine(tmp_path):
    e = make_engine(db_url_for(tmp_path))
    init_db(e)
    return e


@pytest.fixture()
def db(engine):
    with DbSession(engine) as s:
        s.add(m.Viva(id="v1", title="t", subject="s", topics=["a"], difficulty="easy", rules_version="rules-v1",
                     config={"duration_ms": 900000}, created_by="dr-rao"))
        s.commit()  # no relationship() is declared, so the ORM does not order parents before children: commit them
        s.add(m.RosterEntry(viva_id="v1", student_id="S1", name="Asha"))
        s.commit()
        yield s


def new_session(**kw):
    return m.Session(viva_id="v1", student_id="S1", **kw)


def saved_session(db, **kw):
    s = new_session(**kw)
    db.add(s)
    db.commit()
    return s


def test_sqlite_create_all_makes_every_table(engine):
    assert set(inspect(engine).get_table_names()) == TABLES


def test_ddl_compiles_for_postgresql_without_a_server():
    dialect = postgresql.dialect()
    for table in m.Base.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(dialect=dialect))
        assert ddl.startswith("\nCREATE TABLE " + table.name)
        for index in table.indexes:
            assert "CREATE" in str(CreateIndex(index).compile(dialect=dialect))
    full = postgres_ddl()
    for needed in ("JSONB", "UUID", "TIMESTAMP WITH TIME ZONE", "SERIAL", "NUMERIC(5, 2)",
                   "WHERE revoked_at IS NULL"):
        assert needed in full, needed
    assert "DATETIME" not in full and "WITHOUT TIME ZONE" not in full
    assert {t for t in TABLES if f"CREATE TABLE {t} " in full} == TABLES


def test_committed_schema_sql_matches_the_models():
    assert (ROOT / "db" / "schema.sql").read_text() == postgres_ddl(), "run python scripts/export_schema.py"


def test_round_trip_keeps_uuid_json_and_utc(db):
    s = saved_session(db, started_at=NOW, deadline_at=NOW + timedelta(minutes=15))
    db.add(m.Turn(session_id=s.id, idx=0, role="ai", text="hi", meta={"classify_error": "boom"}))
    db.commit()
    db.expire_all()
    got = db.get(m.Session, s.id)
    assert isinstance(got.id, uuid.UUID) and got.status == "created"
    assert got.started_at == NOW and got.started_at.tzinfo is not None
    assert got.deadline_at - got.started_at == timedelta(minutes=15)
    assert db.get(m.Viva, "v1").topics == ["a"] and db.get(m.Turn, (s.id, 0)).meta == {"classify_error": "boom"}
    assert got.consent_at is None  # a session exists before consent


def test_other_timezones_are_stored_as_utc_and_naive_is_refused(db):
    ist = timezone(timedelta(hours=5, minutes=30))
    s = saved_session(db, started_at=datetime(2026, 10, 12, 11, 0, tzinfo=ist))
    db.expire_all()
    assert db.get(m.Session, s.id).started_at == datetime(2026, 10, 12, 5, 30, tzinfo=timezone.utc)
    db.add(m.Override(session_id=s.id, reviewer="r", new_total=1, reason="x", at=datetime(2026, 1, 1)))
    with pytest.raises(Exception, match="naive datetime"):
        db.commit()


def test_none_json_is_sql_null(db):
    s = saved_session(db)
    db.add(m.Turn(session_id=s.id, idx=0, role="ai", text="hi"))
    db.commit()
    assert db.execute(text("SELECT meta IS NULL FROM turns")).scalar() == 1


def test_foreign_keys_are_enforced_on_sqlite(db):
    db.add(m.Session(viva_id="v1", student_id="not-on-roster"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_one_session_per_student_per_viva(db):
    db.add_all([new_session(), new_session()])
    with pytest.raises(IntegrityError):
        db.commit()


def test_client_seq_is_unique_per_session_but_null_repeats(db):
    s = saved_session(db)
    db.add_all([m.Turn(session_id=s.id, idx=i, role="ai", text="x") for i in range(3)])  # null client_seq: fine
    db.commit()
    db.add_all([m.Turn(session_id=s.id, idx=3, role="student", text="a", client_seq=1),
                m.Turn(session_id=s.id, idx=4, role="student", text="b", client_seq=1)])
    with pytest.raises(IntegrityError):
        db.commit()


def test_check_constraints(db):
    db.add(new_session(status="nonsense"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    s = saved_session(db)
    db.add(m.Turn(session_id=s.id, idx=0, role="system", text="x"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(m.Job(session_id=s.id, status="weird"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_status_check_matches_the_state_machine(db):
    for status in SessionStatus:
        db.add(m.RosterEntry(viva_id="v1", student_id=f"S-{status.value}"))
    db.commit()
    for status in SessionStatus:
        db.add(m.Session(viva_id="v1", student_id=f"S-{status.value}", status=status.value))
    db.commit()
    assert db.scalar(select(m.Session).where(m.Session.status == "in_progress")) is not None


def test_only_one_active_access_code_per_student(db):
    db.add(m.AccessCode(viva_id="v1", student_id="S1", code_hash="h1"))
    db.commit()
    db.add(m.AccessCode(viva_id="v1", student_id="S1", code_hash="h2"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    old = db.scalar(select(m.AccessCode))
    old.revoked_at = NOW
    db.add(m.AccessCode(viva_id="v1", student_id="S1", code_hash="h2"))
    db.commit()
    assert db.query(m.AccessCode).count() == 2


def test_job_queue_columns_and_defaults(db):
    s = saved_session(db)
    job = m.Job(session_id=s.id)
    db.add(job)
    db.commit()
    db.refresh(job)
    assert (job.kind, job.status, job.attempts) == ("score", "queued", 0)
    assert job.locked_at is None and job.locked_by is None and job.error is None
    assert job.run_after.tzinfo is not None
    db.add(m.Job(session_id=s.id))  # second job for the same session and kind
    with pytest.raises(IntegrityError):
        db.commit()


def test_overrides_keep_history_in_id_order(db):
    s = saved_session(db)
    for total in (60, 70, 80):
        db.add(m.Override(session_id=s.id, reviewer="dr-rao", old_total=50, new_total=total, reason="because"))
    db.commit()
    latest = db.scalar(select(m.Override).where(m.Override.session_id == s.id).order_by(m.Override.id.desc()))
    assert latest.new_total == 80.0


@pytest.mark.parametrize("api_model,table,derived", [
    (faculty.Turn, m.Turn, set()),
    (faculty.OverrideEntry, m.Override, set()),
    (faculty.IntegrityEvent, m.IntegrityEvent, set()),
    (faculty.Question, m.Question, set()),
    (faculty.Viva, m.Viva, {"question_count", "roster_count", "session_counts"}),
])
def test_every_contract_field_has_a_column(api_model, table, derived):
    columns = {c.key for c in inspect(table).columns}
    missing = set(api_model.model_fields) - columns - derived
    assert not missing, f"{api_model.__name__} fields without a column in {table.__tablename__}: {missing}"


@pytest.mark.sqlite_only
def test_make_engine_reads_database_url(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'x.db'}")
    e = make_engine()
    assert str(e.url).endswith("x.db")
    with e.connect() as c:
        assert c.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_the_suite_runs_on_the_database_it_claims_to(engine):
    """Guards against a --postgres run that quietly used SQLite: the dialect, the per-test schema and the real column types are checked."""
    import harness
    expected = "postgresql" if harness.PG_BASE else "sqlite"
    assert engine.dialect.name == expected
    with engine.connect() as c:
        if expected == "postgresql":
            schema = c.execute(text("select current_schema()")).scalar()
            assert schema.startswith("t_"), "every test gets a schema of its own"
            kinds = dict(c.execute(text("select column_name, data_type from information_schema.columns where table_schema = current_schema() "
                                        "and ((table_name='sessions' and column_name in ('id','started_at')) or (table_name='vivas' and column_name='topics'))")).all())
            assert kinds == {"id": "uuid", "started_at": "timestamp with time zone", "topics": "jsonb"}
            assert c.execute(text("select count(*) from pg_indexes where schemaname = current_schema() and indexdef like '%WHERE (revoked_at IS NULL)%'")).scalar() == 1


def test_the_postgres_pool_is_at_least_as_big_as_the_request_thread_pool(monkeypatch):
    """A pool smaller than FastAPI's 40 worker threads can deadlock: waiting requests use every thread, so no thread is left to close a
    session and return a connection (found by the T7 load test)."""
    from app.db.engine import make_engine
    monkeypatch.delenv("DB_POOL_SIZE", raising=False)
    monkeypatch.delenv("DB_MAX_OVERFLOW", raising=False)
    engine = make_engine("postgresql+psycopg://u@localhost/none")  # lazy: no connection is made
    assert engine.pool.size() + engine.pool._max_overflow >= 40 + 12
    monkeypatch.setenv("DB_POOL_SIZE", "3")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "4")
    small = make_engine("postgresql+psycopg://u@localhost/none")
    assert small.pool.size() == 3 and small.pool._max_overflow == 4


def test_the_request_database_session_is_closed_on_the_event_loop_not_in_a_worker_thread():
    import inspect
    from app.api.deps import get_db
    assert inspect.isasyncgenfunction(get_db)


def test_a_service_call_gives_its_connection_back_before_the_response_is_built():
    """The deadlock found by the load test: the connection used to stay held until the response had been validated in a worker."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from app.api.deps import ReleaseAfterCall

    class Ops:
        label = "ops"

        def __init__(self, db):
            self.db = db

        def read(self):
            return self.db.execute(text("select 1")).scalar()

        def broken(self):
            self.db.execute(text("select 1"))
            raise ValueError("boom")

    db = sessionmaker(create_engine("sqlite://"))()
    ops = ReleaseAfterCall(Ops(db), db)
    assert ops.read() == 1 and not db.in_transaction()
    assert ops.label == "ops"
    with pytest.raises(ValueError):
        ops.broken()
    assert not db.in_transaction()
