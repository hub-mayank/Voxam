"""The scoring worker: claim, score, store, retry, restart. Real API + database (SQLite, or PostgreSQL with --postgres), the mock scorer."""
import threading
import wave
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import select

from app.db import models as m
from app.llm.budget import CallCapExceeded
from app.llm.mock import MockLLM
from app.services import core, jobs, scoring
from app.worker import run_pass
from harness import IYER, RAO, answer, begin, build, db_of, ended_session, make_viva

MOCK = lambda spec: MockLLM()  # noqa: E731


class Crash(BaseException):
    """The process dies: not an Exception, so nothing in the worker may swallow it."""


class Counting(MockLLM):
    def __init__(self, fail_with=None):
        self.calls, self.fail_with = 0, fail_with

    def complete_json(self, system, user, max_tokens=200, kind="classify"):
        self.calls += 1
        if self.fail_with:
            raise self.fail_with
        return super().complete_json(system, user, max_tokens, kind)


@pytest.fixture()
def env(tmp_path):
    app, client, clock = build(tmp_path)
    codes = make_viva(client, students=("S1", "S2", "S3", "S4", "S5", "S6"))
    return app, client, clock, codes


def rows_of(app, sid):
    with db_of(app) as db:
        return list(db.scalars(select(m.Score).where(m.Score.session_id == UUID(sid)).order_by(m.Score.run)))


def job_of(app, sid):
    with db_of(app) as db:
        return db.scalar(select(m.Job).where(m.Job.session_id == UUID(sid)))


def status_of(app, sid):
    with db_of(app) as db:
        return db.get(m.Session, UUID(sid)).status


def step(app, clock, worker="w1", factory=MOCK):
    with db_of(app) as db:
        return scoring.process_next(db, worker, clock(), factory)


def test_the_worker_scores_an_ended_session_and_stores_the_audit_trail(env):
    app, client, clock, codes = env
    sid, h = ended_session(client, clock, codes)
    assert job_of(app, sid).status == "queued" and status_of(app, sid) == "ended"
    assert step(app, clock) == "scored"
    rows = rows_of(app, sid)
    assert [r.run for r in rows] == [1, 2, 3] and status_of(app, sid) == "scored" and job_of(app, sid).status == "done"
    assert {(r.rubric_version, r.prompt_version, r.model) for r in rows} == {("rubric-v1", "scorer-v1", "mock")}
    assert {r.run_spread for r in rows} == {round(max(r.total for r in rows) - min(r.total for r in rows), 2)}
    for r in rows:
        assert set(r.dims) == {"conceptual", "depth", "problem", "practical", "communication"}
        assert all(d["evidence"] and len(d["evidence_ms"]) == len(d["evidence"]) and d["reason"] for d in r.dims.values())
        assert len(r.feedback) >= 3
    assert step(app, clock) is None, "nothing left to do"


def test_the_stored_result_reads_back_through_the_faculty_api(env):
    app, client, clock, codes = env
    sid, h = ended_session(client, clock, codes)
    step(app, clock)
    d = client.get(f"/faculty/sessions/{sid}", headers=RAO).json()
    assert d["status"] == "scored" and len(d["scoring"]["runs"]) == 3 and d["scoring"]["prompt_version"] == "scorer-v1"
    assert d["scoring"]["median_total"] == d["effective_total"] and d["effective_source"] == "ai"
    assert {x["idx"] for x in d["turns"]} >= {i for dim in d["scoring"]["dimensions"] for i in dim["evidence"]}, "evidence cites real turns"
    listed = client.get("/faculty/vivas/demo-viva/sessions", headers=RAO).json()["items"][0]
    assert listed["ai_total"] == d["scoring"]["median_total"]


def test_a_second_job_for_a_scored_session_does_no_work(env):
    app, client, clock, codes = env
    sid, h = ended_session(client, clock, codes)
    step(app, clock)
    with db_of(app) as db:
        core.enqueue_scoring(db, UUID(sid), clock())  # e.g. a duplicate enqueue
        db.commit()
    llm = Counting()
    assert step(app, clock, factory=lambda spec: llm) == "already_scored"
    assert llm.calls == 0 and len(rows_of(app, sid)) == 3 and job_of(app, sid).status == "done"


