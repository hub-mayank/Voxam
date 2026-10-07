import threading
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.db import models as m
from app.services import core
from app.services import secrets_util
from harness import (LONG, RAO, Clock, DownLLM, SlowMock, answer, auth, begin, build, db_of, finish, join, make_viva, start)


@pytest.fixture()
def env(tmp_path):
    app, client, clock = build(tmp_path)
    codes = make_viva(client, students=("S1", "S2", "S3"))
    return app, client, clock, codes, tmp_path


def turns(app, sid):
    with db_of(app) as db:
        return [(t.idx, t.role, t.client_seq, t.action, t.model, t.prompt_version) for t in core.turns_of(db, uuid.UUID(sid))]


# ---------- the happy path and the clock ----------

def test_a_whole_viva_ends_by_itself_and_queues_scoring_in_the_same_commit(env):
    app, client, clock, codes, _ = env
    sid, h = begin(client, codes["S1"])
    last = finish(client, clock, sid, h)
    assert last.json()["status"] == "ended" and last.json()["turn"]["ended"] and last.json()["remaining_ms"] == 0
    with db_of(app) as db:
        s = db.get(m.Session, uuid.UUID(sid))
        jobs = db.scalars(select(m.Job).where(m.Job.session_id == s.id)).all()
        assert s.status == "ended" and s.ended_at is not None
        assert [(j.kind, j.status, j.attempts) for j in jobs] == [("score", "queued", 0)]
    rows = turns(app, sid)
    assert [r[0] for r in rows] == list(range(len(rows))), "idx must be contiguous: it is what scoring evidence cites"
    assert all(r[5] == "interviewer-v1" for r in rows if r[1] == "ai"), "prompt_version on every AI turn"


def test_serving_model_is_stored_on_ai_turns_that_used_a_model(env):
    app, client, clock, codes, _ = env
    sid, h = begin(client, codes["S1"])
    for seq in (1, 2):
        clock.advance(30)
        answer(client, sid, h, seq)
    ai = [r for r in turns(app, sid) if r[1] == "ai"]
    assert ai[0][3] == "open" and ai[0][4] is None, "the canned opener used no model"
    assert ai[2][4] == "mock", "a model-phrased follow-up records who served it"
    detail = client.get(f"/faculty/sessions/{sid}", headers=RAO).json()
    assert detail["turns"][4]["model"] == "mock" and detail["turns"][4]["prompt_version"] == "interviewer-v1"
    assert detail["turns"][1]["model"] is None


def test_deadline_comes_from_the_stored_start_and_status_counts_down(env):
    app, client, clock, codes, _ = env
    sid, h, _ = join(client, codes["S1"])
    first = start(client, sid, h)
    assert first["remaining_ms"] == 900_000 and first["deadline_at"] == "2026-10-12T05:45:00Z"
    clock.advance(100)
    st = client.get(f"/student/sessions/{sid}/status", headers=h).json()
    assert st["remaining_ms"] == 800_000 and st["server_now"] == "2026-10-12T05:31:40Z" and st["last_client_seq"] == 0
    assert st["current_turn"]["idx"] == 0 and st["phase"] == "warmup"


def test_start_needs_consent_and_a_bank(tmp_path):
    app, client, clock = build(tmp_path)
    codes = make_viva(client, bank=None)
    sid, h, _ = join(client, codes["S1"])
    r = client.post(f"/student/sessions/{sid}/start", headers=h)
    assert r.status_code == 409 and r.json()["error"]["details"]["required_status"] == "consented"
    client.post(f"/student/sessions/{sid}/consent", headers=h, json={"accepted": True, "rules_version": "rules-v1"})
    r = client.post(f"/student/sessions/{sid}/start", headers=h)
    assert r.status_code == 409 and "bank is empty" in r.json()["error"]["message"]


