"""The scoring-job queue (table `jobs`, one job per session, D12). Claiming is a compare-and-set UPDATE that works on SQLite and
PostgreSQL; on PostgreSQL the candidate is picked with FOR UPDATE SKIP LOCKED so concurrent workers do not queue up behind the same row.
A worker that dies leaves a `running` job behind: once its lock is older than the lease another worker takes it over.
Callers pass `now` (timezone-aware UTC) so tests control the clock."""
from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session as Db

from ..db import models as m

DEFAULT_LEASE_S = 300


def _runnable(now: datetime, stale_before: datetime):
    return or_(and_(m.Job.status == "queued", m.Job.run_after <= now), and_(m.Job.status == "running", m.Job.locked_at < stale_before))


def claim_next_job(db: Db, worker_id: str, now: datetime, *, kind: str = "score", lease_seconds: int = DEFAULT_LEASE_S, tries: int = 8):
    """Claim the next runnable job for `worker_id` or return None. Runnable: queued and due, or running with a lock older than the lease.
    Sets status running, locked_at, locked_by and attempts + 1. Never returns a job another worker holds."""
    stale_before = now - timedelta(seconds=lease_seconds)
    postgres = db.get_bind().dialect.name == "postgresql"
    for _ in range(tries):
        pick = select(m.Job.id).where(m.Job.kind == kind, _runnable(now, stale_before)).order_by(m.Job.run_after, m.Job.id).limit(1)
        if postgres:
            pick = pick.with_for_update(skip_locked=True)
        job_id = db.execute(pick).scalar()
        if job_id is None:
            db.rollback()
            return None
        won = db.execute(update(m.Job).where(m.Job.id == job_id, _runnable(now, stale_before))
                         .values(status="running", locked_at=now, locked_by=worker_id, attempts=m.Job.attempts + 1, updated_at=now))
        db.commit()
        if won.rowcount == 1:
            return db.get(m.Job, job_id)
        # someone else took that row between our pick and our update (SQLite has no row locks): look at the next one
    return None


def complete_job(db: Db, job_id: int, worker_id: str, now: datetime) -> bool:
    """Mark a job done. Only the worker that holds it can; False otherwise (its lease expired and someone else took over)."""
    done = db.execute(update(m.Job).where(m.Job.id == job_id, m.Job.status == "running", m.Job.locked_by == worker_id)
                      .values(status="done", error=None, updated_at=now))
    db.commit()
    return done.rowcount == 1


def fail_job(db: Db, job_id: int, worker_id: str, now: datetime, error: str, *, max_attempts: int = 3, backoff_seconds: int = 30):
    """Release a job after a failure: back to queued with a growing delay, or failed once max_attempts is reached.
    -> the new status, or None if this worker no longer holds the job."""
    job = db.get(m.Job, job_id)
    if job is None or job.status != "running" or job.locked_by != worker_id:
        db.rollback()
        return None
    status = "failed" if job.attempts >= max_attempts else "queued"
    run_after = now if status == "failed" else now + timedelta(seconds=backoff_seconds * job.attempts)
    db.execute(update(m.Job).where(m.Job.id == job_id, m.Job.locked_by == worker_id)
               .values(status=status, error=error[:1000], run_after=run_after, locked_at=None, locked_by=None, updated_at=now))
    db.commit()
    return status
