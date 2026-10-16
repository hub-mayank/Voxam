import json
import uuid

import pytest
from sqlalchemy import select

from app.api.main import create_app, openapi_json
from app.api.settings import Settings
from app.db import models as m
from app.services.secrets_util import sign_audio
from harness import (IYER, LONG, RAO, SAMPLE_BANK, answer, auth, begin, build, db_of, ended_session, join, make_viva, mark_scored,
                     settings_for)

CSV_BANK = ("id,topic,type,difficulty,text,key_points\n"
            + "".join(f"c{i},t{i},concept,{1 + i % 3},Concept question {i}?,a|b|c\n" for i in range(7))
            + "".join(f"a{i},t{i},applied,2,Applied question {i}?,x|y\n" for i in range(3)))


@pytest.fixture()
def env(tmp_path):
    app, client, clock = build(tmp_path)
    codes = make_viva(client, students=("S1", "S2", "S3"))
    return app, client, clock, codes


# ---------- startup and auth ----------

def test_real_mode_refuses_to_start_without_its_secrets(tmp_path):
    with pytest.raises(ValueError, match="AUDIO_SIGNING_SECRET"):
        create_app(settings_for(tmp_path, audio_signing_secret=""))
    with pytest.raises(ValueError, match="ACCESS_CODE_PEPPER"):
        create_app(settings_for(tmp_path, access_code_pepper="short"))
    create_app(settings_for(tmp_path, access_code_pepper="", require_access_code=False))  # codes off: no pepper needed
    create_app(Settings({}, contract_stub=True))  # the mock backend needs no secrets


def test_real_openapi_is_the_frozen_contract(tmp_path):
    real = create_app(settings_for(tmp_path))
    assert openapi_json(real) == (__import__("pathlib").Path(__file__).resolve().parents[2] / "docs" / "openapi.json").read_text()


def test_stub_mode_still_serves_examples_with_the_header(tmp_path):
    app = create_app(Settings({"tok-rao-0123456789": "dr-rao"}, contract_stub=True))
    from fastapi.testclient import TestClient
    r = TestClient(app).get("/faculty/vivas", headers=RAO)
    assert r.status_code == 200 and r.headers["x-contract-stub"] == "1" and r.json()["items"][0]["id"] == "dsa-midterm-2026"


