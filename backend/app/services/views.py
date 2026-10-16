"""Build API response models from database rows."""
import wave
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session as Db

from ..api.schemas.faculty import (AudioRef, IntegrityEvent, OverrideEntry, PhaseInfo, ReviewEntry, RubricDimension,
                                   Scoring, SessionDetail, SessionSummary, Turn, Viva, VivaConfigView)
from ..db import models as m
from . import core
from .secrets_util import sign_audio

AUDIO_URL_SECONDS = 900
AUDIO_TYPES = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".opus": "audio/ogg", ".webm": "audio/webm",
               ".m4a": "audio/mp4", ".flac": "audio/flac"}  # fixed here: the mimetypes module differs between platforms


def audio_type(path: Path) -> str:
    return AUDIO_TYPES.get(path.suffix.lower(), "application/octet-stream")


@dataclass
class Facts:
    scoring: Scoring | None = None
    low_confidence: bool = False
    reasons: list = field(default_factory=list)
    overrides: list = field(default_factory=list)
    reviews: list = field(default_factory=list)
    scoring_error: str | None = None

    @property
    def effective(self):
        if self.overrides:
            return self.overrides[-1].new_total, "override"
        if self.scoring:
            return self.scoring.median_total, "ai"
        return None, None

    @property
    def needs_review(self):
        return self.low_confidence and not self.overrides and not self.reviews


FAILURE_SENTENCES = (  # (start of the stored job error, what faculty read)
    ("provider failed", "The scoring model was unavailable or over its usage limit."),
    ("scorer failed after retries", "The scoring model returned its answer in the wrong format on every attempt."),
    ("no student turns", "The student gave no answers, so there was nothing to score."),
    ("the session has no turns", "The student gave no answers, so there was nothing to score."),
    ("session is", "The session was not ready to be scored."),
    ("could not store scores", "The scores were produced but could not be saved."),
)
FAILURE_OTHER = "Automatic marking failed for an unexpected reason."


def failure_sentence(error: str | None) -> str:
    """The stored job error is for developers and can quote model output. Faculty get one plain sentence chosen from it."""
    text = (error or "").strip().lower()
    return next((sentence for start, sentence in FAILURE_SENTENCES if text.startswith(start)), FAILURE_OTHER)


def config_view(raw: dict) -> VivaConfigView:
    return VivaConfigView(
        duration_ms=raw["hard_limit_seconds"] * 1000, answer_cap_ms=raw["answer_cap_seconds"] * 1000,
        prompt_version=raw["prompt_version"], rubric_version=raw["rubric"]["version"],
        phases=[PhaseInfo(name=p["name"], start_ms=p["start"] * 1000, end_ms=p["end"] * 1000, max_followups=p["max_followups"])
                for p in raw["phases"]],
        rubric=[RubricDimension(key=d["key"], weight=d["weight"], five_means=d["five_means"]) for d in raw["rubric"]["dimensions"]])


def viva_out(db: Db, v: m.Viva) -> Viva:
    counts = dict(db.execute(select(m.Session.status, func.count()).where(m.Session.viva_id == v.id).group_by(m.Session.status)).all())
    return Viva(id=v.id, title=v.title, subject=v.subject, topics=list(v.topics), difficulty=v.difficulty, created_by=v.created_by,
                created_at=v.created_at, rules_version=v.rules_version, results_visible_to_students=bool(v.results_visible_to_students),
                config=config_view(v.config),
                question_count=db.scalar(select(func.count()).select_from(m.Question).where(m.Question.viva_id == v.id)),
                roster_count=db.scalar(select(func.count()).select_from(m.RosterEntry).where(m.RosterEntry.viva_id == v.id)),
                session_counts=counts)


