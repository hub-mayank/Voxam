"""Seed a clearly labelled DEMO viva so the frontend can run against the real backend.
Everything here is fake: DEMO ids, DEMO students, mock-model scores. Run via scripts/seed_demo.py."""
import json
import uuid
from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from .api.main import create_app
from .config import load_config
from .db import models as m
from .llm.mock import MockLLM
from .scorer import SCORER_PROMPT_VERSION, build_transcript, confidence_flags, score_once, total_of
from .services import core
from .session_state import Event, transition

VIVA_ID = "demo-dsa"
ROOT = Path(__file__).resolve().parents[2]
STUDENTS = [("DEMO001", "DEMO Student A (strong)"), ("DEMO002", "DEMO Student B (weak, flagged)"),
            ("DEMO003", "DEMO Student C (overridden)"), ("DEMO004", "DEMO Student D (in progress)"),
            ("DEMO005", "DEMO Student E (joined, not started)"), ("DEMO006", "DEMO Student F (not joined)")]
STRONG = ("[demo answer] I would start from the requirements, then pick the data structure that fits the access pattern, explain the "
          "trade-offs between memory and speed, and finally describe how it behaves at scale and what I would measure to be sure.")
WEAK = "[demo answer] not sure"


class SeedClock:
    def __init__(self, at):
        self.at = at

    def __call__(self):
        return self.at

    def advance(self, seconds):
        self.at += timedelta(seconds=seconds)


def play(client, clock, codes, student_id, text, answers, finish, step=40):
    """Join, consent, start, give `answers` answers (or until the viva closes). finish=True lets the time run out."""
    body = client.post("/student/join", json={"viva_id": VIVA_ID, "student_id": student_id, "access_code": codes[student_id]}).json()
    sid, headers = body["session_id"], {"Authorization": f"Bearer {body['session_token']}"}
    client.post(f"/student/sessions/{sid}/consent", headers=headers, json={"accepted": True, "rules_version": body["rules_version"]})
    client.post(f"/student/sessions/{sid}/start", headers=headers)
    for seq in range(1, answers + 1):
        clock.advance(step)
        r = client.post(f"/student/sessions/{sid}/answer", headers=headers, json={"text": text, "client_seq": seq}).json()
        if r["turn"]["ended"]:
            break
    if finish:
        clock.advance(901)
        client.get(f"/student/sessions/{sid}/status", headers=headers)  # the server notices the deadline and ends the session
    return sid


def score_like_the_worker(app, sid, mock_label="demo-mock"):
    """What the T5 worker will do: three scorer runs on the stored transcript, one score row each, then status scored."""
    with app.state.sessionmaker() as db:
        s = db.get(m.Session, uuid.UUID(sid))
        viva = db.get(m.Viva, s.viva_id)
        cfg = load_config(core.DEFAULT_CONFIG_PATH)
        events = core.turns_to_events(core.turns_of(db, s.id), s.started_at)
        transcript = build_transcript(events)
        raws = [score_once(MockLLM(), cfg, transcript)[0] for _ in range(3)]
        totals = [total_of(r["dimensions"], cfg) for r in raws]
        flags = confidence_flags(events, transcript, totals)
        for run, (raw, total) in enumerate(zip(raws, totals), start=1):
            db.add(m.Score(session_id=s.id, run=run, rubric_version=viva.config["rubric"]["version"], prompt_version=SCORER_PROMPT_VERSION,
                           model=mock_label, dims=raw["dimensions"], total=total, confidence=0.5 if flags else 0.9,
                           low_confidence=bool(flags), low_confidence_reasons=flags, feedback=raw["feedback"]))
        for event in (Event.begin_scoring, Event.scored):
            s.status = transition(s.status, event).value
        for job in db.scalars(select(m.Job).where(m.Job.session_id == s.id)):
            job.status = "done"
        db.commit()


def seed(settings, real_now) -> dict:
    """-> {student_id: access_code}. Raises SystemExit if the demo viva already exists."""
    start = real_now() - timedelta(hours=3)
    clock = SeedClock(start)
    app = create_app(settings, now=clock)
    client = TestClient(app)
    with app.state.sessionmaker() as db:
        if db.get(m.Viva, VIVA_ID):
            raise SystemExit(f"{VIVA_ID!r} already exists in this database. Delete the database file to reseed, "
                             "or use POST .../reset-code to get fresh access codes.")
    token = next(iter(settings.faculty_tokens))
    headers = {"Authorization": f"Bearer {token}"}
    made = client.post("/faculty/vivas", headers=headers, json={
        "viva_id": VIVA_ID, "title": "[DEMO] DSA viva (seeded fake data, not real students)", "subject": "Data Structures and Algorithms (DEMO)",
        "topics": ["hash-tables", "complexity", "databases"], "difficulty": "medium", "results_visible_to_students": True})
    assert made.status_code == 201, made.text
    bank = (ROOT / "config" / "question_bank.sample.json").read_bytes()
    client.post(f"/faculty/vivas/{VIVA_ID}/questions", headers=headers, files={"file": ("bank.json", bank, "application/json")})
    roster = "student_id,name\n" + "".join(f"{i},{n}\n" for i, n in STUDENTS)
    issued = client.post(f"/faculty/vivas/{VIVA_ID}/roster", headers=headers, files={"file": ("roster.csv", roster.encode(), "text/csv")}).json()
    codes = {i["student_id"]: i["access_code"] for i in issued["items"]}

    a = play(client, clock, codes, "DEMO001", STRONG, 40, finish=True, step=100)
    b = play(client, clock, codes, "DEMO002", WEAK, 3, finish=True)
    c = play(client, clock, codes, "DEMO003", STRONG, 40, finish=True, step=100)
    for sid in (a, b, c):
        score_like_the_worker(app, sid)
    with app.state.sessionmaker() as db:
        db.add(m.Override(session_id=uuid.UUID(c), reviewer="demo-seed", old_total=None, new_total=88.0,
                          reason="[demo] seeded override so the history is not empty", at=clock()))
        db.commit()
    clock.at = real_now() - timedelta(minutes=4)  # the in-progress one really is in progress for the next 11 minutes
    play(client, clock, codes, "DEMO004", STRONG, 3, finish=False)
    client.post("/student/join", json={"viva_id": VIVA_ID, "student_id": "DEMO005", "access_code": codes["DEMO005"]})
    return codes