def test_real_mode_has_no_stub_header_and_needs_real_tokens(env):
    app, client, clock, codes = env
    r = client.get("/faculty/vivas", headers=RAO)
    assert r.status_code == 200 and "x-contract-stub" not in r.headers
    assert client.get("/faculty/vivas", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/faculty/vivas", headers=auth("st_" + "a" * 43)).status_code == 403
    assert client.get("/faculty/vivas", headers={**RAO, "X-Mock-Error": "internal_error"}).status_code == 200, "no mock errors in real mode"


# ---------- vivas ----------

def test_create_viva_records_the_creator_from_the_token_and_rejects_duplicates(env):
    app, client, clock, codes = env
    v = client.get("/faculty/vivas/demo-viva", headers=RAO).json()
    assert v["created_by"] == "dr-rao" and v["question_count"] == 7 and v["roster_count"] == 3
    assert v["config"]["duration_ms"] == 900_000 and v["results_visible_to_students"] is False
    dup = client.post("/faculty/vivas", headers=IYER, json={"viva_id": "demo-viva", "title": "x", "subject": "s", "topics": ["a"], "difficulty": "easy"})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "already_exists"
    auto = client.post("/faculty/vivas", headers=IYER, json={"title": "x", "subject": "s", "topics": ["a"], "difficulty": "hard"}).json()
    assert auto["id"].startswith("viva-") and auto["created_by"] == "dr-iyer"
    assert client.get("/faculty/vivas/nope", headers=RAO).json()["error"]["code"] == "not_found"
    assert {x["id"] for x in client.get("/faculty/vivas", headers=RAO).json()["items"]} == {"demo-viva", auto["id"]}


def test_session_counts_follow_the_sessions(env):
    app, client, clock, codes = env
    begin(client, codes["S1"], "S1")
    join(client, codes["S2"], student_id="S2")
    assert client.get("/faculty/vivas/demo-viva", headers=RAO).json()["session_counts"] == {"in_progress": 1, "created": 1}


# ---------- question bank ----------

def put_bank(client, name, data, viva="demo-viva"):
    return client.post(f"/faculty/vivas/{viva}/questions", headers=RAO, files={"file": (name, data, "application/octet-stream")})


def fresh_viva(client, viva="empty-viva"):
    client.post("/faculty/vivas", headers=RAO, json={"viva_id": viva, "title": "t", "subject": "s", "topics": ["a"], "difficulty": "easy"})
    return viva


def test_bank_upload_csv_and_json_and_warnings(env):
    app, client, clock, codes = env
    v = fresh_viva(client)
    r = put_bank(client, "bank.csv", CSV_BANK.encode(), v)
    assert r.status_code == 200 and (r.json()["concept_count"], r.json()["applied_count"], r.json()["warnings"]) == (7, 3, [])
    assert [q for q in r.json()["items"] if q["id"] == "c0"][0]["key_points"] == ["a", "b", "c"], "listed in id order"
    small = put_bank(client, "b.json", SAMPLE_BANK, v).json()
    assert small["concept_count"] == 5 and small["applied_count"] == 2 and "small" in small["warnings"][0]
    assert client.get(f"/faculty/vivas/{v}/questions", headers=RAO).json() == small, "an upload replaces the bank"


def test_syllabus_generation_saves_only_reviewable_drafts_and_approval_uses_existing_flow(env):
    app, client, clock, codes = env
    v = fresh_viva(client, "generated-viva")

    class DraftModel:
        def __init__(self): self.calls = []
        def complete_json(self, system, user, max_tokens, kind):
            self.calls.append((system, user, max_tokens, kind))
            return [{"topic": "a", "type": "concept" if i < 2 else "applied", "difficulty": 2, "text": f"Explain concept {i}?",
                     "key_points": ["definition", "example", "trade-off"]} for i in range(3)]

    model = DraftModel()
    app.state.llm_factory = lambda spec: model
    syllabus = "Arrays, hashing, and collision handling"
    response = client.post(f"/faculty/vivas/{v}/questions/generate", headers=RAO, json={"syllabus": syllabus, "count": 3})
    assert response.status_code == 200, response.text
    questions = response.json()["items"]
    assert len(questions) == 3 and len({q["id"] for q in questions}) == 3
    assert {kind: sum(q["type"] == kind for q in questions) for kind in ("concept", "applied")} == {"concept": 2, "applied": 1}
    assert all(q["source"] == "ai-draft" and q["approved_by"] is None for q in questions)
    assert model.calls[0][2:] == (540, "generate") and syllabus in model.calls[0][1]
    assert syllabus not in str(client.get(f"/faculty/vivas/{v}/questions", headers=RAO).json())
    from app.services.core import bank_of
    with db_of(app) as db:
        assert bank_of(db, v) == [], "students must not receive AI drafts before faculty approval"
    approved = client.post(f"/faculty/vivas/{v}/questions/approve", headers=RAO,
                           json={"question_ids": [questions[0]["id"]]}).json()["items"]
    assert next(q for q in approved if q["id"] == questions[0]["id"])["approved_by"] == "dr-rao"
    assert next(q for q in approved if q["id"] == questions[1]["id"])["source"] == "ai-draft"
    with db_of(app) as db:
        assert [q["id"] for q in bank_of(db, v)] == [questions[0]["id"]]


def test_question_generation_is_bounded_locked_after_join_and_atomic_on_bad_model_output(env):
    app, client, clock, codes = env
    v = fresh_viva(client, "broken-generated-viva")
    app.state.llm_factory = lambda spec: type("BadModel", (), {"complete_json": lambda *args, **kwargs: []})()
    bad = client.post(f"/faculty/vivas/{v}/questions/generate", headers=RAO, json={"syllabus": "Arrays", "count": 2})
    assert bad.status_code == 503 and bad.json()["error"]["code"] == "provider_unavailable"
    assert client.get(f"/faculty/vivas/{v}/questions", headers=RAO).json()["items"] == []
    assert client.post(f"/faculty/vivas/{v}/questions/generate", headers=RAO, json={"syllabus": "  ", "count": 1}).status_code == 422
    assert client.post(f"/faculty/vivas/{v}/questions/generate", headers=RAO, json={"syllabus": "Arrays", "count": 21}).status_code == 422
    join(client, codes["S1"])
    locked = client.post("/faculty/vivas/demo-viva/questions/generate", headers=RAO, json={"syllabus": "Arrays", "count": 1})
    assert locked.status_code == 409 and locked.json()["error"]["details"]["reason"] == "students_joined"


def test_a_bad_bank_upload_changes_nothing_and_reports_every_row(env):
    app, client, clock, codes = env
    v = fresh_viva(client)
    assert put_bank(client, "b.csv", CSV_BANK.encode(), v).status_code == 200
    before = client.get(f"/faculty/vivas/{v}/questions", headers=RAO).json()
    bad = ("id,topic,type,difficulty,text,key_points\n"
           "q1,a,concept,1,Fine question?,x\n"
           "q2,a,weird,9,,x\n"
           "q1,a,concept,1,Duplicate id?,x\n")
    r = put_bank(client, "b.csv", bad.encode(), v)
    rows = r.json()["error"]["details"]["rows"]
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_upload"
    assert {(x["row"], x["field"]) for x in rows} >= {(2, "type"), (2, "difficulty"), (2, "text"), (3, "id")}
    assert client.get(f"/faculty/vivas/{v}/questions", headers=RAO).json() == before, "atomic: the old bank is untouched"
    for name, data, field in [("b.csv", b"id,topic\nq,t\n", "type"), ("b.txt", b"x", "file"), ("b.json", b"{not json", "file"),
                              ("b.json", b'{"a": 1}', "file"), ("b.json", b"[]", "file"), ("b.csv", b"\xff\xfe", "file"),
                              ("b.csv", b"x" * 1_000_002, "file")]:
        err = put_bank(client, name, data, v)
        assert err.status_code == 422 and err.json()["error"]["code"] == "invalid_upload", (name, err.text[:100])
        assert any(x["field"] == field for x in err.json()["error"]["details"]["rows"]), (name, err.json())
    assert client.get(f"/faculty/vivas/{v}/questions", headers=RAO).json() == before


def test_the_bank_is_locked_once_a_student_has_joined(env):
    app, client, clock, codes = env
    join(client, codes["S1"])
    r = put_bank(client, "b.json", SAMPLE_BANK)
    assert r.status_code == 409 and r.json()["error"]["details"]["reason"] == "students_joined"


def drafted_viva(client, viva="draft-viva"):
    """A viva whose bank is the CSV bank with its first three concept questions marked ai-draft."""
    fresh_viva(client, viva)
    head, *rows = CSV_BANK.strip().split("\n")
    lines = [head + ",source"] + [r + (",ai-draft" if i < 3 else ",") for i, r in enumerate(rows)]
    assert put_bank(client, "bank.csv", "\n".join(lines).encode(), viva).status_code == 200
    return viva


def approve(client, viva, body, headers=RAO):
    return client.post(f"/faculty/vivas/{viva}/questions/approve", headers=headers, json=body)


def sources(client, viva):
    return {q["id"]: (q["source"], q["approved_by"]) for q in client.get(f"/faculty/vivas/{viva}/questions", headers=RAO).json()["items"]}


def test_approving_some_drafts_sets_source_and_the_reviewer_from_the_token(env):
    app, client, clock, codes = env
    v = drafted_viva(client)
    assert sorted(i for i, (src, _) in sources(client, v).items() if src == "ai-draft") == ["c0", "c1", "c2"]
    r = approve(client, v, {"question_ids": ["c0", "c2"]}, IYER)
    assert r.status_code == 200
    got = sources(client, v)
    assert got["c0"] == ("bank", "dr-iyer") and got["c2"] == ("bank", "dr-iyer") and got["c1"] == ("ai-draft", None)
    assert [q["id"] for q in r.json()["items"]] == sorted(got), "returns the whole bank"


def test_approving_with_no_ids_approves_every_draft_and_is_idempotent(env):
    app, client, clock, codes = env
    v = drafted_viva(client)
    approve(client, v, {"question_ids": ["c0"]}, IYER)
    assert approve(client, v, {}, RAO).status_code == 200
    got = sources(client, v)
    assert {src for src, _ in got.values()} == {"bank"}
    assert got["c0"][1] == "dr-iyer", "the first approver stays"
    assert got["c1"][1] == "dr-rao" and got["a0"] == ("bank", None), "uploaded bank questions are not touched"
    before = got
    assert approve(client, v, {"question_ids": ["c1", "c1"]}, IYER).status_code == 200
    assert sources(client, v) == before


def test_an_unknown_id_is_a_404_and_nothing_changes(env):
    app, client, clock, codes = env
    v = drafted_viva(client)
    before = sources(client, v)
    r = approve(client, v, {"question_ids": ["c0", "nope"]})
    assert r.status_code == 404 and r.json()["error"]["details"]["ids"] == ["nope"]
    assert sources(client, v) == before
    assert approve(client, "no-such-viva", {}).status_code == 404
    assert approve(client, v, {"question_ids": []}).status_code == 422, "an empty list is a mistake, not 'all'"


def test_approval_is_locked_once_a_student_has_joined(env):
    app, client, clock, codes = env
    join(client, codes["S1"])
    r = approve(client, "demo-viva", {})
    assert r.status_code == 409 and r.json()["error"]["details"]["reason"] == "students_joined"


def test_only_faculty_can_approve(env):
    app, client, clock, codes = env
    v = drafted_viva(client)
    sid, student, _ = join(client, codes["S1"], viva_id="demo-viva")
    assert approve(client, v, {}, student).status_code == 403
    assert approve(client, v, {}, {}).status_code == 401
    assert {src for src, _ in sources(client, v).values()} == {"ai-draft", "bank"} and sources(client, v)["c0"][0] == "ai-draft"


# ---------- roster and codes ----------

def test_roster_upload_returns_codes_once_and_stores_only_hashes(env):
    app, client, clock, codes = env
    assert set(codes) == {"S1", "S2", "S3"} and all(len(c) == 9 and c[4] == "-" for c in codes.values())
    listing = client.get("/faculty/vivas/demo-viva/roster", headers=RAO)
    assert all("access_code" not in item for item in listing.json()["items"]), "the list has no code field (access_code_active is only a flag)"
    assert all(codes[c] not in listing.text for c in codes)
    csv = b"student_id,name\nS1,Student S1\nS4,New Student\n"
    r = client.post("/faculty/vivas/demo-viva/roster", headers=RAO, files={"file": ("r.csv", csv, "text/csv")}).json()
    assert (r["created"], r["unchanged"]) == (1, 1)
    by = {i["student_id"]: i for i in r["items"]}
    assert by["S1"]["outcome"] == "unchanged" and by["S1"]["access_code"] is None
    assert by["S4"]["outcome"] == "created" and by["S4"]["access_code"]
    assert client.post("/student/join", json={"viva_id": "demo-viva", "student_id": "S1", "access_code": codes["S1"]}).status_code == 200, "old codes survive"
    with db_of(app) as db:
        text = json.dumps([[c.code_hash, c.student_id] for c in db.query(m.AccessCode)])
        assert not any(c in text for c in list(codes.values()) + [by["S4"]["access_code"]])


def test_a_bad_roster_changes_nothing(env):
    app, client, clock, codes = env
    bad = b"student_id,name\nS9,A\n,B\nS9,C\n" + b"X" * 41 + b",D\n"
    r = client.post("/faculty/vivas/demo-viva/roster", headers=RAO, files={"file": ("r.csv", bad, "text/csv")})
    rows = r.json()["error"]["details"]["rows"]
    assert r.status_code == 422 and {(x["row"], x["field"]) for x in rows} == {(2, "student_id"), (3, "student_id"), (4, "student_id")}
    assert [i["student_id"] for i in client.get("/faculty/vivas/demo-viva/roster", headers=RAO).json()["items"]] == ["S1", "S2", "S3"]
    assert client.post("/faculty/vivas/demo-viva/roster", headers=RAO, files={"file": ("r.csv", b"name\nA\n", "text/csv")}).status_code == 422


def test_reset_code_revokes_the_old_one_and_is_refused_after_the_end(env):
    app, client, clock, codes = env
    new = client.post("/faculty/vivas/demo-viva/roster/S2/reset-code", headers=RAO).json()
    assert new["student_id"] == "S2" and new["access_code"] != codes["S2"]
    assert client.post("/student/join", json={"viva_id": "demo-viva", "student_id": "S2", "access_code": codes["S2"]}).status_code == 403
    clock.advance(1)  # the wrong (old) code earned a one second delay
    assert client.post("/student/join", json={"viva_id": "demo-viva", "student_id": "S2", "access_code": new["access_code"]}).status_code == 200
    assert client.post("/faculty/vivas/demo-viva/roster/NOPE/reset-code", headers=RAO).json()["error"]["code"] == "not_found"
    ended_session(client, clock, codes, "S1")
    r = client.post("/faculty/vivas/demo-viva/roster/S1/reset-code", headers=RAO)
    assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_state"
    with db_of(app) as db:
        active = db.query(m.AccessCode).filter_by(student_id="S2", revoked_at=None).count()
        assert active == 1


# ---------- sessions, scoring view, override, review ----------

def test_session_detail_aggregates_the_runs_and_shows_the_transcript(env):
    app, client, clock, codes = env
    sid, _ = ended_session(client, clock, codes)
    mark_scored(app, sid)
    d = client.get(f"/faculty/sessions/{sid}", headers=RAO).json()
    s = d["scoring"]
    assert d["status"] == "scored" and d["student_name"] == "Student S1" and d["low_confidence"] is False and d["needs_review"] is False
    assert [r["total"] for r in s["runs"]] == [71.0, 68.0, 71.0] and s["median_total"] == 71.0 and s["total_spread"] == 3.0
    practical = next(x for x in s["dimensions"] if x["key"] == "practical")
    assert (practical["score"], practical["score_min"], practical["score_max"], practical["weight"]) == (4, 3, 4, 15)
    assert practical["reason"] == "practical reason (run 1)", "reason comes from the run holding the median total"
    assert len(s["feedback"]) == 3 and d["effective_total"] == 71.0 and d["effective_source"] == "ai"
    assert d["overrides"] == [] and d["reviews"] == []
    assert [t["idx"] for t in d["turns"]] == list(range(len(d["turns"]))) and d["turns"][0]["action"] == "open"
    assert d["audio"] == {"available": False, "url": None, "content_type": None, "duration_ms": None, "size_bytes": None, "expires_at": None}


def test_override_wins_and_is_logged_with_the_reviewer_from_the_token(env):
    app, client, clock, codes = env
    sid, _ = ended_session(client, clock, codes)
    mark_scored(app, sid)
    url = f"/faculty/sessions/{sid}/override"
    first = client.post(url, headers=RAO, json={"new_total": 80, "reason": "great project explanation"})
    assert first.status_code == 201 and first.json()["effective_total"] == 80
    assert first.json()["override"]["reviewer"] == "dr-rao" and first.json()["override"]["old_total"] == 71.0
    second = client.post(url, headers=IYER, json={"new_total": 65.5, "reason": "second look: too generous"}).json()
    assert second["override"]["reviewer"] == "dr-iyer" and second["override"]["old_total"] == 80.0, "old_total is the effective total before"
    d = client.get(f"/faculty/sessions/{sid}", headers=RAO).json()
    assert d["effective_total"] == 65.5 and d["effective_source"] == "override" and d["scoring"]["median_total"] == 71.0
    assert [(o["reviewer"], o["old_total"], o["new_total"]) for o in d["overrides"]] == [("dr-rao", 71.0, 80.0), ("dr-iyer", 80.0, 65.5)]
    row = client.get("/faculty/vivas/demo-viva/sessions", headers=RAO).json()["items"][0]
    assert row["effective_total"] == 65.5 and row["ai_total"] == 71.0 and row["overridden"] is True
    assert client.post(url, headers=RAO, json={"new_total": 101, "reason": "too high"}).status_code == 422
    assert client.post(url, headers=RAO, json={"new_total": 50, "reason": "x"}).status_code == 422, "a reason is required"


def test_override_needs_a_scored_or_failed_session(env):
    app, client, clock, codes = env
    sid, _ = begin(client, codes["S1"])
    r = client.post(f"/faculty/sessions/{sid}/override", headers=RAO, json={"new_total": 50, "reason": "no way"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_state"
    assert client.post(f"/faculty/sessions/{uuid.uuid4()}/override", headers=RAO, json={"new_total": 50, "reason": "no way"}).status_code == 404
    failed, _ = ended_session(client, clock, codes, "S2")
    with db_of(app) as db:
        db.get(m.Session, uuid.UUID(failed)).status = "failed"
        db.commit()
    r = client.post(f"/faculty/sessions/{failed}/override", headers=RAO, json={"new_total": 55, "reason": "scored by hand"})
    assert r.status_code == 201 and r.json()["override"]["old_total"] is None, "a failed session can be marked by hand"


def test_review_clears_the_mandatory_review_flag_and_is_logged(env):
    app, client, clock, codes = env
    sid, _ = ended_session(client, clock, codes)
    mark_scored(app, sid, low=True, reasons=["very short answers on average"])
    d = client.get(f"/faculty/sessions/{sid}", headers=RAO).json()
    assert d["low_confidence"] is True and d["needs_review"] is True and d["low_confidence_reasons"] == ["very short answers on average"]
    flagged = client.get("/faculty/vivas/demo-viva/sessions?low_confidence=true", headers=RAO).json()["items"]
    assert [x["needs_review"] for x in flagged] == [True]
    r = client.post(f"/faculty/sessions/{sid}/review", headers=IYER, json={"note": "listened to the audio, mark is fair"})
    assert r.status_code == 201 and r.json()["needs_review"] is False and r.json()["review"]["reviewer"] == "dr-iyer"
    d = client.get(f"/faculty/sessions/{sid}", headers=RAO).json()
    assert d["low_confidence"] is True, "the AI's flag stays; only the review requirement is cleared"
    assert d["needs_review"] is False and d["effective_total"] == 71.0 and d["overrides"] == []
    assert [(x["reviewer"], x["note"]) for x in d["reviews"]] == [("dr-iyer", "listened to the audio, mark is fair")]
    in_progress, _ = begin(client, codes["S2"], "S2")
    assert client.post(f"/faculty/sessions/{in_progress}/review", headers=RAO, json={"note": "too early"}).status_code == 409


def test_an_override_also_clears_the_review_requirement(env):
    app, client, clock, codes = env
    sid, _ = ended_session(client, clock, codes)
    mark_scored(app, sid, low=True)
    client.post(f"/faculty/sessions/{sid}/override", headers=RAO, json={"new_total": 60, "reason": "marked by hand"})
    assert client.get(f"/faculty/sessions/{sid}", headers=RAO).json()["needs_review"] is False


def test_rescore_goes_back_to_ended_and_queues_a_job(env):
    app, client, clock, codes = env
    sid, _ = ended_session(client, clock, codes)
    assert client.post(f"/faculty/sessions/{sid}/rescore", headers=RAO).status_code == 409, "an ended session is already waiting for scoring"
    mark_scored(app, sid)
    with db_of(app) as db:
        job = db.scalar(select(m.Job))
        job.status, job.attempts = "done", 2
        db.commit()
    r = client.post(f"/faculty/sessions/{sid}/rescore", headers=RAO)
    assert r.status_code == 202 and r.json() == {"session_id": sid, "status": "ended", "job_status": "queued"}
    with db_of(app) as db:
        jobs = db.scalars(select(m.Job)).all()
        assert [(j.status, j.attempts) for j in jobs] == [("queued", 0)], "same row reset, not a second job"
        assert db.get(m.Session, uuid.UUID(sid)).status == "ended"
    assert client.post(f"/faculty/sessions/{sid}/rescore", headers=RAO).status_code == 409
    in_progress, _ = begin(client, codes["S2"], "S2")
    assert client.post(f"/faculty/sessions/{in_progress}/rescore", headers=RAO).status_code == 409


def test_session_list_filters_search_and_cursor_pagination(env):
    app, client, clock, codes = env
    for sid_ in ("S1", "S2", "S3"):
        clock.advance(10)
        begin(client, codes[sid_], sid_)
    url = "/faculty/vivas/demo-viva/sessions"
    page1 = client.get(f"{url}?limit=2", headers=RAO).json()
    assert [i["student_id"] for i in page1["items"]] == ["S3", "S2"] and page1["next_cursor"]
    page2 = client.get(f"{url}?limit=2&cursor={page1['next_cursor']}", headers=RAO).json()
    assert [i["student_id"] for i in page2["items"]] == ["S1"] and page2["next_cursor"] is None
    assert [i["student_id"] for i in client.get(f"{url}?search=student s2", headers=RAO).json()["items"]] == ["S2"]
    assert [i["student_id"] for i in client.get(f"{url}?search=S3", headers=RAO).json()["items"]] == ["S3"]
    assert client.get(f"{url}?search=%25", headers=RAO).json()["items"] == [], "% is a literal, not a wildcard"
    assert len(client.get(f"{url}?status=in_progress", headers=RAO).json()["items"]) == 3
    assert client.get(f"{url}?status=scored", headers=RAO).json()["items"] == []
    assert client.get(f"{url}?cursor=garbage", headers=RAO).status_code == 422
    assert client.get("/faculty/vivas/nope/sessions", headers=RAO).status_code == 404


def test_students_who_left_are_ended_and_queued_when_faculty_look(env):
    app, client, clock, codes = env
    sid, _ = begin(client, codes["S1"])
    clock.advance(2000)
    row = client.get("/faculty/vivas/demo-viva/sessions", headers=RAO).json()["items"][0]
    assert row["status"] == "ended" and row["ended_at"] == "2026-10-12T05:45:00Z"
    with db_of(app) as db:
        assert db.query(m.Job).count() == 1


# ---------- audio ----------

def wav_file(tmp_path, seconds=2):
    import wave
    path = tmp_path / "rec.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x01" * 8000 * seconds)
    return path


def test_audio_is_404_in_text_mode(env):
    app, client, clock, codes = env
    sid, _ = begin(client, codes["S1"])
    r = client.get(f"/faculty/sessions/{sid}/audio", headers=RAO)
    assert r.status_code == 404 and r.json()["error"]["code"] == "audio_not_available"


def test_audio_signed_url_range_and_expiry(env, tmp_path):
    app, client, clock, codes = env
    sid, _ = begin(client, codes["S1"])
    path = wav_file(tmp_path)
    with db_of(app) as db:
        db.get(m.Session, uuid.UUID(sid)).audio_uri = str(path)
        db.commit()
    audio = client.get(f"/faculty/sessions/{sid}", headers=RAO).json()["audio"]
    assert audio["available"] and audio["content_type"] == "audio/wav" and audio["duration_ms"] == 2000 and audio["size_bytes"] == path.stat().st_size
    assert audio["expires_at"] == "2026-10-12T05:45:00Z"
    full = client.get(audio["url"])  # no Authorization header, like an <audio> tag
    assert full.status_code == 200 and full.content == path.read_bytes() and full.headers["accept-ranges"] == "bytes"
    part = client.get(audio["url"], headers={"Range": "bytes=100-199"})
    assert part.status_code == 206 and part.content == path.read_bytes()[100:200] and part.headers["content-range"] == f"bytes 100-199/{path.stat().st_size}"
    assert client.get(audio["url"], headers={"Range": "bytes=99999999-"}).status_code == 416
    assert client.get(f"/faculty/sessions/{sid}/audio", headers=RAO).status_code == 200, "a faculty token works too"
    exp, sig = audio["url"].split("exp=")[1].split("&sig=")
    flipped = sig[:-1] + ("1" if sig[-1] == "0" else "0")  # always a different signature
    assert client.get(f"/faculty/sessions/{sid}/audio?exp={exp}&sig={flipped}").status_code == 401, "tampered signature"
    assert client.get(f"/faculty/sessions/{sid}/audio?exp={int(exp) + 60}&sig={sig}").status_code == 401, "expiry is covered by the signature"
    other = uuid.uuid4()
    assert client.get(f"/faculty/sessions/{other}/audio?exp={exp}&sig={sig}").status_code == 401, "signature is bound to the session"
    clock.advance(901)
    assert client.get(audio["url"]).status_code == 401, "expired"
    secret = app.state.settings.audio_signing_secret
    assert sig == sign_audio(secret, uuid.UUID(sid), int(exp))


# ---------- results, export ----------

def test_student_results_are_released_by_faculty_and_show_the_final_total(env):
    app, client, clock, codes = env
    sid, h = ended_session(client, clock, codes)
    url = f"/student/sessions/{sid}/result"
    assert client.get(url, headers=h).json()["error"]["code"] == "results_not_released"
    assert client.patch("/faculty/vivas/demo-viva", headers=RAO, json={"results_visible_to_students": True}).json()["results_visible_to_students"] is True
    early = client.get(url, headers=h)
    assert early.status_code == 409 and early.json()["error"]["details"]["required_status"] == "scored"
    mark_scored(app, sid)
    r = client.get(url, headers=h).json()
    assert r["total"] == 71.0 and r["overridden"] is False and len(r["feedback"]) == 3
    assert {d["key"]: d["score"] for d in r["dimensions"]} == {"conceptual": 4, "depth": 3, "problem": 3, "practical": 4, "communication": 4}
    client.post(f"/faculty/sessions/{sid}/override", headers=RAO, json={"new_total": 90, "reason": "exceptional"})
    assert client.get(url, headers=h).json()["total"] == 90.0 and client.get(url, headers=h).json()["overridden"] is True
    client.patch("/faculty/vivas/demo-viva", headers=RAO, json={"results_visible_to_students": False})
    assert client.get(url, headers=h).status_code == 403


def test_csv_export_has_the_marks_and_neutralises_formulas(tmp_path):
    app, client, clock = build(tmp_path)
    codes = make_viva(client, students=("S1", "=EVIL"))
    sid, _ = ended_session(client, clock, codes, "S1")
    mark_scored(app, sid)
    client.post(f"/faculty/sessions/{sid}/override", headers=RAO, json={"new_total": 80, "reason": "fair"})
    ended_session(client, clock, codes, "=EVIL")
    r = client.get("/faculty/vivas/demo-viva/export.csv", headers=RAO)
    lines = r.text.strip().split("\n")
    assert r.headers["content-type"].startswith("text/csv") and lines[0].startswith("student_id,name,status,ai_total,effective_total")
    assert lines[1].startswith("'=EVIL,") and "S1,Student S1,scored,71.0,80.0,true,false,false,4,3,3,4,4,dr-rao" in lines[2]
    assert client.get("/faculty/vivas/nope/export.csv", headers=RAO).status_code == 404


def test_revoking_a_code_stops_future_joins_keeps_the_session_and_can_be_followed_by_a_new_code(env):
    app, client, clock, codes = env
    first = client.get("/faculty/vivas/demo-viva/roster", headers=RAO).json()["items"]
    assert {i["student_id"]: i["access_code_active"] for i in first} == {"S1": True, "S2": True, "S3": True}

    r = client.post("/faculty/vivas/demo-viva/roster/S1/revoke-code", headers=RAO)
    assert r.status_code == 200 and r.json()["student_id"] == "S1" and r.json()["access_code_active"] is False
    assert "access_code" not in r.json()
    again = client.post("/faculty/vivas/demo-viva/roster/S1/revoke-code", headers=RAO)
    assert again.status_code == 200, "revoking twice is harmless"
    assert client.post("/student/join", json={"viva_id": "demo-viva", "student_id": "S1", "access_code": codes["S1"]}).status_code == 403
    others = {i["student_id"]: i["access_code_active"] for i in client.get("/faculty/vivas/demo-viva/roster", headers=RAO).json()["items"]}
    assert others == {"S1": False, "S2": True, "S3": True}

    fresh = client.post("/faculty/vivas/demo-viva/roster/S1/reset-code", headers=RAO).json()["access_code"]
    assert client.post("/student/join", json={"viva_id": "demo-viva", "student_id": "S1", "access_code": fresh}).status_code == 200


def test_revoking_an_unknown_student_or_viva_is_not_found_and_needs_a_faculty_token(env):
    app, client, clock, codes = env
    assert client.post("/faculty/vivas/demo-viva/roster/NOPE/revoke-code", headers=RAO).status_code == 404
    assert client.post("/faculty/vivas/nope/roster/S1/revoke-code", headers=RAO).status_code == 404
    assert client.post("/faculty/vivas/demo-viva/roster/S1/revoke-code").status_code == 401


def test_revoking_a_code_does_not_end_a_session_already_in_progress(env):
    from harness import begin
    app, client, clock, codes = env
    sid, headers = begin(client, codes["S2"], student_id="S2")
    client.post("/faculty/vivas/demo-viva/roster/S2/revoke-code", headers=RAO)
    status = client.get(f"/student/sessions/{sid}/status", headers=headers)
    assert status.status_code == 200 and status.json()["status"] == "in_progress", "the running viva and its token keep working"
    item = {i["student_id"]: i for i in client.get("/faculty/vivas/demo-viva/roster", headers=RAO).json()["items"]}["S2"]
    assert item["access_code_active"] is False and item["session_status"] == "in_progress"