def test_a_worker_that_dies_mid_job_is_replaced_and_the_session_is_scored_once(env):
    app, client, clock, codes = env
    sid, h = ended_session(client, clock, codes)
    with pytest.raises(Crash):
        step(app, clock, "w1", factory=lambda spec: Counting(fail_with=Crash()))
    job = job_of(app, sid)
    assert (job.status, job.locked_by, job.attempts) == ("running", "w1", 1) and status_of(app, sid) == "scoring" and not rows_of(app, sid)
    clock.advance(jobs.DEFAULT_LEASE_S - 1)
    assert step(app, clock, "w2") is None, "the lease has not run out: w2 must not take it"
    clock.advance(2)
    assert step(app, clock, "w2") == "scored"
    job = job_of(app, sid)
    assert (job.status, job.attempts) == ("done", 2) and len(rows_of(app, sid)) == 3 and status_of(app, sid) == "scored"
    with db_of(app) as db:
        assert jobs.complete_job(db, job.id, "w1", clock()) is False, "the dead worker cannot complete it later"


def test_a_slow_worker_whose_lease_ran_out_writes_nothing(env):
    app, client, clock, codes = env
    sid, h = ended_session(client, clock, codes)

    class SlowThenLate(MockLLM):
        """While w1 is 'thinking', time passes and w2 takes the job and finishes it."""
        def complete_json(self, system, user, max_tokens=200, kind="classify"):
            if not getattr(self, "hijacked", False):
                self.hijacked = True
                clock.advance(jobs.DEFAULT_LEASE_S + 1)
                assert step(app, clock, "w2") == "scored"
            return super().complete_json(system, user, max_tokens, kind)

    assert step(app, clock, "w1", factory=lambda spec: SlowThenLate()) == "lost"
    assert len(rows_of(app, sid)) == 3 and job_of(app, sid).status == "done" and job_of(app, sid).locked_by == "w2"


def test_failures_retry_with_a_growing_delay_then_fail_the_session_and_a_rescore_recovers(env):
    app, client, clock, codes = env
    sid, h = ended_session(client, clock, codes)
    broken = lambda spec: Counting(fail_with=RuntimeError("provider down"))  # noqa: E731
    assert step(app, clock, factory=broken) == "retry"
    job = job_of(app, sid)
    assert job.status == "queued" and job.run_after - clock() == timedelta(seconds=30) and status_of(app, sid) == "scoring"
    assert step(app, clock, factory=broken) is None, "not due yet"
    clock.advance(31)
    assert step(app, clock, factory=broken) == "retry"
    assert job_of(app, sid).run_after - clock() == timedelta(seconds=60), "the delay grows"
    clock.advance(61)
    assert step(app, clock, factory=broken) == "failed"
    assert (job_of(app, sid).status, status_of(app, sid)) == ("failed", "failed") and "provider down" in job_of(app, sid).error
    assert client.post(f"/faculty/sessions/{sid}/rescore", headers=RAO).status_code == 202
    assert step(app, clock) == "scored" and len(rows_of(app, sid)) == 3 and status_of(app, sid) == "scored"


def test_a_provider_out_of_budget_defers_the_job_without_using_an_attempt(env):
    app, client, clock, codes = env
    sid, h = ended_session(client, clock, codes)
    out_of_budget = lambda spec: Counting(fail_with=CallCapExceeded("groq|openai/gpt-oss-20b: free-tier budget used"))  # noqa: E731
    assert step(app, clock, factory=out_of_budget) == "deferred"
    job = job_of(app, sid)
    assert (job.status, job.attempts) == ("queued", 0) and job.run_after - clock() == timedelta(seconds=scoring.BUDGET_WAIT_SECONDS)
    assert "budget" in job.error and status_of(app, sid) == "scoring"
    clock.advance(scoring.BUDGET_WAIT_SECONDS + 1)
    assert step(app, clock) == "scored"


def test_a_session_nobody_answered_fails_at_once_instead_of_retrying(env):
    app, client, clock, codes = env
    sid, h = begin(client, codes["S1"])  # started, never answered
    clock.advance(901)
    assert client.get(f"/student/sessions/{sid}/status", headers=h).json()["status"] == "ended"
    assert step(app, clock) == "failed"
    assert (status_of(app, sid), job_of(app, sid).attempts) == ("failed", 1) and "no student turns" in job_of(app, sid).error


def test_a_rescore_replaces_the_old_rows_and_a_failed_rescore_changes_nothing(env, monkeypatch):
    app, client, clock, codes = env
    sid, h = ended_session(client, clock, codes)
    step(app, clock)
    old = [(r.run, r.total, r.created_at) for r in rows_of(app, sid)]

    class Harsh(MockLLM):
        def _score(self, user):
            out = super()._score(user)
            for d in out["dimensions"].values():
                d["score"], d["reason"] = 1, "harsh"
                d["evidence"] = d["evidence"][:1]
            return out

    real_store = scoring.store_scores

    def store_then_break(db, s, result, now):
        real_store(db, s, result, now)  # old rows deleted, new rows added ...
        raise RuntimeError("disk full")  # ... and then the transaction dies

    client.post(f"/faculty/sessions/{sid}/rescore", headers=IYER)
    monkeypatch.setattr(scoring, "store_scores", store_then_break)
    assert step(app, clock, factory=lambda spec: Harsh()) == "retry"
    assert [(r.run, r.total, r.created_at) for r in rows_of(app, sid)] == old, "the old rows survived the failed store"
    monkeypatch.undo()
    clock.advance(31)
    assert step(app, clock, factory=lambda spec: Harsh()) == "scored"
    new = rows_of(app, sid)
    assert [r.run for r in new] == [1, 2, 3] and {r.total for r in new} == {20.0} and {d["reason"] for r in new for d in r.dims.values()} == {"harsh"}
    assert status_of(app, sid) == "scored"


