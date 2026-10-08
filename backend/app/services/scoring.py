"""Scoring a finished session and storing the result. The worker (app/worker.py) calls `process_next`.

Session status while a job runs: ended (or failed, after a rescore) -> scoring -> scored | failed. A job that is retried leaves the
session in `scoring`; a worker that dies leaves it there too, and the next worker to claim the job carries on. The scores are written
in one transaction together with the session's move to `scored` and the job's completion, so a half-written result never exists:
a rescore replaces the old rows (delete + insert) or changes nothing."""
import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete

from ..db import models as m
from ..llm.budget import CallCapExceeded
from ..scorer import ScoreError, score_session
from ..session_state import Event, SessionStatus, transition
from . import core, jobs
from .views import audio_file

audit = logging.getLogger("aiviva.audit")

MAX_ATTEMPTS = 3
BACKOFF_SECONDS = 30         # a failed attempt waits 30 s, then 60 s: backoff x attempts
BUDGET_WAIT_SECONDS = 300    # a provider that is out of free-tier budget is asked again after this long, without using up an attempt


def events_of(db, s: m.Session) -> tuple[list, bool]:
    """-> (scorer events, audio_missing). Voice sessions are the ones whose turns carry an audio offset."""
    turns = core.turns_of(db, s.id)
    if not turns:
        raise ScoreError("the session has no turns")
    events = core.turns_to_events(turns, s.started_at or turns[0].created_at)
    voice = any(t.t_start_ms is not None for t in turns)
    return events, voice and audio_file(s.audio_uri) is None


def store_scores(db, s: m.Session, result: dict, now: datetime):
    """Replace this session's score rows with `result` (one row per run) and mark it scored. Does not commit."""
    db.execute(delete(m.Score).where(m.Score.session_id == s.id))
    for run, detail in enumerate(result["run_details"], start=1):
        dims = {}
        for key, d in detail["dimensions"].items():
            evidence = list(d.get("evidence", []))
            dims[key] = {"score": d["score"], "reason": d["reason"], "evidence": evidence,
                         "evidence_ms": [result["evidence_offsets_ms"].get(i) for i in evidence]}
        db.add(m.Score(session_id=s.id, run=run, rubric_version=result["rubric_version"], prompt_version=result["scorer_prompt_version"],
                       model=detail["model"], dims=dims, total=detail["total"], run_spread=result["total_spread"],
                       low_confidence=result["low_confidence"], low_confidence_reasons=result["low_confidence_reasons"],
                       feedback=detail["feedback"], created_at=now))
    s.status = transition(s.status, Event.scored).value


def process_next(db, worker_id: str, now: datetime, llm_factory, chain: str | None = None) -> str | None:
    """Claim and run one scoring job. -> what happened: scored, already_scored, retry, deferred, failed, lost, skipped; None if no job was due."""
    job = jobs.claim_next_job(db, worker_id, now)
    if job is None:
        return None
    s = db.get(m.Session, job.session_id)
    if s.status == SessionStatus.scored.value:  # a duplicate job for work that is already done
        return "already_scored" if jobs.complete_job(db, job.id, worker_id, now) else "lost"
    if s.status in (SessionStatus.ended.value, SessionStatus.failed.value):
        s.status = transition(s.status, Event.begin_scoring).value
        db.commit()
    elif s.status != SessionStatus.scoring.value:  # still running or abandoned: nothing to score
        jobs.fail_job(db, job.id, worker_id, now, f"session is {s.status}, not ready to score", max_attempts=1)
        return "skipped"
    viva = db.get(m.Viva, s.viva_id)
    try:
        events, audio_missing = events_of(db, s)
        result = score_session(llm_factory(chain), core.viva_config(viva), events, runs=3, audio_missing=audio_missing)
    except ScoreError as e:
        if isinstance(e.__cause__, CallCapExceeded):  # the scorer wraps it: not tried, so leave the attempt unused and come back later
            jobs.defer_job(db, job.id, worker_id, now, f"waiting for provider budget: {e.__cause__}", delay_seconds=BUDGET_WAIT_SECONDS)
            audit.warning("scoring deferred: session=%s %s", s.id, e.__cause__)
            return "deferred"
        no_answers = "no student turns" in str(e) or "no turns" in str(e)  # retrying cannot help
        return _failed(db, job, s, worker_id, now, str(e), max_attempts=1 if no_answers else MAX_ATTEMPTS)
    except Exception as e:  # a bug or a database hiccup must not kill the worker or loop forever on one job
        audit.exception("scoring crashed: session=%s", s.id)
        db.rollback()
        return _failed(db, job, s, worker_id, now, f"{type(e).__name__}: {e}")
    try:
        store_scores(db, s, result, now)
        if not jobs.complete_job(db, job.id, worker_id, now, commit=False):  # our lease ran out and someone else holds the job: write nothing
            db.rollback()
            return "lost"
        db.commit()
    except Exception as e:  # the old rows (if any) survive: delete + insert are one transaction
        audit.exception("storing scores failed: session=%s", s.id)
        db.rollback()
        return _failed(db, job, s, worker_id, now, f"could not store scores: {type(e).__name__}: {e}")
    audit.info("scored: session=%s total=%s runs=%s model=%s", s.id, result["total"], result["runs"], result["model"])
    return "scored"


def _failed(db, job, s, worker_id, now, error, max_attempts=MAX_ATTEMPTS) -> str:
    status = jobs.fail_job(db, job.id, worker_id, now, error, max_attempts=max_attempts, backoff_seconds=BACKOFF_SECONDS)
    if status == "failed":
        s = db.get(m.Session, s.id)
        s.status = transition(s.status, Event.fail).value
        db.commit()
        audit.error("scoring failed for good: session=%s %s", s.id, error)
        return "failed"
    audit.warning("scoring attempt failed, will retry: session=%s %s", s.id, error)
    return "retry" if status == "queued" else "lost"
