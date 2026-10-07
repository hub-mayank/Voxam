"""The faculty side: vivas, bank, roster, sessions, audit, override, review, rescore, audio, export."""
import base64
import csv
import io
import json
import secrets
from datetime import timedelta
from uuid import UUID

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.exc import IntegrityError

from ..api.errors import ApiError, ErrorCode
from ..api.schemas.faculty import (IssuedEntry, OverrideRequest, OverrideResult, Question, QuestionList, RescoreResult,
                                   ResetCodeResult, ReviewRequest, ReviewResult, RosterEntry, RosterList, RosterUploadResult,
                                   SessionList, Viva, VivaCreate, VivaList, VivaUpdate)
from ..db import models as m
from ..session_state import REJOIN_OK, Event, SessionStatus, transition
from . import core, views
from .rules import RULES_VERSION
from .secrets_util import hash_code, new_code
from .stubs import file_source
from .uploads import parse_bank, parse_roster

MIN_CONCEPT, MIN_APPLIED = 7, 3
FAILED_OR_SCORED = (SessionStatus.failed.value, SessionStatus.scored.value)


def _cursor(s: m.Session) -> str:
    return base64.urlsafe_b64encode(f"{s.created_at.isoformat()}|{s.id}".encode()).decode()


def _parse_cursor(cursor: str):
    from datetime import datetime
    try:
        stamp, sid = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return datetime.fromisoformat(stamp), UUID(sid)
    except (ValueError, UnicodeDecodeError):
        raise ApiError(ErrorCode.validation_error, "Bad cursor.", {"fields": [{"loc": ["query", "cursor"], "message": "invalid cursor"}]})


