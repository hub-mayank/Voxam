"""Database tables. Schema only, no business logic (that is T2b). db/schema.sql is generated from this file."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (Boolean, CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric, String, Text,
                        UniqueConstraint, Uuid, text)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ..session_state import SessionStatus
from .types import JsonType, UtcDateTime


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def one_of(column, values):
    return CheckConstraint(f"{column} IN ({', '.join(repr(v) for v in values)})", name=f"ck_{column}")


Total = Numeric(5, 2, asdecimal=False)  # marks out of 100, returned as float


class Base(DeclarativeBase):
    pass


class Viva(Base):
    __tablename__ = "vivas"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String)
    subject: Mapped[str] = mapped_column(String)
    topics: Mapped[list] = mapped_column(JsonType)
    difficulty: Mapped[str] = mapped_column(String)
    rules_version: Mapped[str] = mapped_column(String)
    results_visible_to_students: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[dict] = mapped_column(JsonType)  # phases, rubric, versions the engine runs
    created_by: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)


class Question(Base):
    __tablename__ = "questions"
    viva_id: Mapped[str] = mapped_column(ForeignKey("vivas.id"), primary_key=True)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    topic: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)
    difficulty: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    key_points: Mapped[list] = mapped_column(JsonType, default=list)
    source: Mapped[str] = mapped_column(String, default="bank")
    approved_by: Mapped[Optional[str]] = mapped_column(String)
    __table_args__ = (one_of("type", ["concept", "applied"]), one_of("source", ["bank", "generated"]))


class RosterEntry(Base):
    __tablename__ = "roster"
    viva_id: Mapped[str] = mapped_column(ForeignKey("vivas.id"), primary_key=True)
    student_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)


class AccessCode(Base):
    """Hashed one-time codes. A reset revokes the old row and adds a new one; at most one row per student is active."""
    __tablename__ = "access_codes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    viva_id: Mapped[str] = mapped_column(String)
    student_id: Mapped[str] = mapped_column(String)
    code_hash: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(UtcDateTime)
    __table_args__ = (
        ForeignKeyConstraint(["viva_id", "student_id"], ["roster.viva_id", "roster.student_id"]),
        Index("uq_access_codes_active", "viva_id", "student_id", unique=True,
              sqlite_where=text("revoked_at IS NULL"), postgresql_where=text("revoked_at IS NULL")),
    )


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    viva_id: Mapped[str] = mapped_column(ForeignKey("vivas.id"))
    student_id: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default=SessionStatus.created.value)
    token_hash: Mapped[Optional[str]] = mapped_column(String)  # hash of the current session token; rotates on rejoin
    consent_at: Mapped[Optional[datetime]] = mapped_column(UtcDateTime)  # was NOT NULL; a session exists before consent
    rules_version: Mapped[Optional[str]] = mapped_column(String)
    started_at: Mapped[Optional[datetime]] = mapped_column(UtcDateTime)
    deadline_at: Mapped[Optional[datetime]] = mapped_column(UtcDateTime)  # started_at + hard limit, fixed at start
    ended_at: Mapped[Optional[datetime]] = mapped_column(UtcDateTime)
    audio_uri: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    __table_args__ = (
        ForeignKeyConstraint(["viva_id", "student_id"], ["roster.viva_id", "roster.student_id"]),
        UniqueConstraint("viva_id", "student_id", name="uq_sessions_student"),
        one_of("status", [s.value for s in SessionStatus]),
        Index("ix_sessions_viva_status", "viva_id", "status"),
    )


class Turn(Base):
    """Spoken turns only. `idx` counts them from 0 and is the number scoring evidence cites."""
    __tablename__ = "turns"
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id"), primary_key=True)
    idx: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(String)
    text: Mapped[str] = mapped_column(Text)
    t_start_ms: Mapped[Optional[int]] = mapped_column(Integer)
    t_end_ms: Mapped[Optional[int]] = mapped_column(Integer)
    phase: Mapped[Optional[str]] = mapped_column(String)
    question_id: Mapped[Optional[str]] = mapped_column(String)
    action: Mapped[Optional[str]] = mapped_column(String)
    quality: Mapped[Optional[str]] = mapped_column(String)
    model: Mapped[Optional[str]] = mapped_column(String)
    prompt_version: Mapped[Optional[str]] = mapped_column(String)
    client_seq: Mapped[Optional[int]] = mapped_column(Integer)  # student turns: the answer's client_seq (idempotency)
    meta: Mapped[Optional[dict]] = mapped_column(JsonType)  # engine audit events for this turn (classify_error, bank_exhausted)
    __table_args__ = (one_of("role", ["ai", "student"]), UniqueConstraint("session_id", "client_seq", name="uq_turns_client_seq"))


class Score(Base):
    """One scorer run. The median over runs is computed on read."""
    __tablename__ = "scores"
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id"), primary_key=True)
    run: Mapped[int] = mapped_column(Integer, primary_key=True)
    rubric_version: Mapped[str] = mapped_column(String)
    prompt_version: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String)
    dims: Mapped[dict] = mapped_column(JsonType)
    total: Mapped[Optional[float]] = mapped_column(Total)
    confidence: Mapped[Optional[float]] = mapped_column(Numeric(4, 3, asdecimal=False))
    low_confidence: Mapped[bool] = mapped_column(Boolean, default=False)
    low_confidence_reasons: Mapped[Optional[list]] = mapped_column(JsonType)
    feedback: Mapped[Optional[list]] = mapped_column(JsonType)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)


class Override(Base):
    __tablename__ = "overrides"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # the latest id wins
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id"), index=True)
    reviewer: Mapped[str] = mapped_column(String)
    old_total: Mapped[Optional[float]] = mapped_column(Total)
    new_total: Mapped[float] = mapped_column(Total)
    reason: Mapped[str] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)


class IntegrityEvent(Base):
    __tablename__ = "integrity_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id"), index=True)
    kind: Mapped[str] = mapped_column(String)
    t_ms: Mapped[int] = mapped_column(Integer)
    detail: Mapped[Optional[dict]] = mapped_column(JsonType)


class Job(Base):
    """Scoring queue. One job per (session, kind), so enqueueing twice is harmless. Claiming is T2b's job."""
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String, default="score")
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id"))
    status: Mapped[str] = mapped_column(String, default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_at: Mapped[Optional[datetime]] = mapped_column(UtcDateTime)
    locked_by: Mapped[Optional[str]] = mapped_column(String)
    run_after: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow, onupdate=utcnow)
    __table_args__ = (
        one_of("status", ["queued", "running", "done", "failed"]),
        UniqueConstraint("session_id", "kind", name="uq_jobs_session_kind"),
        Index("ix_jobs_claim", "status", "run_after"),
    )
