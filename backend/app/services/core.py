"""Database helpers shared by the student and faculty services. No HTTP here."""
import statistics
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session as Db

from ..api.errors import ApiError, ErrorCode
from ..api.schemas.faculty import DimensionResult, FeedbackLine, RunScore, Scoring
from ..config import VivaConfig, config_from_raw
from ..db import models as m
from ..interviewer import CLOSER
from ..session_state import Event, SessionStatus, transition

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "viva.config.json"
TURN_FIELDS = ("role", "text", "phase", "question_id", "action", "quality")


def viva_config(viva: m.Viva) -> VivaConfig:
    return config_from_raw(viva.config)


def bank_of(db: Db, viva_id: str) -> list:
    rows = db.scalars(select(m.Question).where(m.Question.viva_id == viva_id).order_by(m.Question.id)).all()
    return [{"id": q.id, "topic": q.topic, "type": q.type, "difficulty": q.difficulty, "text": q.text,
             "key_points": list(q.key_points or [])} for q in rows]


def turns_of(db: Db, session_id) -> list:
    return list(db.scalars(select(m.Turn).where(m.Turn.session_id == session_id).order_by(m.Turn.idx)))


def turn_dict(t: m.Turn) -> dict:
    return {k: getattr(t, k) for k in TURN_FIELDS}


def ms_between(later: datetime, earlier: datetime) -> int:
    return int((later - earlier).total_seconds() * 1000)


def remaining_ms(s: m.Session, now: datetime) -> int | None:
    """Milliseconds left on the clock: null before start, 0 once the session is over for any reason."""
    if s.deadline_at is None:
        return None
    if s.status != SessionStatus.in_progress.value:
        return 0
    return max(0, ms_between(s.deadline_at, now))


def enqueue_scoring(db: Db, session_id, now: datetime):
    """One scoring job per session. Enqueueing again (rescore) resets the same row. Caller commits."""
    job = db.scalar(select(m.Job).where(m.Job.session_id == session_id, m.Job.kind == "score"))
    if job is None:
        db.add(m.Job(session_id=session_id, kind="score", status="queued", run_after=now, created_at=now, updated_at=now))
    else:
        job.status, job.attempts, job.error = "queued", 0, None
        job.locked_at = job.locked_by = None
        job.run_after, job.updated_at = now, now


def end_session(db: Db, s: m.Session, at: datetime, now: datetime):
    """in_progress -> ended plus the scoring job. Caller commits, so session and job become visible together."""
    s.status = transition(s.status, Event.end).value
    s.ended_at = at
    s.lease_until = None
    db.flush()
    enqueue_scoring(db, s.id, now)


def expire_session(db: Db, s: m.Session, now: datetime, say_goodbye: bool) -> str | None:
    """The deadline has passed for an in-progress session. If the student is present, store the closing line they are
    shown. Returns the closing text. Caller commits."""
    text = None
    if say_goodbye:
        turns = turns_of(db, s.id)
        last_ai = next((t for t in reversed(turns) if t.role == "ai"), None)
        text = CLOSER
        if not (last_ai and last_ai.action == "close"):
            db.add(m.Turn(session_id=s.id, idx=len(turns), role="ai", text=CLOSER, phase="scoring",
                          question_id=last_ai.question_id if last_ai else None, action="close",
                          prompt_version=viva_config(db.get(m.Viva, s.viva_id)).prompt_version, created_at=now))
    end_session(db, s, min(now, s.deadline_at), now)
    return text


def sweep_expired(db: Db, now: datetime) -> int:
    """End every in-progress session whose deadline has passed (students who left without finishing). Commits."""
    rows = db.scalars(select(m.Session).where(m.Session.status == SessionStatus.in_progress.value,
                                               m.Session.deadline_at <= now)).all()
    for s in rows:
        expire_session(db, s, now, say_goodbye=False)
    db.commit()
    return len(rows)


def need(db: Db, model, key, what: str):
    row = db.get(model, key)
    if row is None:
        raise ApiError(ErrorCode.not_found, f"No such {what}.", {"resource": what})
    return row


# ---------- scores ----------

def aggregate_scores(rows: list, rubric: list):
    """Per-run rows -> (Scoring, low_confidence, reasons) or (None, False, []). The median is taken over runs;
    reason and evidence come from the run holding the median total (as the scorer does)."""
    if not rows:
        return None, False, []
    rows = sorted(rows, key=lambda r: r.run)
    weights = {d["key"]: d["weight"] for d in rubric}

    def total_of(dims):
        return round(sum(weights[k] * float(dims[k]) / 5 for k in weights), 2)

    run_scores = [RunScore(run=r.run, total=r.total if r.total is not None else total_of({k: v["score"] for k, v in r.dims.items()}),
                           dimension_scores={k: int(v["score"]) for k, v in r.dims.items()}) for r in rows]
    rep = sorted(rows, key=lambda r: next(x.total for x in run_scores if x.run == r.run))[len(rows) // 2]
    dims, medians = [], {}
    for key, weight in weights.items():
        scores = [r.dims[key]["score"] for r in rows]
        medians[key] = statistics.median(scores)
        dims.append(DimensionResult(key=key, weight=weight, score=medians[key], score_min=int(min(scores)), score_max=int(max(scores)),
                                    reason=rep.dims[key]["reason"], evidence=list(rep.dims[key].get("evidence", []))))
    totals = [x.total for x in run_scores]
    reasons = []
    for r in rows:
        for why in r.low_confidence_reasons or []:
            if why not in reasons:
                reasons.append(why)
    scoring = Scoring(rubric_version=rep.rubric_version, prompt_version=rep.prompt_version, model=rep.model, runs=run_scores,
                      median_total=total_of(medians), total_spread=round(max(totals) - min(totals), 2), dimensions=dims,
                      feedback=[FeedbackLine(text=f["text"], evidence=list(f.get("evidence", []))) for f in (rep.feedback or [])])
    return scoring, any(r.low_confidence for r in rows), reasons
