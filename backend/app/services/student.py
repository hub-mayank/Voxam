"""The student side: join, consent, start, answer, status, result. All state lives in the database."""
import logging
import time
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from ..api.errors import ApiError, ErrorCode
from ..api.schemas.student import (AiTurn, AnswerRequest, AnswerResponse, ConsentRequest, ConsentResponse, JoinRequest,
                                   JoinResponse, StartResponse, StatusResponse, StudentDimension, StudentResult)
from ..clock import VivaClock
from ..db import models as m
from ..interviewer import Interviewer
from ..llm.graceful import GracefulLLM
from ..session_state import Event, InvalidTransition, SessionStatus, can_rejoin, transition
from . import core, views
from .rules import RULES
from .secrets_util import code_matches, hash_code, hash_token, new_session_token
from .throttle import SlidingWindow

audit = logging.getLogger("aiviva.audit")
POLL_SECONDS = 0.05


class _NoLLM:
    name = None  # start() never calls a model


def harvest(events):
    """From the interviewer's new log entries: the student's classified quality, audit notes and the AI turn."""
    quality, meta, ai = None, {}, None
    for e in events:
        if e["role"] == "system":
            quality = e.get("quality", quality)
            if e.get("action") == "classify_error":
                meta["classify_error"] = e.get("error")
            if e.get("action") == "bank_exhausted":
                meta["bank_exhausted"] = True
        elif e["role"] == "ai":
            ai = e
    return quality, meta, ai


