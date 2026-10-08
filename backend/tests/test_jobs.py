"""Scoring-job queue: claim, complete, fail, lease takeover, and a multi-process proof. Runs on SQLite, and on PostgreSQL with --postgres."""
import json
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session as Db

import harness
from app.db import models as m
from app.db.engine import init_db, make_engine
from app.services.jobs import claim_next_job, complete_job, fail_job

ROOT = Path(__file__).resolve().parents[2]
T0 = datetime(2026, 10, 12, 6, 0, tzinfo=timezone.utc)


def secs(n):
    return T0 + timedelta(seconds=n)


@pytest.fixture()
def db(tmp_path):
    engine = make_engine(harness.db_url_for(tmp_path))
    init_db(engine)
    with Db(engine) as session:
        session.add(m.Viva(id="v", title="t", subject="s", topics=["a"], difficulty="easy", rules_version="rules-v1", config={}, created_by="x"))
        session.commit()
        yield session


def add_jobs(db, n, run_after=None, status="queued", first=0):
    db.add_all([m.RosterEntry(viva_id="v", student_id=f"S{first + i}") for i in range(n)])
    db.commit()
    sessions = [m.Session(id=uuid.uuid4(), viva_id="v", student_id=f"S{first + i}", status="ended") for i in range(n)]
    db.add_all(sessions)
    db.commit()
    jobs = [m.Job(session_id=s.id, kind="score", status=status, run_after=(run_after[i] if run_after else T0)) for i, s in enumerate(sessions)]
    db.add_all(jobs)
    db.commit()
    return [j.id for j in jobs]


def test_claims_in_due_order_and_records_the_owner(db):
    ids = add_jobs(db, 3, run_after=[secs(30), secs(10), secs(20)])
    first = claim_next_job(db, "w1", secs(60))
    assert first.id == ids[1], "the job that became due first goes first"
    assert (first.status, first.locked_by, first.attempts) == ("running", "w1", 1) and first.locked_at == secs(60)
    assert [claim_next_job(db, "w1", secs(60)).id for _ in range(2)] == [ids[2], ids[0]]
    assert claim_next_job(db, "w1", secs(60)) is None


def test_a_job_that_is_not_due_yet_is_left_alone(db):
    add_jobs(db, 1, run_after=[secs(100)])
    assert claim_next_job(db, "w1", secs(50)) is None
    assert claim_next_job(db, "w1", secs(100)) is not None


def test_a_held_job_is_not_given_to_a_second_worker_until_its_lease_expires(db):
    (job_id,) = add_jobs(db, 1)
    assert claim_next_job(db, "w1", secs(0), lease_seconds=300).id == job_id
    assert claim_next_job(db, "w2", secs(299), lease_seconds=300) is None
    taken = claim_next_job(db, "w2", secs(301), lease_seconds=300)
    assert taken.id == job_id and taken.locked_by == "w2" and taken.attempts == 2, "a dead worker's job is taken over"
    assert complete_job(db, job_id, "w1", secs(302)) is False, "the old owner can no longer finish it"
    assert complete_job(db, job_id, "w2", secs(303)) is True
    assert db.get(m.Job, job_id).status == "done" and claim_next_job(db, "w3", secs(9999)) is None


def add_jobs_after(db, n):
    return add_jobs(db, n, first=100)


def test_other_kinds_and_finished_jobs_are_never_claimed(db):
    (a,) = add_jobs(db, 1)
    db.get(m.Job, a).kind = "other"
    db.commit()
    assert claim_next_job(db, "w", secs(1)) is None, "only kind=score is this queue's business"
    (b,) = add_jobs_after(db, 1)
    db.get(m.Job, b).status = "done"
    db.commit()
    assert claim_next_job(db, "w", secs(1)) is None


def test_a_failure_requeues_with_a_growing_delay_then_gives_up(db):
    (job_id,) = add_jobs(db, 1)
    now = 0
    for attempt in (1, 2):
        job = claim_next_job(db, "w", secs(now))
        assert job.attempts == attempt
        assert fail_job(db, job_id, "w", secs(now), "provider down", max_attempts=3, backoff_seconds=30) == "queued"
        j = db.get(m.Job, job_id)
        assert j.error == "provider down" and j.locked_by is None and j.run_after == secs(now) + timedelta(seconds=30 * attempt)
        assert claim_next_job(db, "w", secs(now + 29 * attempt)) is None, "not before the delay is over"
        now += 30 * attempt
    assert claim_next_job(db, "w", secs(now)).attempts == 3
    assert fail_job(db, job_id, "w", secs(now), "still down", max_attempts=3) == "failed"
    assert claim_next_job(db, "w", secs(10_000)) is None, "a failed job is not retried by the queue"
    assert fail_job(db, job_id, "someone-else", secs(now), "x") is None


def test_two_database_sessions_never_get_the_same_job(db):
    ids = add_jobs(db, 6)
    other = Db(db.get_bind())
    try:
        got = []
        for _ in range(3):
            got += [claim_next_job(db, "a", secs(1)).id, claim_next_job(other, "b", secs(1)).id]
        assert sorted(got) == sorted(ids) and len(set(got)) == 6
    finally:
        other.close()


def test_a_viva_that_ends_through_the_api_leaves_exactly_one_job_a_worker_can_claim(tmp_path):
    """The T2b enqueue (same transaction as 'ended') and this claim agree: end a session, claim its job once, finish it, and a rescore queues it again."""
    app, client, clock = harness.build(tmp_path)
    codes = harness.make_viva(client, students=("S1",))
    sid, _ = harness.ended_session(client, clock, codes)
    with app.state.sessionmaker() as session:
        job = claim_next_job(session, "worker-1", clock())
        assert job is not None and str(job.session_id) == sid and job.kind == "score" and job.attempts == 1
        assert claim_next_job(session, "worker-2", clock()) is None, "one session, one job"
        job_id = job.id
        assert complete_job(session, job_id, "worker-1", clock())
    harness.mark_scored(app, sid)
    assert client.post(f"/faculty/sessions/{sid}/rescore", headers=harness.RAO).status_code == 202
    with app.state.sessionmaker() as session:
        again = claim_next_job(session, "worker-2", clock())
        assert again is not None and again.id == job_id and again.attempts == 1, "rescore resets the same job row"


def run_proof(url, jobs, workers):
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "prove_job_claim.py"), "--db", url, "--jobs", str(jobs), "--workers", str(workers),
                          "--work-ms", "2"], capture_output=True, text=True, env={"PATH": "/usr/bin:/bin", "HOME": str(Path.home()), "AI_VIVA_NO_DOTENV": "1"})
    return json.loads(out.stdout.strip().splitlines()[-1]), out


def test_competing_os_processes_never_claim_the_same_job(tmp_path):
    url = harness.PG_BASE or f"sqlite:///{tmp_path / 'proof.db'}"
    summary, out = run_proof(url, jobs=200, workers=4)
    assert out.returncode == 0, out.stderr[-500:]
    assert summary["ok"] and summary["claims"] == 200 and summary["duplicate_claims"] == 0 and summary["lost_jobs"] == 0
    assert summary["final_status"] == {"done": 200} and summary["attempts_histogram"] == {"1": 200}
    assert sum(1 for n in summary["per_worker"].values() if n > 0) >= 2, "the work really was shared between processes"
    assert summary["dialect"] == ("postgresql" if harness.PG_BASE else "sqlite")