def test_consent_rules_version_decline_and_repeat(env):
    app, client, clock, codes, _ = env
    sid, h, _ = join(client, codes["S1"])
    url = f"/student/sessions/{sid}/consent"
    bad = client.post(url, headers=h, json={"accepted": True, "rules_version": "rules-v0"})
    assert bad.status_code == 409 and bad.json()["error"]["code"] == "rules_version_mismatch"
    no = client.post(url, headers=h, json={"accepted": False, "rules_version": "rules-v1"}).json()
    assert no == {"status": "created", "consent_at": None}
    yes = client.post(url, headers=h, json={"accepted": True, "rules_version": "rules-v1"}).json()
    again = client.post(url, headers=h, json={"accepted": True, "rules_version": "rules-v1"}).json()
    assert yes["status"] == "consented" and again == yes


def test_answer_before_start_is_refused(env):
    app, client, clock, codes, _ = env
    sid, h, _ = join(client, codes["S1"])
    r = answer(client, sid, h, 1)
    assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_state"


# ---------- double start and rejoin ----------

def test_double_start_returns_the_same_clock_and_opener(env):
    app, client, clock, codes, _ = env
    sid, h, _ = join(client, codes["S1"])
    first = start(client, sid, h)
    clock.advance(20)
    second = client.post(f"/student/sessions/{sid}/start", headers=h).json()
    assert second["started_at"] == first["started_at"] and second["deadline_at"] == first["deadline_at"]
    assert second["turn"] == first["turn"] and second["remaining_ms"] == 880_000
    assert len(turns(app, sid)) == 1