class FacultyService:
    def __init__(self, db, settings, now):
        self.db, self.settings, self.now = db, settings, now

    def _viva(self, viva_id) -> m.Viva:
        return core.need(self.db, m.Viva, viva_id, "viva")

    def _session(self, sid) -> m.Session:
        return core.need(self.db, m.Session, sid, "session")

    def _sweep(self):
        core.sweep_expired(self.db, self.now())  # students who left: end them and queue scoring

    # ---------- vivas ----------

    def create_viva(self, body: VivaCreate, faculty) -> Viva:
        db = self.db
        viva_id = body.viva_id or f"viva-{secrets.token_hex(4)}"
        if db.get(m.Viva, viva_id):
            raise ApiError(ErrorCode.already_exists, details={"resource": "viva", "id": viva_id})
        config = json.loads(core.DEFAULT_CONFIG_PATH.read_text())
        config["viva_id"] = viva_id
        db.add(m.Viva(id=viva_id, title=body.title, subject=body.subject, topics=body.topics, difficulty=body.difficulty.value,
                      rules_version=RULES_VERSION, results_visible_to_students=body.results_visible_to_students, config=config,
                      created_by=faculty.reviewer, created_at=self.now()))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise ApiError(ErrorCode.already_exists, details={"resource": "viva", "id": viva_id})
        return views.viva_out(db, db.get(m.Viva, viva_id))

    def list_vivas(self) -> VivaList:
        self._sweep()
        rows = self.db.scalars(select(m.Viva).order_by(m.Viva.created_at.desc(), m.Viva.id)).all()
        return VivaList(items=[views.viva_out(self.db, v) for v in rows])

    def get_viva(self, viva_id) -> Viva:
        self._sweep()
        return views.viva_out(self.db, self._viva(viva_id))

    def update_viva(self, viva_id, body: VivaUpdate) -> Viva:
        v = self._viva(viva_id)
        if body.results_visible_to_students is not None:
            v.results_visible_to_students = body.results_visible_to_students
        self.db.commit()
        return views.viva_out(self.db, v)

    # ---------- bank and roster ----------

    def _bank_out(self, viva_id) -> QuestionList:
        rows = self.db.scalars(select(m.Question).where(m.Question.viva_id == viva_id).order_by(m.Question.id)).all()
        concept = sum(q.type == "concept" for q in rows)
        applied = len(rows) - concept
        warnings = []
        if rows and (concept < MIN_CONCEPT or applied < MIN_APPLIED):
            warnings.append(f"bank is small (concept={concept}, applied={applied}); aim for at least {MIN_CONCEPT} concept and {MIN_APPLIED} applied")
        return QuestionList(items=[Question(id=q.id, topic=q.topic, type=q.type, difficulty=q.difficulty, text=q.text,
                                            key_points=list(q.key_points or []), source=q.source, approved_by=q.approved_by) for q in rows],
                            concept_count=concept, applied_count=applied, warnings=warnings)

    def list_questions(self, viva_id) -> QuestionList:
        self._viva(viva_id)
        return self._bank_out(viva_id)

    def upload_questions(self, viva_id, filename, data: bytes) -> QuestionList:
        db = self.db
        self._viva(viva_id)
        if db.scalar(select(exists().where(m.Session.viva_id == viva_id))):
            raise ApiError(ErrorCode.invalid_state, "The question bank is locked: a student has already joined this viva.",
                           {"reason": "students_joined"})
        questions = parse_bank(filename, data)  # raises before anything is touched
        db.query(m.Question).filter(m.Question.viva_id == viva_id).delete()
        db.add_all([m.Question(viva_id=viva_id, id=q.id, topic=q.topic, type=q.type.value, difficulty=q.difficulty, text=q.text,
                               key_points=q.key_points, source="bank") for q in questions])
        db.commit()  # delete and insert land together or not at all
        return self._bank_out(viva_id)

    def upload_roster(self, viva_id, filename, data: bytes) -> RosterUploadResult:
        db, now, st = self.db, self.now(), self.settings
        self._viva(viva_id)
        rows = parse_roster(filename, data)
        known = set(db.scalars(select(m.RosterEntry.student_id).where(m.RosterEntry.viva_id == viva_id)))
        fresh = [(sid, name) for sid, name in rows if sid not in known]
        db.add_all([m.RosterEntry(viva_id=viva_id, student_id=sid, name=name, created_at=now) for sid, name in fresh])
        db.flush()  # roster rows must exist before the codes that reference them
        codes = {}
        if st.require_access_code:
            for sid, _ in fresh:
                codes[sid] = new_code()
                db.add(m.AccessCode(viva_id=viva_id, student_id=sid, code_hash=hash_code(st.access_code_pepper, viva_id, sid, codes[sid]),
                                    created_at=now))
        db.commit()
        items = [IssuedEntry(student_id=sid, name=name, outcome="created" if sid in codes or sid not in known else "unchanged",
                             access_code=codes.get(sid)) for sid, name in rows]
        return RosterUploadResult(items=items, created=len(fresh), unchanged=len(rows) - len(fresh))

    def list_roster(self, viva_id) -> RosterList:
        self._viva(viva_id)
        rows = self.db.execute(
            select(m.RosterEntry, m.Session).outerjoin(m.Session, and_(m.Session.viva_id == m.RosterEntry.viva_id,
                                                                       m.Session.student_id == m.RosterEntry.student_id))
            .where(m.RosterEntry.viva_id == viva_id).order_by(m.RosterEntry.student_id)).all()
        return RosterList(items=[RosterEntry(student_id=r.student_id, name=r.name, session_id=s.id if s else None,
                                             session_status=s.status if s else None) for r, s in rows])

    def reset_code(self, viva_id, student_id) -> ResetCodeResult:
        db, now, st = self.db, self.now(), self.settings
        self._viva(viva_id)
        roster = core.need(db, m.RosterEntry, (viva_id, student_id), "student")
        if not st.require_access_code:
            raise ApiError(ErrorCode.invalid_state, "Access codes are switched off on this server.", {"reason": "codes_disabled"})
        s = db.scalar(select(m.Session).where(m.Session.viva_id == viva_id, m.Session.student_id == student_id))
        if s is not None and s.status not in {x.value for x in REJOIN_OK}:
            raise ApiError(ErrorCode.invalid_state, "The session has ended; its code is dead.", {"status": s.status})
        for old in db.scalars(select(m.AccessCode).where(m.AccessCode.viva_id == viva_id, m.AccessCode.student_id == student_id,
                                                         m.AccessCode.revoked_at.is_(None))):
            old.revoked_at = now
        db.flush()  # the old code must be revoked before the new active one is inserted
        code = new_code()
        db.add(m.AccessCode(viva_id=viva_id, student_id=student_id, code_hash=hash_code(st.access_code_pepper, viva_id, student_id, code),
                            created_at=now))
        roster.failed_attempts, roster.locked_until = 0, None  # a reset also unlocks a locked-out student
        db.commit()
        return ResetCodeResult(student_id=student_id, access_code=code, issued_at=now)

    # ---------- sessions ----------

    def list_sessions(self, viva_id, status, low_confidence, search, limit, cursor) -> SessionList:
        db = self.db
        viva = self._viva(viva_id)
        self._sweep()
        q = (select(m.Session, m.RosterEntry.name)
             .join(m.RosterEntry, and_(m.RosterEntry.viva_id == m.Session.viva_id, m.RosterEntry.student_id == m.Session.student_id))
             .where(m.Session.viva_id == viva_id))
        if status is not None:
            q = q.where(m.Session.status == status.value)
        if low_confidence is not None:
            flagged = exists().where(m.Score.session_id == m.Session.id, m.Score.low_confidence.is_(True))
            q = q.where(flagged if low_confidence else ~flagged)
        if search:
            needle = search.lower()
            q = q.where(or_(func.lower(m.Session.student_id).contains(needle, autoescape=True),
                            func.lower(m.RosterEntry.name).contains(needle, autoescape=True)))
        if cursor:
            at, sid = _parse_cursor(cursor)
            q = q.where(or_(m.Session.created_at < at, and_(m.Session.created_at == at, m.Session.id < sid)))
        rows = db.execute(q.order_by(m.Session.created_at.desc(), m.Session.id.desc()).limit(limit + 1)).all()
        page = rows[:limit]
        facts = views.facts_for(db, [s for s, _ in page], {viva.id: viva.config["rubric"]["dimensions"]})
        return SessionList(items=[views.summary(s, name, facts[s.id]) for s, name in page],
                           next_cursor=_cursor(page[-1][0]) if len(rows) > limit else None)

    def get_session(self, sid):
        s = self._session(sid)
        self._sweep()
        self.db.refresh(s)
        name = self.db.scalar(select(m.RosterEntry.name).where(m.RosterEntry.viva_id == s.viva_id, m.RosterEntry.student_id == s.student_id))
        return views.detail(self.db, s, self.db.get(m.Viva, s.viva_id), name, self.settings.audio_signing_secret, self.now())

    def _facts(self, s):
        viva = self.db.get(m.Viva, s.viva_id)
        return views.facts_for(self.db, [s], {viva.id: viva.config["rubric"]["dimensions"]})[s.id]

    def override_session(self, sid, body: OverrideRequest, faculty) -> OverrideResult:
        db = self.db
        s = self._session(sid)
        if s.status not in FAILED_OR_SCORED:
            raise ApiError(ErrorCode.invalid_state, "Only scored or failed sessions can be overridden.",
                           {"status": s.status, "required_status": "scored"})
        old, _ = self._facts(s).effective
        row = m.Override(session_id=s.id, reviewer=faculty.reviewer, old_total=old, new_total=body.new_total, reason=body.reason, at=self.now())
        db.add(row)
        db.commit()
        db.refresh(row)
        return OverrideResult(override=views.override_entry(row), effective_total=row.new_total)

    def review_session(self, sid, body: ReviewRequest, faculty) -> ReviewResult:
        db = self.db
        s = self._session(sid)
        if s.status not in FAILED_OR_SCORED:
            raise ApiError(ErrorCode.invalid_state, "Only scored or failed sessions can be reviewed.",
                           {"status": s.status, "required_status": "scored"})
        row = m.Review(session_id=s.id, reviewer=faculty.reviewer, note=body.note, at=self.now())
        db.add(row)
        db.commit()
        db.refresh(row)
        return ReviewResult(review=views.review_entry(row), needs_review=self._facts(s).needs_review)

    def rescore_session(self, sid) -> RescoreResult:
        db = self.db
        s = self._session(sid)
        if s.status not in FAILED_OR_SCORED:
            raise ApiError(ErrorCode.invalid_state, "Only failed or scored sessions can be scored again.",
                           {"status": s.status, "required_status": "failed"})
        s.status = transition(s.status, Event.rescore).value
        core.enqueue_scoring(db, s.id, self.now())
        db.commit()
        return RescoreResult(session_id=s.id, status=s.status, job_status="queued")

    # ---------- audio and export ----------

    def audio(self, sid):
        """-> AudioSource. 404 audio_not_available when there is no recording."""
        s = self._session(sid)
        path = views.audio_file(s.audio_uri)
        if path is None:
            raise ApiError(ErrorCode.audio_not_available)
        return file_source(path, views.audio_type(path))

    def export_csv(self, viva_id) -> str:
        db = self.db
        viva = self._viva(viva_id)
        self._sweep()
        keys = [d["key"] for d in viva.config["rubric"]["dimensions"]]
        rows = db.execute(select(m.Session, m.RosterEntry.name).join(
            m.RosterEntry, and_(m.RosterEntry.viva_id == m.Session.viva_id, m.RosterEntry.student_id == m.Session.student_id))
            .where(m.Session.viva_id == viva_id).order_by(m.Session.student_id)).all()
        facts = views.facts_for(db, [s for s, _ in rows], {viva.id: viva.config["rubric"]["dimensions"]})
        out = io.StringIO()
        w = csv.writer(out, lineterminator="\n")
        w.writerow(["student_id", "name", "status", "ai_total", "effective_total", "overridden", "low_confidence", "needs_review",
                    *keys, "last_reviewer"])
        for s, name in rows:
            f = facts[s.id]
            scores = {d.key: d.score for d in f.scoring.dimensions} if f.scoring else {}
            reviewer = (f.overrides or f.reviews)[-1].reviewer if (f.overrides or f.reviews) else ""
            total = f.effective[0]
            w.writerow([_safe(s.student_id), _safe(name or ""), s.status, str(float(f.scoring.median_total)) if f.scoring else "",
                        str(float(total)) if total is not None else "",
                        str(bool(f.overrides)).lower(), str(f.low_confidence).lower(), str(f.needs_review).lower(),
                        *[f"{scores[k]:g}" if k in scores else "" for k in keys], reviewer])
        return out.getvalue()


def _safe(value: str) -> str:
    """Spreadsheet formula injection: a leading = + - @ in student-controlled text would run as a formula when opened."""
    return "'" + value if value[:1] in ("=", "+", "-", "@") else value
