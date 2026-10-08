"""The 30-question data-structures-and-algorithms bank. It is an AI DRAFT: every question is marked source "ai-draft" and
faculty must review it before real use. These tests check shape, that both file formats load, and that a full viva does not run it dry."""
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
JSON_FILE, CSV_FILE = ROOT / "config" / "question_bank.dsa.json", ROOT / "config" / "question_bank.dsa.csv"
CFG = load_config(ROOT / "config" / "viva.config.json")


def bank():
    return json.loads(JSON_FILE.read_text())


def test_load_bank_accepts_it_without_a_size_warning():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        loaded = load_bank(JSON_FILE)
    assert len(loaded) == 30


def test_shape_is_what_was_asked_for():
    b = bank()
    assert len(b) == 30 and len({q["id"] for q in b}) == 30
    assert sum(q["type"] == "concept" for q in b) == 24 and sum(q["type"] == "applied" for q in b) == 6
    openers = [q for q in b if q["id"].startswith("o")]
    assert len(openers) == 4 and all(q["difficulty"] == 1 and q["type"] == "concept" for q in openers), "4 easy openers"
    assert len([q for q in b if q["id"].startswith("c")]) == 20 and len([q for q in b if q["id"].startswith("a")]) == 6
    assert all(q["difficulty"] in (1, 2, 3) for q in b)
    assert all(3 <= len(q["key_points"]) <= 5 and all(k.strip() for k in q["key_points"]) for q in b)
    assert all(q["source"] == "ai-draft" for q in b), "an AI draft must say so"
    assert all(len(q["text"].split()) >= 8 for q in b) and len({q["text"] for q in b}) == 30
    assert len({q["topic"] for q in b}) >= 12, "covers a spread of topics"


def test_questions_do_not_give_the_answer_away():
    for q in bank():
        # key points are private marking hints; a question that quotes most of them would hand the answer to the student
        hits = sum(k.lower() in q["text"].lower() for k in q["key_points"])
        assert hits <= 1, q["id"]


def test_csv_and_json_hold_the_same_bank():
    from_json = parse_bank("b.json", JSON_FILE.read_bytes())
    from_csv = parse_bank("b.csv", CSV_FILE.read_bytes())
    assert [q.model_dump() for q in from_json] == [q.model_dump() for q in from_csv]
    assert {q.source.value for q in from_csv} == {"ai-draft"}


@pytest.mark.parametrize("path,mime", [(JSON_FILE, "application/json"), (CSV_FILE, "text/csv")])
def test_the_upload_endpoint_takes_it_and_keeps_the_draft_label(tmp_path, path, mime):
    app, client, clock = build(tmp_path)
    client.post("/faculty/vivas", headers=RAO, json={"viva_id": "dsa", "title": "t", "subject": "s", "topics": ["a"], "difficulty": "easy"})
    r = client.post("/faculty/vivas/dsa/questions", headers=RAO, files={"file": (path.name, path.read_bytes(), mime)})
    body = r.json()
    assert r.status_code == 200 and (body["concept_count"], body["applied_count"], body["warnings"]) == (24, 6, [])
    assert {q["source"] for q in body["items"]} == {"ai-draft"} and len(body["items"]) == 30
    assert client.get("/faculty/vivas/dsa/questions", headers=RAO).json()["items"][0]["approved_by"] is None


def test_a_bad_source_is_rejected_per_row(tmp_path):
    app, client, clock = build(tmp_path)
    client.post("/faculty/vivas", headers=RAO, json={"viva_id": "dsa", "title": "t", "subject": "s", "topics": ["a"], "difficulty": "easy"})
    bad = json.loads(JSON_FILE.read_text())
    bad[3]["source"] = "found-on-the-internet"
    r = client.post("/faculty/vivas/dsa/questions", headers=RAO, files={"file": ("b.json", json.dumps(bad).encode(), "application/json")})
    assert r.status_code == 422 and any(x["row"] == 4 and x["field"] == "source" for x in r.json()["error"]["details"]["rows"])


class Tick:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def run_viva(answer_for, step):
    tick = Tick()
    iv = Interviewer(MockLLM(), load_bank(JSON_FILE), VivaClock(CFG, now=tick), CFG, seed="dsa")
    iv.start()
    for i in range(1, 100):
        tick.t = step * i
        if tick.t >= CFG.hard_limit:
            break
        iv.respond(answer_for(i))
        if iv.log[-1]["action"] == "close":
            break
    return iv


@pytest.mark.parametrize("step", [30, 45, 60])
@pytest.mark.parametrize("answers", ["strong", "idk", "mixed"])
def test_a_full_length_viva_does_not_exhaust_the_bank(step, answers):
    pick = {"strong": lambda i: LONG, "idk": lambda i: "I don't know", "mixed": lambda i: [LONG, "I don't know", "short answer", LONG][i % 4]}[answers]
    iv = run_viva(pick, step)
    asked = [e["question_id"] for e in iv.log if e.get("action") == "new_question"]
    assert not [e for e in iv.log if e.get("action") == "bank_exhausted"], f"ran dry after {len(asked)} questions"
    assert len(asked) == len(set(asked)) and not any(a.startswith("fb") for a in asked), "no repeats and no canned fallbacks"
    assert len(asked) >= 4


def test_through_the_real_backend_too(tmp_path):
    """A viva answered every 30 s through the API (the fastest pace the clock allows) never touches the canned fallbacks."""
    app, client, clock = build(tmp_path)
    codes = make_viva(client, bank=JSON_FILE.read_bytes())
    sid, h = begin(client, codes["S1"])
    last = finish(client, clock, sid, h, step=30)
    assert last.json()["turn"]["ended"]
    turns = client.get(f"/faculty/sessions/{sid}", headers=RAO).json()["turns"]
    ids = [t["question_id"] for t in turns if t["role"] == "ai" and t["action"] == "new_question"]
    assert len(ids) == len(set(ids)) and not any(i.startswith("fb") for i in ids)
    with app.state.sessionmaker() as db:
        from app.db import models as m
        assert not [t for t in db.query(m.Turn) if (t.meta or {}).get("bank_exhausted")]


def test_the_old_sample_bank_does_run_dry_so_this_test_can_fail():
    """Control: the 7-question sample bank is exhausted by the same viva, so the check above really measures something."""
    tick = Tick()
    iv = Interviewer(MockLLM(), load_bank(ROOT / "config" / "question_bank.sample.json"), VivaClock(CFG, now=tick), CFG, seed="s")
    iv.start()
    for i in range(1, 30):
        tick.t = 30 * i
        iv.respond("I don't know")
        if iv.log[-1]["action"] == "close":
            break
    assert [e for e in iv.log if e.get("action") == "bank_exhausted"]