def test_the_background_pass_ends_expired_sessions_and_scores_them(env):
    app, client, clock, codes = env
    sid, h = begin(client, codes["S1"])
    for seq in (1, 2, 3):
        clock.advance(20)
        assert answer(client, sid, h, seq).status_code == 200
    clock.advance(901)  # the student left; nobody asks for the status
    with db_of(app) as db:
        assert db.get(m.Session, UUID(sid)).status == "in_progress"
        counts = run_pass(db, "w1", clock, MOCK)
    assert counts == {"swept": 1, "scored": 1} and status_of(app, sid) == "scored"
    with db_of(app) as db:
        assert run_pass(db, "w1", clock, MOCK) == {"swept": 0}


def test_low_confidence_signals_are_stored_and_reach_the_faculty_flag(env):
    app, client, clock, codes = env
    sid, h = begin(client, codes["S1"])
    for seq in range(1, 5):
        clock.advance(20)
        assert answer(client, sid, h, seq, "I don't know").status_code == 200
    clock.advance(901)
    client.get(f"/student/sessions/{sid}/status", headers=h)
    step(app, clock)
    reasons = rows_of(app, sid)[0].low_confidence_reasons
    assert any("repeated" in r for r in reasons) and all(r.low_confidence for r in rows_of(app, sid))
    detail = client.get(f"/faculty/sessions/{sid}", headers=RAO).json()
    assert detail["low_confidence"] and detail["needs_review"] and detail["low_confidence_reasons"] == reasons


def voice_session(app, client, clock, codes, student, wav=None, confidence=None):
    """A session whose student turns look like voice: audio offsets, optional STT confidence, optional recording on disk."""
    sid, h = begin(client, codes[student], student)
    for seq in range(1, 8):
        clock.advance(20)
        assert answer(client, sid, h, seq).status_code == 200
    clock.advance(901)
    client.get(f"/student/sessions/{sid}/status", headers=h)
    with db_of(app) as db:
        for t in core.turns_of(db, UUID(sid)):
            t.t_start_ms = t.idx * 10_000 if t.role == "student" else None
            if t.role == "student" and confidence is not None:
                t.meta = {"stt_confidence": confidence}
        if wav:
            db.get(m.Session, UUID(sid)).audio_uri = str(wav)
        db.commit()
    return sid


def test_voice_signals_missing_audio_and_shaky_speech_recognition(env, tmp_path):
    app, client, clock, codes = env
    wav = tmp_path / "a.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(16000), w.writeframes(b"\0\0" * 1600)
    ok = voice_session(app, client, clock, codes, "S1", wav=wav, confidence=0.9)
    gone = voice_session(app, client, clock, codes, "S2", wav=None, confidence=0.9)
    shaky = voice_session(app, client, clock, codes, "S3", wav=wav, confidence=0.4)
    while step(app, clock):
        pass
    why = lambda sid: rows_of(app, sid)[0].low_confidence_reasons  # noqa: E731
    assert not any("audio" in r or "speech-recognition" in r for r in why(ok))
    assert "audio recording missing" in why(gone)
    assert any("speech-recognition confidence" in r for r in why(shaky))
    offsets = rows_of(app, ok)[0].dims["conceptual"]["evidence_ms"]
    assert offsets and all(ms is not None and ms % 10_000 == 0 for ms in offsets), "evidence turns map to audio offsets"


def test_several_workers_score_every_session_exactly_once(env):
    app, client, clock, codes = env
    sids = [ended_session(client, clock, codes, student_id=s)[0] for s in ("S1", "S2", "S3", "S4", "S5", "S6")]
    errors, outcomes = [], []

    def work(name):
        try:
            with db_of(app) as db:
                outcomes.append(run_pass(db, name, clock, MOCK))
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=work, args=(f"w{i}",)) for i in range(3)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors
    assert sum(o.get("scored", 0) for o in outcomes) == 6
    for sid in sids:
        assert [r.run for r in rows_of(app, sid)] == [1, 2, 3] and status_of(app, sid) == "scored" and job_of(app, sid).attempts == 1