def facts_for(db: Db, sessions: list, rubrics: dict) -> dict:
    """session id -> Facts, using four queries however many sessions there are. rubrics: viva id -> rubric dimension list."""
    ids = [s.id for s in sessions]
    out = {s.id: Facts() for s in sessions}
    if not ids:
        return out
    scores, overrides, reviews = defaultdict(list), defaultdict(list), defaultdict(list)
    for row in db.scalars(select(m.Score).where(m.Score.session_id.in_(ids))):
        scores[row.session_id].append(row)
    for row in db.scalars(select(m.Override).where(m.Override.session_id.in_(ids)).order_by(m.Override.id)):
        overrides[row.session_id].append(row)
    for row in db.scalars(select(m.Review).where(m.Review.session_id.in_(ids)).order_by(m.Review.id)):
        reviews[row.session_id].append(row)
    failed = [s.id for s in sessions if s.status == "failed"]
    errors = dict(db.execute(select(m.Job.session_id, m.Job.error).where(m.Job.session_id.in_(failed), m.Job.kind == "score")).all()) if failed else {}
    for s in sessions:
        f = out[s.id]
        if s.status == "failed":
            f.scoring_error = failure_sentence(errors.get(s.id))
        f.scoring, f.low_confidence, f.reasons = core.aggregate_scores(scores[s.id], rubrics[s.viva_id])
        f.overrides, f.reviews = overrides[s.id], reviews[s.id]
    return out


def override_entry(o: m.Override) -> OverrideEntry:
    return OverrideEntry(id=o.id, reviewer=o.reviewer, old_total=o.old_total, new_total=o.new_total, reason=o.reason, at=o.at)


def review_entry(r: m.Review) -> ReviewEntry:
    return ReviewEntry(id=r.id, reviewer=r.reviewer, note=r.note, at=r.at)


def summary(s: m.Session, name, f: Facts) -> SessionSummary:
    total, _ = f.effective
    return SessionSummary(session_id=s.id, student_id=s.student_id, student_name=name, status=s.status, started_at=s.started_at,
                          ended_at=s.ended_at, ai_total=f.scoring.median_total if f.scoring else None, effective_total=total,
                          overridden=bool(f.overrides), low_confidence=f.low_confidence, needs_review=f.needs_review,
                          scoring_error=f.scoring_error)


def audio_file(uri) -> Path | None:
    if not uri:
        return None
    path = Path(uri[7:] if uri.startswith("file://") else uri)
    return path if path.is_file() else None


def audio_ref(s: m.Session, secret: str, now) -> AudioRef:
    path = audio_file(s.audio_uri)
    if path is None:
        return AudioRef(available=False)
    exp = int((now + timedelta(seconds=AUDIO_URL_SECONDS)).timestamp())
    duration = None
    if path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path)) as w:
                duration = int(w.getnframes() * 1000 / w.getframerate())
        except (wave.Error, EOFError):
            pass
    return AudioRef(available=True, url=f"/faculty/sessions/{s.id}/audio?exp={exp}&sig={sign_audio(secret, s.id, exp)}",
                    content_type=audio_type(path), duration_ms=duration,
                    size_bytes=path.stat().st_size, expires_at=now + timedelta(seconds=AUDIO_URL_SECONDS))


def detail(db: Db, s: m.Session, viva: m.Viva, name, secret: str, now) -> SessionDetail:
    f = facts_for(db, [s], {viva.id: viva.config["rubric"]["dimensions"]})[s.id]
    total, source = f.effective
    events = db.scalars(select(m.IntegrityEvent).where(m.IntegrityEvent.session_id == s.id).order_by(m.IntegrityEvent.id)).all()
    return SessionDetail(
        session_id=s.id, viva_id=s.viva_id, student_id=s.student_id, student_name=name, status=s.status, rules_version=s.rules_version,
        consent_at=s.consent_at, started_at=s.started_at, ended_at=s.ended_at, deadline_at=s.deadline_at,
        turns=[Turn(idx=t.idx, role=t.role, text=t.text, t_start_ms=t.t_start_ms, t_end_ms=t.t_end_ms, phase=t.phase or "",
                    question_id=t.question_id, action=t.action, quality=t.quality, model=t.model, prompt_version=t.prompt_version)
               for t in core.turns_of(db, s.id)],
        scoring=f.scoring, scoring_error=f.scoring_error, low_confidence=f.low_confidence, low_confidence_reasons=f.reasons, needs_review=f.needs_review,
        effective_total=total, effective_source=source, audio=audio_ref(s, secret, now),
        overrides=[override_entry(o) for o in f.overrides], reviews=[review_entry(r) for r in f.reviews],
        integrity_events=[IntegrityEvent(id=e.id, kind=e.kind, t_ms=e.t_ms, detail=e.detail or {}) for e in events])