class StudentService:
    def __init__(self, db, settings, now, llm_factory, sleep=time.sleep, ip_throttle: SlidingWindow = None):
        self.db, self.settings, self.now, self.llm_factory, self.sleep = db, settings, now, llm_factory, sleep
        self.ip_throttle = ip_throttle or SlidingWindow(settings.ip_failures_per_minute)

    # ---------- small helpers ----------

    def _session(self, sid) -> m.Session:
        return core.need(self.db, m.Session, sid, "session")

    def _viva(self, s) -> m.Viva:
        return self.db.get(m.Viva, s.viva_id)

    def _ai(self, t: m.Turn) -> AiTurn:
        return AiTurn(idx=t.idx, text=t.text, phase=t.phase or "", ended=t.action == "close")

    def _ended(self, s):
        raise ApiError(ErrorCode.session_ended, details={"status": s.status})

    def _need_in_progress(self, s):
        if s.status == SessionStatus.in_progress.value:
            return
        if s.status in (SessionStatus.created.value, SessionStatus.consented.value):
            raise ApiError(ErrorCode.invalid_state, details={"status": s.status, "required_status": "in_progress"})
        self._ended(s)

    def _expire(self, s, say_goodbye=True):
        """Deadline passed while the session was in progress: end it, queue scoring, commit. Returns the closing text."""
        text = core.expire_session(self.db, s, self.now(), say_goodbye)
        self.db.commit()
        return text

    # ---------- join ----------

    def join(self, body: JoinRequest, client_ip: str = "unknown") -> JoinResponse:
        db, now, st = self.db, self.now(), self.settings
        if st.require_access_code and not body.access_code:
            raise ApiError(ErrorCode.validation_error, "access_code is required.",
                           {"fields": [{"loc": ["body", "access_code"], "message": "Field required"}]})
        viva = db.get(m.Viva, body.viva_id)
        roster = db.get(m.RosterEntry, (body.viva_id, body.student_id)) if viva else None
        if st.require_access_code:
            self._check_code(roster, body, now, client_ip)
        elif roster is None:
            raise ApiError(ErrorCode.invalid_credentials)
        for attempt in range(2):
            s = db.scalar(select(m.Session).where(m.Session.viva_id == viva.id, m.Session.student_id == body.student_id))
            token = new_session_token()
            if s is None:
                s = m.Session(viva_id=viva.id, student_id=body.student_id, token_hash=hash_token(token), created_at=now)
                db.add(s)
                resumed = False
            else:
                if s.status == SessionStatus.in_progress.value and s.deadline_at and now >= s.deadline_at:
                    self._expire(s, say_goodbye=False)
                if not can_rejoin(s.status):
                    raise ApiError(ErrorCode.session_ended, details={"status": s.status})
                s.token_hash, resumed = hash_token(token), True  # the old token stops working
            try:
                db.commit()
                break
            except IntegrityError:  # two joins for the same student at once: the other one created the session
                db.rollback()
                if attempt:
                    raise
        cfg = core.viva_config(viva)
        return JoinResponse(session_id=s.id, session_token=token, status=s.status, resumed=resumed, viva_title=viva.title,
                            duration_ms=cfg.hard_limit * 1000, rules_text=RULES[viva.rules_version], rules_version=viva.rules_version)

    def _check_code(self, roster, body, now, client_ip):
        """Constant-time code check with a growing delay. After n wrong codes for a student the next try must wait
        min(cap, 2^(n-1)) seconds; attempts made during the wait are refused WITHOUT being checked and do not extend it, so a
        spammer can never keep the real student out for longer than the cap. A second limit counts wrong codes per client IP.
        Unknown student, wrong code and no code on file all look the same."""
        db, st = self.db, self.settings
        stamp = now.timestamp()
        wait = self.ip_throttle.retry_after_s(client_ip, stamp)
        if wait > 0:
            raise ApiError(ErrorCode.rate_limited, "Too many wrong codes from this address.", {"retry_after_ms": int(wait * 1000) + 1})
        if roster is not None and roster.locked_until and roster.locked_until > now:  # locked_until = next attempt allowed at
            raise ApiError(ErrorCode.rate_limited, details={"retry_after_ms": core.ms_between(roster.locked_until, now)})
        row = None
        if roster is not None:
            row = db.scalar(select(m.AccessCode).where(m.AccessCode.viva_id == roster.viva_id, m.AccessCode.student_id == roster.student_id,
                                                       m.AccessCode.revoked_at.is_(None)))
        if row is not None:
            ok = code_matches(st.access_code_pepper, body.viva_id, body.student_id, body.access_code, row.code_hash)
        else:
            hash_code(st.access_code_pepper, body.viva_id, body.student_id, body.access_code)  # same work either way
            ok = False
        if ok:
            if roster.failed_attempts or roster.locked_until:
                roster.failed_attempts, roster.locked_until = 0, None
                db.commit()
            return
        self.ip_throttle.record(client_ip, stamp)
        if roster is not None:
            db.execute(update(m.RosterEntry).where(m.RosterEntry.viva_id == roster.viva_id, m.RosterEntry.student_id == roster.student_id)
                       .values(failed_attempts=m.RosterEntry.failed_attempts + 1))
            db.flush()
            db.refresh(roster)
            delay = min(st.code_delay_cap_seconds, 2 ** (min(roster.failed_attempts, 30) - 1))
            roster.locked_until = now + timedelta(seconds=delay)
            db.commit()
        raise ApiError(ErrorCode.invalid_credentials)

    # ---------- consent and start ----------

    def consent(self, sid, body: ConsentRequest) -> ConsentResponse:
        s = self._session(sid)
        viva = self._viva(s)
        if body.rules_version != viva.rules_version:
            raise ApiError(ErrorCode.rules_version_mismatch, details={"current_rules_version": viva.rules_version})
        if not body.accepted:
            return ConsentResponse(status=s.status, consent_at=s.consent_at)
        if s.status == SessionStatus.created.value:
            s.status = transition(s.status, Event.consent).value
            s.consent_at, s.rules_version = self.now(), viva.rules_version
            self.db.commit()
        elif s.status not in (SessionStatus.consented.value, SessionStatus.in_progress.value):
            self._ended(s)
        return ConsentResponse(status=s.status, consent_at=s.consent_at)

    def start(self, sid) -> StartResponse:
        db, now = self.db, self.now()
        s = self._session(sid)
        viva = self._viva(s)
        if s.status == SessionStatus.consented.value:
            if not core.bank_of(db, viva.id):
                raise ApiError(ErrorCode.invalid_state, "The question bank is empty; ask faculty to upload it.", {"status": s.status})
            cfg = core.viva_config(viva)
            claimed = db.execute(update(m.Session).where(m.Session.id == s.id, m.Session.status == SessionStatus.consented.value)
                                 .values(status=transition(s.status, Event.start).value, started_at=now,
                                         deadline_at=now + timedelta(seconds=cfg.hard_limit)))
            if claimed.rowcount == 1:  # we won the start; a concurrent second start sees in_progress and just reads
                db.refresh(s)
                iv = Interviewer(_NoLLM(), [], VivaClock.resume(cfg, now, self.now), cfg, seed=str(s.id))
                text, event = iv.start(), iv.log[-1]
                db.add(m.Turn(session_id=s.id, idx=0, role="ai", text=text, phase=event["phase"], question_id=event["question_id"],
                              action="open", prompt_version=cfg.prompt_version, created_at=now))
                db.commit()
            else:
                db.rollback()
            db.expire_all()
            s = self._session(sid)
        if s.status == SessionStatus.created.value:
            raise ApiError(ErrorCode.invalid_state, details={"status": s.status, "required_status": "consented"})
        if s.status != SessionStatus.in_progress.value:
            self._ended(s)
        if now >= s.deadline_at:
            self._expire(s)
            self._ended(s)
        current = [t for t in core.turns_of(db, s.id) if t.role == "ai"][-1]
        return StartResponse(status=s.status, started_at=s.started_at, deadline_at=s.deadline_at, server_now=now,
                             remaining_ms=core.remaining_ms(s, now), turn=self._ai(current))

    # ---------- answer ----------

    def _out(self, s, seq, reply, replayed, now) -> AnswerResponse:
        return AnswerResponse(client_seq=seq, replayed=replayed, status=s.status, turn=self._ai(reply), server_now=now,
                              remaining_ms=core.remaining_ms(s, now) or 0)

    def _reply_to(self, turns, mine):
        return next((t for t in turns if t.idx == mine.idx + 1 and t.role == "ai"), None)

    def answer(self, sid, body: AnswerRequest) -> AnswerResponse:
        now = self.now()
        s = self._session(sid)
        turns = core.turns_of(self.db, s.id)
        students = [t for t in turns if t.role == "student"]
        last = max((t.client_seq or 0 for t in students), default=0)
        seq = body.client_seq
        if seq <= last:  # a retry of an answer we already have
            mine = next(t for t in students if t.client_seq == seq)
            if mine.text != body.text:
                raise ApiError(ErrorCode.bad_client_seq, "This client_seq was already used with different text.",
                               {"expected": last + 1, "received": seq})
            reply = self._reply_to(turns, mine)
            if reply is not None:
                return self._out(s, seq, reply, True, now)
        else:
            self._need_in_progress(s)  # a finished session says so before it complains about sequence numbers
            if seq != last + 1:
                raise ApiError(ErrorCode.bad_client_seq, details={"expected": last + 1, "received": seq})
            if students and self._reply_to(turns, students[-1]) is None:  # the previous answer is still waiting for its reply
                raise ApiError(ErrorCode.bad_client_seq, "Resend the previous answer first.", {"expected": last, "received": seq})
            if now >= s.deadline_at:
                closing = self._expire(s)
                raise ApiError(ErrorCode.deadline_passed, details={"closing_text": closing, "deadline_at": s.deadline_at.strftime("%Y-%m-%dT%H:%M:%SZ")})
        return self._serialized(sid, seq, body)

    def _claim(self, sid) -> bool:
        now = self.now()
        won = self.db.execute(update(m.Session).where(m.Session.id == sid, (m.Session.lease_until.is_(None)) | (m.Session.lease_until < now))
                              .values(lease_until=now + timedelta(seconds=self.settings.answer_lease_seconds)))
        self.db.commit()
        return won.rowcount == 1

    def _release(self, sid):
        self.db.rollback()
        self.db.execute(update(m.Session).where(m.Session.id == sid).values(lease_until=None))
        self.db.commit()

    def _finished_reply(self, sid, seq, text):
        self.db.expire_all()
        turns = core.turns_of(self.db, sid)
        mine = next((t for t in turns if t.role == "student" and t.client_seq == seq), None)
        reply = self._reply_to(turns, mine) if mine is not None else None
        if reply is None:
            return None
        if mine.text != text:
            raise ApiError(ErrorCode.bad_client_seq, "This client_seq was already used with different text.", {"received": seq})
        return self._out(self._session(sid), seq, reply, True, self.now())

    def _serialized(self, sid, seq, body) -> AnswerResponse:
        """One answer at a time per session. The loser of a race waits for the winner's reply and returns it as a replay."""
        give_up = time.monotonic() + self.settings.answer_lease_seconds + 5
        while not self._claim(sid):
            done = self._finished_reply(sid, seq, body.text)
            if done is not None:
                return done
            if time.monotonic() > give_up:
                raise ApiError(ErrorCode.provider_unavailable, "Still processing; retry the same request.", {"retry_after_ms": 3000})
            self.sleep(POLL_SECONDS)
        try:
            return self._under_lease(sid, seq, body)
        finally:
            self._release(sid)

    def _interviewer(self, s, viva, before):
        cfg = core.viva_config(viva)
        llm = GracefulLLM(self.llm_factory(self.settings.llm_chain or None))
        iv = Interviewer(llm, core.bank_of(self.db, viva.id), VivaClock.resume(cfg, s.started_at, self.now), cfg, seed=str(s.id))
        return iv.restore([core.turn_dict(t) for t in before]), llm, cfg

    def _under_lease(self, sid, seq, body) -> AnswerResponse:
        db = self.db
        db.expire_all()
        s = self._session(sid)
        viva = self._viva(s)
        turns = core.turns_of(db, s.id)
        mine = next((t for t in turns if t.role == "student" and t.client_seq == seq), None)
        if mine is not None:
            reply = self._reply_to(turns, mine)
            if reply is not None:  # another worker finished it while we waited for the lease
                return self._out(s, seq, reply, True, self.now())
            before = [t for t in turns if t.idx < mine.idx]
        else:
            self._need_in_progress(s)
            before = turns
        iv, llm, cfg = self._interviewer(s, viva, before)
        now = self.now()
        if mine is None:  # the answer is stored BEFORE any model is called
            mine = m.Turn(session_id=s.id, idx=len(before), role="student", text=body.text, phase=iv.phase_name,
                          question_id=iv.q["id"], t_start_ms=body.t_start_ms, t_end_ms=body.t_end_ms, client_seq=seq, created_at=now)
            db.add(mine)
            db.commit()
        marker = len(iv.log)
        iv.respond(mine.text)
        quality, meta, event = harvest(iv.log[marker:])
        if llm.errors:
            meta["llm_errors"] = llm.errors
            if any(e.startswith("phrase") for e in llm.errors):
                meta["llm_degraded"] = True
                audit.warning("llm degraded, canned reply used: session=%s idx=%s errors=%s", s.id, mine.idx + 1, llm.errors)
        now = self.now()
        mine.quality = quality
        reply = m.Turn(session_id=s.id, idx=mine.idx + 1, role="ai", text=event["text"], phase=event["phase"], question_id=event["question_id"],
                       action=event["action"], model=llm.served if llm.calls else None, prompt_version=cfg.prompt_version,
                       meta=meta or None, created_at=now)
        db.add(reply)
        if event["action"] == "close":  # the session ends and the scoring job is queued in this same transaction
            db.flush()
            core.end_session(db, s, now, now)
        db.commit()
        return self._out(s, seq, reply, False, now)

    # ---------- status and result ----------

    def status(self, sid) -> StatusResponse:
        db, now = self.db, self.now()
        s = self._session(sid)
        if s.status == SessionStatus.in_progress.value and now >= s.deadline_at:
            self._expire(s)
        turns = core.turns_of(db, s.id)
        ai = [t for t in turns if t.role == "ai"]
        seqs = [t.client_seq or 0 for t in turns if t.role == "student"]
        return StatusResponse(status=s.status, phase=ai[-1].phase if ai else None, server_now=now, started_at=s.started_at,
                              deadline_at=s.deadline_at, remaining_ms=core.remaining_ms(s, now), last_client_seq=max(seqs, default=0),
                              current_turn=self._ai(ai[-1]) if ai else None)

    def result(self, sid) -> StudentResult:
        db = self.db
        s = self._session(sid)
        viva = self._viva(s)
        if not viva.results_visible_to_students:
            raise ApiError(ErrorCode.results_not_released)
        if s.status != SessionStatus.scored.value:
            raise ApiError(ErrorCode.invalid_state, "Your result is not ready yet.", {"status": s.status, "required_status": "scored"})
        f = views.facts_for(db, [s], {viva.id: viva.config["rubric"]["dimensions"]})[s.id]
        total, _ = f.effective
        return StudentResult(total=total, overridden=bool(f.overrides),
                             dimensions=[StudentDimension(key=d.key, weight=d.weight, score=d.score) for d in f.scoring.dimensions],
                             feedback=f.scoring.feedback)