def test_concurrent_double_start_makes_one_opener(env):
    app, client, clock, codes, _ = env
    sid, h, _ = join(client, codes["S1"])
    client.post(f"/student/sessions/{sid}/consent", headers=h, json={"accepted": True, "rules_version": "rules-v1"})
    out = []

    def go():
        from fastapi.testclient import TestClient
        out.append(TestClient(app).post(f"/student/sessions/{sid}/start", headers=h))

    ts = [threading.Thread(target=go) for _ in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert [r.status_code for r in out] == [200] * 6
    assert len({r.json()["started_at"] for r in out}) == 1
    assert len(turns(app, sid)) == 1


def test_rejoin_mid_viva_resumes_with_a_new_token_and_kills_the_old_one(env):
    app, client, clock, codes, _ = env
    sid, old, _ = join(client, codes["S1"])
    start(client, sid, old)
    clock.advance(50)
    assert answer(client, sid, old, 1).status_code == 200
    clock.advance(10)
    sid2, new, body = join(client, codes["S1"])  # the same code works again while in progress
    assert sid2 == sid and body["resumed"] is True and body["status"] == "in_progress"
    assert client.get(f"/student/sessions/{sid}/status", headers=old).status_code == 401
    st = client.get(f"/student/sessions/{sid}/status", headers=new).json()
    assert st["last_client_seq"] == 1 and st["current_turn"]["idx"] == 2 and st["remaining_ms"] == 840_000
    clock.advance(30)
    nxt = answer(client, sid, new, st["last_client_seq"] + 1)
    assert nxt.status_code == 200 and nxt.json()["turn"]["idx"] == 4


def test_one_session_per_student_and_no_retake(env):
    app, client, clock, codes, _ = env
    sid, h = begin(client, codes["S1"])
    finish(client, clock, sid, h)
    r = client.post("/student/join", json={"viva_id": "demo-viva", "student_id": "S1", "access_code": codes["S1"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "session_ended"
    with db_of(app) as db:
        assert db.query(m.Session).filter_by(student_id="S1").count() == 1


def test_rejoin_after_the_deadline_ends_the_session_and_queues_scoring(env):
    app, client, clock, codes, _ = env
    sid, h = begin(client, codes["S1"])
    clock.advance(901)
    r = client.post("/student/join", json={"viva_id": "demo-viva", "student_id": "S1", "access_code": codes["S1"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "session_ended"
    with db_of(app) as db:
        assert db.query(m.Job).count() == 1 and db.query(m.Session).one().status == "ended"


# ---------- deadline ----------

def test_answer_after_the_deadline_is_rejected_with_the_closing_text_and_not_recorded(env):
    app, client, clock, codes, _ = env
    sid, h = begin(client, codes["S1"])
    clock.advance(30)
    assert answer(client, sid, h, 1).status_code == 200
    before = len([r for r in turns(app, sid) if r[1] == "student"])
    clock.advance(900)
    late = answer(client, sid, h, 2, text="my very late answer")
    err = late.json()["error"]
    assert late.status_code == 409 and err["code"] == "deadline_passed"
    assert err["details"]["closing_text"] and err["details"]["deadline_at"] == "2026-10-12T05:45:00Z"
    rows = turns(app, sid)
    assert len([r for r in rows if r[1] == "student"]) == before, "the late answer is not stored"
    assert rows[-1][3] == "close"
    again = answer(client, sid, h, 3)
    assert again.status_code == 409 and again.json()["error"]["code"] == "session_ended"
    with db_of(app) as db:
        assert [j.status for j in db.query(m.Job)] == ["queued"] and db.query(m.Session).one().status == "ended"


def test_status_after_the_deadline_ends_the_session(env):
    app, client, clock, codes, _ = env
    sid, h = begin(client, codes["S1"])
    clock.advance(1000)
    st = client.get(f"/student/sessions/{sid}/status", headers=h).json()
    assert st["status"] == "ended" and st["remaining_ms"] == 0


# ---------- idempotency ----------

def test_duplicate_client_seq_replays_the_same_reply_and_stores_nothing_twice(env):
    app, client, clock, codes, _ = env
    sid, h = begin(client, codes["S1"])
    clock.advance(30)
    first = answer(client, sid, h, 1).json()
    rows_after_first = turns(app, sid)
    clock.advance(30)
    second = answer(client, sid, h, 1).json()
    assert first["replayed"] is False and second["replayed"] is True
    assert second["turn"] == first["turn"] and second["client_seq"] == 1
    assert turns(app, sid) == rows_after_first


def test_client_seq_conflicts(env):
    app, client, clock, codes, _ = env
    sid, h = begin(client, codes["S1"])
    clock.advance(30)
    assert answer(client, sid, h, 1).status_code == 200
    same_seq_other_text = answer(client, sid, h, 1, text="something else")
    assert same_seq_other_text.status_code == 409 and same_seq_other_text.json()["error"]["details"]["expected"] == 2
    skip = answer(client, sid, h, 3)
    assert skip.status_code == 409 and skip.json()["error"]["code"] == "bad_client_seq" and skip.json()["error"]["details"]["expected"] == 2
    assert answer(client, sid, h, 2).status_code == 200


def test_concurrent_duplicates_produce_exactly_one_reply(tmp_path):
    app, client, clock = build(tmp_path, llm=lambda spec: SlowMock(0.15))
    codes = make_viva(client)
    sid, h = begin(client, codes["S1"])
    clock.advance(30)
    out, errors = [], []

    def go():
        from fastapi.testclient import TestClient
        try:
            out.append(TestClient(app).post(f"/student/sessions/{sid}/answer", headers=h, json={"text": LONG, "client_seq": 1}))
        except Exception as e:  # a thread failing must fail the test, not vanish
            errors.append(e)

    ts = [threading.Thread(target=go) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errors
    assert [r.status_code for r in out] == [200] * 8, [r.text for r in out if r.status_code != 200]
    bodies = [r.json() for r in out]
    assert sum(not b["replayed"] for b in bodies) == 1, "exactly one request did the work"
    assert len({(b["turn"]["idx"], b["turn"]["text"]) for b in bodies}) == 1
    rows = turns(app, sid)
    assert [r for r in rows if r[1] == "student"] == [(1, "student", 1, None, None, None)]
    assert len(rows) == 3


def test_concurrent_answers_with_different_seq_never_interleave(tmp_path):
    app, client, clock = build(tmp_path, llm=lambda spec: SlowMock(0.1))
    codes = make_viva(client)
    sid, h = begin(client, codes["S1"])
    clock.advance(30)
    out = []

    def go(seq):
        from fastapi.testclient import TestClient
        out.append(TestClient(app).post(f"/student/sessions/{sid}/answer", headers=h, json={"text": LONG, "client_seq": seq}))

    ts = [threading.Thread(target=go, args=(s,)) for s in (1, 2, 3)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(r.status_code for r in out) in ([200, 409, 409], [200, 200, 409], [200, 200, 200])
    rows = turns(app, sid)
    assert [r[0] for r in rows] == list(range(len(rows))), "no gaps or duplicates in idx"
    roles = [r[1] for r in rows]
    assert roles[0] == "ai" and all(roles[i] != roles[i + 1] for i in range(len(roles) - 1)), "ai and student strictly alternate"


# ---------- restart, crash and failure ----------

def test_kill_and_restart_continues_the_session(tmp_path):
    clock = Clock()
    app1, client1, _ = build(tmp_path, clock=clock)
    codes = make_viva(client1)
    sid, h = begin(client1, codes["S1"])
    for seq in (1, 2, 3):
        clock.advance(40)
        assert answer(client1, sid, h, seq).status_code == 200
    expected_next = None
    app1.state.engine.dispose()
    del app1, client1  # the process is gone; only the database file remains
    app2, client2, _ = build(tmp_path, clock=clock)  # new engine, new settings, new objects
    st = client2.get(f"/student/sessions/{sid}/status", headers=h).json()
    assert st["status"] == "in_progress" and st["last_client_seq"] == 3 and st["current_turn"]["idx"] == 6
    clock.advance(40)
    r = answer(client2, sid, h, 4)
    assert r.status_code == 200 and r.json()["turn"]["idx"] == 8 and r.json()["replayed"] is False
    again = answer(client2, sid, h, 3)  # a retry of an answer from before the restart still replays
    assert again.json()["replayed"] is True and again.json()["turn"]["idx"] == 6
    assert expected_next is None
    finish(client2, clock, sid, h, first_seq=5)
    assert client2.get(f"/student/sessions/{sid}/status", headers=h).json()["status"] == "ended"


class Crash(BaseException):
    """Not an Exception: nothing in the request path may swallow it, like a killed process."""


def test_crash_after_the_answer_is_stored_loses_nothing_and_a_retry_finishes_it(tmp_path):
    clock = Clock()
    boom = {"on": False}

    class MaybeCrash(SlowMock):
        def complete_json(self, *a, **k):
            if boom["on"]:
                raise Crash()
            return super().complete_json(*a, **k)

    app, client, _ = build(tmp_path, clock=clock, llm=lambda spec: MaybeCrash(0))
    codes = make_viva(client)
    sid, h = begin(client, codes["S1"])
    clock.advance(30)
    assert answer(client, sid, h, 1).status_code == 200
    boom["on"] = True
    clock.advance(30)
    from fastapi.testclient import TestClient
    with pytest.raises(Crash):  # a client that re-raises server exceptions, so the "kill" is visible
        TestClient(app).post(f"/student/sessions/{sid}/answer", headers=h, json={"text": "the answer that must survive", "client_seq": 2})
    rows = turns(app, sid)
    assert rows[-1][1] == "student" and rows[-1][2] == 2, "the student's answer is stored even though no reply was made"
    boom["on"] = False
    app2, client2, _ = build(tmp_path, clock=clock)
    skip = answer(client2, sid, h, 3)
    assert skip.status_code == 409 and skip.json()["error"]["details"]["expected"] == 2, "must resend the pending answer first"
    done = client2.post(f"/student/sessions/{sid}/answer", headers=h, json={"text": "the answer that must survive", "client_seq": 2})
    assert done.status_code == 200 and done.json()["replayed"] is False and done.json()["turn"]["idx"] == 4
    assert len([r for r in turns(app2, sid) if r[1] == "student"]) == 2, "not stored twice"


def test_a_dead_workers_lease_expires_and_another_worker_takes_over(tmp_path):
    clock = Clock()
    app, client, _ = build(tmp_path, clock=clock, answer_lease_seconds=60)
    codes = make_viva(client)
    sid, h = begin(client, codes["S1"])
    clock.advance(30)
    with db_of(app) as db:  # a worker claimed the session and died without releasing it
        db.execute(update(m.Session).values(lease_until=clock() + timedelta(seconds=60)))
        db.commit()
    from app.services.student import StudentService
    svc = StudentService(db_of(app), app.state.settings, clock, app.state.llm_factory, sleep=lambda s: clock.advance(20))
    from app.api.schemas.student import AnswerRequest
    reply = svc.answer(uuid.UUID(sid), AnswerRequest(text=LONG, client_seq=1))
    assert reply.turn.idx == 2 and reply.replayed is False


def test_when_every_model_is_down_the_student_gets_a_graceful_reply_and_nothing_is_lost(tmp_path):
    app, client, clock = build(tmp_path, llm=lambda spec: DownLLM())
    codes = make_viva(client)
    sid, h = begin(client, codes["S1"])
    clock.advance(30)
    r = answer(client, sid, h, 1)
    assert r.status_code == 200, r.text
    clock.advance(30)
    r2 = answer(client, sid, h, 2)
    assert r2.status_code == 200 and r2.json()["turn"]["text"]
    with db_of(app) as db:
        rows = core.turns_of(db, uuid.UUID(sid))
        students = [t for t in rows if t.role == "student"]
        assert [t.text for t in students] == [LONG, LONG], "both answers stored"
        ai = [t for t in rows if t.role == "ai"][1:]
        assert all(t.model is None for t in ai), "no model served these turns"
        degraded = [t for t in ai if (t.meta or {}).get("llm_degraded")]
        assert degraded and degraded[0].meta["llm_errors"], "the audit trail says why the reply was canned"
        assert any((t.meta or {}).get("classify_error") for t in ai)
    detail = client.get(f"/faculty/sessions/{sid}", headers=RAO).json()
    assert detail["turns"][2]["model"] is None


def test_ending_and_enqueueing_scoring_are_one_transaction(env, monkeypatch):
    app, client, clock, codes, _ = env
    sid, h = begin(client, codes["S1"])

    def broken(db, session_id, now):
        raise RuntimeError("queue is down")

    monkeypatch.setattr(core, "enqueue_scoring", broken)  # only called when the session ends
    for seq in range(1, 40):
        clock.advance(60)
        r = answer(client, sid, h, seq)
        if r.status_code != 200:
            break
    assert r.status_code == 500 and r.json()["error"]["code"] == "internal_error", "the closing answer hit the broken queue"
    with db_of(app) as db:
        s = db.query(m.Session).one()
        assert s.status == "in_progress" and s.ended_at is None and db.query(m.Job).count() == 0, "no half-ended session"
        assert s.lease_until is None, "the lease is released so a retry can proceed"
        last = core.turns_of(db, s.id)[-1]
        assert last.role == "student" and last.client_seq == seq, "the answer itself was stored first"
    monkeypatch.undo()
    clock.advance(1)
    done = answer(client, sid, h, seq)
    assert done.status_code == 200 and done.json()["status"] == "ended" and done.json()["replayed"] is False
    with db_of(app) as db:
        assert [j.status for j in db.query(m.Job)] == ["queued"]


# ---------- access codes and tokens ----------

def test_wrong_codes_lock_the_student_out_then_the_lockout_expires(env):
    app, client, clock, codes, _ = env
    body = {"viva_id": "demo-viva", "student_id": "S1"}
    for _ in range(3):
        r = client.post("/student/join", json={**body, "access_code": "AAAA-AAAA"})
        assert r.status_code == 403 and r.json()["error"]["code"] == "invalid_credentials"
    locked = client.post("/student/join", json={**body, "access_code": codes["S1"]})
    assert locked.status_code == 429 and locked.json()["error"]["details"]["retry_after_ms"] == 900_000, "even the right code is refused"
    assert client.post("/student/join", json={**body, "student_id": "S2", "access_code": codes["S2"]}).status_code == 200, "others are unaffected"
    clock.advance(901)
    assert client.post("/student/join", json={**body, "access_code": codes["S1"]}).status_code == 200


def test_a_success_resets_the_failure_count_and_reset_code_unlocks(env):
    app, client, clock, codes, _ = env
    body = {"viva_id": "demo-viva", "student_id": "S1"}
    client.post("/student/join", json={**body, "access_code": "AAAA-AAAA"})
    client.post("/student/join", json={**body, "access_code": "AAAA-AAAA"})
    assert client.post("/student/join", json={**body, "access_code": codes["S1"]}).status_code == 200
    for _ in range(2):
        client.post("/student/join", json={**body, "access_code": "AAAA-AAAA"})
    assert client.post("/student/join", json={**body, "access_code": "AAAA-AAAA"}).status_code == 403  # 3rd, not 5th
    assert client.post("/student/join", json={**body, "access_code": codes["S1"]}).status_code == 429
    new = client.post("/faculty/vivas/demo-viva/roster/S1/reset-code", headers=RAO).json()["access_code"]
    assert client.post("/student/join", json={**body, "access_code": codes["S1"]}).status_code == 403, "old code is dead"
    assert client.post("/student/join", json={**body, "access_code": new}).status_code == 200


def test_unknown_student_and_wrong_code_look_identical(env):
    app, client, clock, codes, _ = env
    a = client.post("/student/join", json={"viva_id": "demo-viva", "student_id": "NOPE", "access_code": codes["S1"]})
    b = client.post("/student/join", json={"viva_id": "demo-viva", "student_id": "S1", "access_code": "ZZZZ-ZZZZ"})
    c = client.post("/student/join", json={"viva_id": "no-viva", "student_id": "S1", "access_code": codes["S1"]})
    assert a.status_code == b.status_code == c.status_code == 403
    assert a.json() == b.json() == c.json()


def test_code_entry_is_forgiving_about_case_and_dashes(env):
    app, client, clock, codes, _ = env
    sloppy = codes["S1"].lower().replace("-", " ")
    assert client.post("/student/join", json={"viva_id": "demo-viva", "student_id": "S1", "access_code": sloppy}).status_code == 200


def test_codes_are_hmac_hashed_and_compared_in_constant_time(env, monkeypatch):
    app, client, clock, codes, _ = env
    with db_of(app) as db:
        hashes = [c.code_hash for c in db.query(m.AccessCode)]
    assert len(hashes) == 3 and all(len(h) == 64 for h in hashes)
    plain = {secrets_util.normalize_code(c) for c in codes.values()}
    assert not any(p in h.upper() for h in hashes for p in plain)
    pepper = app.state.settings.access_code_pepper
    assert secrets_util.hash_code(pepper, "demo-viva", "S1", codes["S1"]) in hashes
    assert secrets_util.hash_code("another-pepper-0123456789", "demo-viva", "S1", codes["S1"]) not in hashes
    assert secrets_util.hash_code(pepper, "demo-viva", "S2", codes["S1"]) not in hashes, "bound to the student"
    calls = []
    real = secrets_util.hmac.compare_digest
    monkeypatch.setattr(secrets_util.hmac, "compare_digest", lambda a, b: calls.append(1) or real(a, b))
    client.post("/student/join", json={"viva_id": "demo-viva", "student_id": "S1", "access_code": "AAAA-AAAA"})
    assert calls, "codes are compared with hmac.compare_digest"


def test_session_tokens_are_stored_hashed_and_bound_to_their_session(env):
    app, client, clock, codes, _ = env
    sid_a, ha = begin(client, codes["S1"], "S1")
    sid_b, hb = begin(client, codes["S2"], "S2")
    token_a = ha["Authorization"].split()[1]
    with db_of(app) as db:
        assert token_a not in [s.token_hash for s in db.query(m.Session)]
        assert secrets_util.hash_token(token_a) in [s.token_hash for s in db.query(m.Session)]
    r = client.get(f"/student/sessions/{sid_b}/status", headers=ha)
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    assert answer(client, sid_b, ha, 1).status_code == 403
    assert client.get(f"/student/sessions/{sid_a}/status", headers=ha).status_code == 200
    assert client.get(f"/student/sessions/{sid_a}/status", headers=auth("st_" + "x" * 43)).status_code == 401
    assert client.get(f"/student/sessions/{sid_a}/status", headers=RAO).status_code == 403
    assert client.get(f"/student/sessions/{sid_a}/status").status_code == 401


def test_codes_can_be_switched_off_for_local_dev(tmp_path):
    app, client, clock = build(tmp_path, require_access_code=False, access_code_pepper="")
    codes = make_viva(client)
    assert set(codes.values()) == {None}
    r = client.post("/student/join", json={"viva_id": "demo-viva", "student_id": "S1"})
    assert r.status_code == 200
    assert client.post("/student/join", json={"viva_id": "demo-viva", "student_id": "NOPE"}).status_code == 403


# ---------- transcript replay ----------

def test_replaying_the_stored_transcript_reproduces_every_ai_turn(env):
    """Rebuild the interviewer from the stored turns before each AI turn and answer again: same reply, same decision."""
    from app.clock import VivaClock
    from app.config import config_from_raw
    from app.interviewer import Interviewer
    from app.llm.mock import MockLLM
    app, client, clock, codes, _ = env
    sid, h = begin(client, codes["S1"])
    texts = [LONG, "short one", "I don't know", LONG, "cricket is great", LONG] * 4
    for seq, text in enumerate(texts, start=1):
        clock.advance(45)
        r = answer(client, sid, h, seq, text=text)
        if r.json()["turn"]["ended"]:
            break
    with db_of(app) as db:
        s = db.get(m.Session, uuid.UUID(sid))
        cfg = config_from_raw(db.get(m.Viva, s.viva_id).config)
        bank = core.bank_of(db, s.viva_id)
        rows = core.turns_of(db, s.id)
        checked = 0
        for ai in (t for t in rows if t.role == "ai" and t.idx > 0):
            student = rows[ai.idx - 1]
            at = lambda t=ai: t.created_at  # noqa: E731  replay at the moment the reply was made
            iv = Interviewer(MockLLM(), bank, VivaClock.resume(cfg, s.started_at, at), cfg, seed=str(s.id))
            iv.restore([core.turn_dict(t) for t in rows[:student.idx]])
            iv.respond(student.text)
            event = [e for e in iv.log if e["role"] == "ai"][-1]
            assert (event["text"], event["action"], event["question_id"], event["phase"]) == (ai.text, ai.action, ai.question_id, ai.phase), ai.idx
            checked += 1
        assert checked >= 15


# ---------- trying to break it ----------

def test_answer_input_limits_and_unicode(env):
    app, client, clock, codes, _ = env
    sid, h = begin(client, codes["S1"])
    clock.advance(30)
    assert answer(client, sid, h, 1, text="").status_code == 422
    assert answer(client, sid, h, 1, text="x" * 4001).status_code == 422
    assert client.post(f"/student/sessions/{sid}/answer", headers=h, json={"text": "hi", "client_seq": 1, "t_start_ms": -5}).status_code == 422
    assert client.post(f"/student/sessions/{sid}/answer", headers=h, content=b"not json").status_code == 422
    hinglish = "Hash table ek data structure hai jo key ko index se map karta hai 🙂 — collision handle karne ke liye chaining use hoti hai"
    r = answer(client, sid, h, 1, text=hinglish)
    assert r.status_code == 200
    assert client.get(f"/faculty/sessions/{sid}", headers=RAO).json()["turns"][1]["text"] == hinglish
    assert answer(client, sid, h, 2, text="x" * 4000).status_code == 200, "exactly at the limit is fine"


def test_twenty_students_at_once_on_sqlite(tmp_path):
    from fastapi.testclient import TestClient
    app, client, clock = build(tmp_path, llm=lambda spec: SlowMock(0.01))
    ids = tuple(f"S{i:02d}" for i in range(20))
    codes = make_viva(client, students=ids)
    results, errors = {}, []

    def one(student):
        try:
            c = TestClient(app)
            sid, h = begin(c, codes[student], student)
            codes_seen = [answer(c, sid, h, seq).status_code for seq in range(1, 6)]
            results[student] = (sid, codes_seen)
        except Exception as e:
            errors.append((student, repr(e)))

    ts = [threading.Thread(target=one, args=(s,)) for s in ids]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errors, errors
    assert all(c == [200] * 5 for _, c in results.values()), {s: c for s, (_, c) in results.items() if c != [200] * 5}
    for student, (sid, _) in results.items():
        rows = turns(app, sid)
        assert [r[0] for r in rows] == list(range(len(rows))) and len(rows) == 11, student


# ---------- through the real provider chain (retry, fallback, telemetry) ----------

def test_fallback_chain_records_the_backup_that_served_and_a_dead_chain_degrades(tmp_path, monkeypatch):
    from app.llm.fake import FakeProvider
    from app.llm.resilient import ResilientLLM
    monkeypatch.setenv("TELEMETRY_FILE", str(tmp_path / "telemetry.jsonl"))
    primary = FakeProvider(script=(503,), model="primary", data={"quality": "strong"}, text="Primary says hi.")
    backup = FakeProvider(script=("ok",), model="backup", data={"quality": "strong"}, text="Backup here, go deeper.")
    chain = lambda spec: ResilientLLM([primary, backup], retries=1, backoff=0, jitter=0, sleep=lambda s: None)  # noqa: E731
    app, client, clock = build(tmp_path, llm=chain)
    codes = make_viva(client)
    sid, h = begin(client, codes["S1"])
    clock.advance(30)
    assert answer(client, sid, h, 1).status_code == 200
    clock.advance(30)
    r = answer(client, sid, h, 2)
    assert r.status_code == 200 and r.json()["turn"]["text"] == "Backup here, go deeper."
    detail = client.get(f"/faculty/sessions/{sid}", headers=RAO).json()
    ai = [t for t in detail["turns"] if t["role"] == "ai"]
    assert ai[-1]["model"] == "fake:backup", "the fallback that really served the turn is visible to faculty"
    assert primary.calls >= 2 and backup.calls >= 1
    # now the whole chain dies: the student still gets a reply and the viva continues
    dead = FakeProvider(script=(503,), model="dead")
    (tmp_path / "second").mkdir()
    app2, client2, clock2 = build(tmp_path / "second", llm=lambda spec: ResilientLLM([dead], retries=1, backoff=0, jitter=0, sleep=lambda s: None))
    codes2 = make_viva(client2)
    sid2, h2 = begin(client2, codes2["S1"])
    for seq in (1, 2):  # the first answer only changes phase (no model call); the second needs one
        clock2.advance(30)
        r2 = answer(client2, sid2, h2, seq)
        assert r2.status_code == 200 and r2.json()["turn"]["text"]
    with db_of(app2) as db:
        flagged = [t for t in core.turns_of(db, uuid.UUID(sid2)) if (t.meta or {}).get("llm_errors")]
        assert flagged and all(t.model is None for t in flagged) and flagged[0].meta["llm_degraded"] is True
