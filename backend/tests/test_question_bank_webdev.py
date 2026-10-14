"""TJ-2: validate the AI-draft Web Development bank and exercise uploads and full offline vivas.
Mock answers prove bank capacity and API integration, not question quality or real-model accuracy.
"""
import json
import warnings
from pathlib import Path

import pytest

from app.clock import VivaClock
from app.config import load_bank, load_config
from app.interviewer import Interviewer
from app.llm.mock import MockLLM
from app.services.uploads import parse_bank
from harness import LONG, RAO, begin, build, finish, make_viva

ROOT = Path(__file__).resolve().parents[2]
JSON_FILE = ROOT / "config" / "question_bank.webdev.json"
CSV_FILE = JSON_FILE.with_suffix(".csv")
CFG = load_config(ROOT / "config" / "viva.config.json")


def bank():
    return json.loads(JSON_FILE.read_text())


def test_bank_has_the_requested_shape_and_topic_coverage():
    questions = bank()
    assert len(questions) == len({q["id"] for q in questions}) == 30
    assert sum(q["type"] == "concept" for q in questions) == 24
    assert sum(q["type"] == "applied" for q in questions) == 6
    openers = [q for q in questions if q["id"].startswith("o")]
    assert len(openers) == 4 and all(q["difficulty"] == 1 and q["type"] == "concept" for q in openers)
    assert sum(q["id"].startswith("c") for q in questions) == 20
    assert sum(q["id"].startswith("a") for q in questions) == 6
    assert all(q["difficulty"] in (1, 2, 3) and q["source"] == "ai-draft" for q in questions)
    assert len({q["text"] for q in questions}) == 30
    assert all(len(q["text"].split()) >= 8 for q in questions)
    assert {"html-semantics", "accessibility", "css-layout", "javascript-async", "http",
            "authentication-authorization", "database-indexes", "xss", "csrf"} <= {q["topic"] for q in questions}
    assert len({q["topic"] for q in questions}) >= 12
    assert all(3 <= len(q["key_points"]) <= 5 and all(k.strip() for k in q["key_points"]) for q in questions)


def test_question_text_does_not_quote_its_private_marking_hints():
    for q in bank():
        assert sum(k.lower() in q["text"].lower() for k in q["key_points"]) <= 1, q["id"]


def test_both_formats_load_the_same_draft_bank_without_size_warnings():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert len(load_bank(JSON_FILE)) == 30
    from_json = parse_bank(JSON_FILE.name, JSON_FILE.read_bytes())
    from_csv = parse_bank(CSV_FILE.name, CSV_FILE.read_bytes())
    assert [q.model_dump() for q in from_json] == [q.model_dump() for q in from_csv]
    assert {q.source.value for q in from_json} == {"ai-draft"}


@pytest.mark.parametrize("path,mime", [(JSON_FILE, "application/json"), (CSV_FILE, "text/csv")])
def test_upload_accepts_the_bank_without_warnings_and_preserves_draft_status(tmp_path, path, mime):
    app, client, clock = build(tmp_path)
    created = client.post("/faculty/vivas", headers=RAO, json={"viva_id": "webdev", "title": "Web Development",
                          "subject": "Web Development", "topics": sorted({q["topic"] for q in bank()}), "difficulty": "medium"})
    assert created.status_code == 201
    response = client.post("/faculty/vivas/webdev/questions", headers=RAO,
                           files={"file": (path.name, path.read_bytes(), mime)})
    assert response.status_code == 200
    body = response.json()
    assert (body["concept_count"], body["applied_count"], body["warnings"]) == (24, 6, [])
    expected = {q.id: q.model_dump(mode="json") for q in parse_bank(path.name, path.read_bytes())}
    assert len(body["items"]) == 30
    for q in body["items"]:
        assert q["approved_by"] is None
        assert {k: q[k] for k in expected[q["id"]]} == expected[q["id"]]
    stored = client.get("/faculty/vivas/webdev/questions", headers=RAO)
    assert stored.status_code == 200 and stored.json() == body
    approved = client.post("/faculty/vivas/webdev/questions/approve", headers=RAO, json={})
    assert approved.status_code == 200
    assert all(q["source"] == "bank" and q["approved_by"] == "dr-rao" for q in approved.json()["items"])


class Tick:
    t = 0.0

    def __call__(self):
        return self.t


@pytest.mark.parametrize("step", [30, 45, 60])
@pytest.mark.parametrize("answers", ["strong", "idk", "mixed"])
def test_full_simulated_viva_keeps_questions_unique_and_does_not_exhaust_the_bank(step, answers):
    tick = Tick()
    iv = Interviewer(MockLLM(), load_bank(JSON_FILE), VivaClock(CFG, now=tick), CFG, seed="webdev")
    iv.start()
    for i in range(1, 100):
        tick.t = step * i
        text = {"strong": LONG, "idk": "I don't know", "mixed": [LONG, "I don't know", "short answer", LONG][i % 4]}[answers]
        iv.respond(text)
        if iv.log[-1]["action"] == "close":
            break
    ids = [e["question_id"] for e in iv.log if e.get("action") == "new_question"]
    assert len(ids) >= 4 and len(ids) == len(set(ids))
    assert not any(e.get("action") == "bank_exhausted" for e in iv.log)
    assert not any(q.startswith("fb") for q in ids)
    assert iv.log[-1]["action"] == "close"


def test_full_simulated_viva_through_real_api_uses_the_approved_bank(tmp_path):
    app, client, clock = build(tmp_path)
    codes = make_viva(client, bank=JSON_FILE.read_bytes())
    assert client.post("/faculty/vivas/demo-viva/questions/approve", headers=RAO, json={}).status_code == 200
    sid, headers = begin(client, codes["S1"])
    last = finish(client, clock, sid, headers, step=30)
    assert last.status_code == 200 and last.json()["turn"]["ended"]
    detail = client.get(f"/faculty/sessions/{sid}", headers=RAO)
    assert detail.status_code == 200
    turns = detail.json()["turns"]
    ids = [t["question_id"] for t in turns if t["role"] == "ai" and t["action"] == "new_question"]
    assert len(ids) >= 4 and len(ids) == len(set(ids))
    assert set(ids) <= {q["id"] for q in bank()}
    with app.state.sessionmaker() as db:
        from app.db import models as m
        assert not any((t.meta or {}).get("bank_exhausted") for t in db.query(m.Turn))


def test_small_sample_bank_control_really_detects_exhaustion():
    tick = Tick()
    with pytest.warns(UserWarning, match="question bank small"):
        small = load_bank(ROOT / "config" / "question_bank.sample.json")
    iv = Interviewer(MockLLM(), small, VivaClock(CFG, now=tick), CFG, seed="webdev")
    iv.start()
    for i in range(1, 30):
        tick.t = 30 * i
        iv.respond("I don't know")
        if iv.log[-1]["action"] == "close":
            break
    assert any(e.get("action") == "bank_exhausted" for e in iv.log)
