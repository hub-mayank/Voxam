import uuid

import pytest

from app.db import models as m
from app.services.views import FAILURE_OTHER, failure_sentence
from harness import RAO, build, db_of, ended_session, make_viva, mark_scored


@pytest.fixture()
def env(tmp_path):
    app, client, clock = build(tmp_path)
    codes = make_viva(client, students=("S1", "S2"))
    return app, client, clock, codes


def fail(app, sid, error):
    with db_of(app) as db:
        job = db.query(m.Job).filter(m.Job.session_id == uuid.UUID(sid)).one()
        job.status, job.error = "failed", error
        db.get(m.Session, uuid.UUID(sid)).status = "failed"
        db.commit()


@pytest.mark.parametrize("stored, words", [
    ("scorer failed after retries: [\"dimension keys ['conceptual', 'evidence', 'reason'] != ['communication']\"]", "wrong format"),
    ("provider failed: Groq daily token budget reached", "unavailable or over its usage limit"),
    ("no student turns to score", "no answers"),
    ("session is ended, not ready to score", "not ready"),
    ("could not store scores: IntegrityError: boom", "could not be saved"),
    ("RuntimeError: something nobody planned for", FAILURE_OTHER),
    (None, FAILURE_OTHER),
])
def test_each_stored_error_becomes_one_plain_sentence(stored, words):
    assert words in failure_sentence(stored)


def test_a_failed_session_says_why_in_the_detail_and_in_the_list(env):
    app, client, clock, codes = env
    sid, _ = ended_session(client, clock, codes)
    fail(app, sid, "scorer failed after retries: [\"dimension keys ['conceptual', 'evidence', 'reason'] != ['communication']\"]")
    detail = client.get(f"/faculty/sessions/{sid}", headers=RAO).json()
    assert detail["status"] == "failed" and "wrong format" in detail["scoring_error"]
    assert "conceptual" not in detail["scoring_error"], "raw model output stays in the worker log"
    row = next(r for r in client.get("/faculty/vivas/demo-viva/sessions", headers=RAO).json()["items"] if r["session_id"] == sid)
    assert row["scoring_error"] == detail["scoring_error"]


def test_only_failed_sessions_carry_a_reason(env):
    app, client, clock, codes = env
    scored, _ = ended_session(client, clock, codes, "S1")
    mark_scored(app, scored)
    waiting, _ = ended_session(client, clock, codes, "S2")
    for sid in (scored, waiting):
        assert client.get(f"/faculty/sessions/{sid}", headers=RAO).json()["scoring_error"] is None
    assert all(r["scoring_error"] is None for r in client.get("/faculty/vivas/demo-viva/sessions", headers=RAO).json()["items"])


def test_a_failed_session_without_a_job_row_still_gets_a_sentence(env):
    app, client, clock, codes = env
    sid, _ = ended_session(client, clock, codes)
    with db_of(app) as db:
        db.query(m.Job).filter(m.Job.session_id == uuid.UUID(sid)).delete()
        db.get(m.Session, uuid.UUID(sid)).status = "failed"
        db.commit()
    assert client.get(f"/faculty/sessions/{sid}", headers=RAO).json()["scoring_error"] == FAILURE_OTHER
