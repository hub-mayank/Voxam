"""Shared helpers for tests that run the real backend (SQLite file, injected clock, injected LLM)."""
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.api.settings import Settings
from app.llm.mock import MockLLM
from app.services.rules import RULES_VERSION

ROOT = Path(__file__).resolve().parents[2]
PG_BASE = None        # set by conftest with --postgres
_SCHEMAS = set()
SAMPLE_BANK = (ROOT / "config" / "question_bank.sample.json").read_bytes()
START = datetime(2026, 10, 12, 5, 30, 0, tzinfo=timezone.utc)
RAO = {"Authorization": "Bearer tok-rao-0123456789"}
IYER = {"Authorization": "Bearer tok-iyer-0123456789"}
LONG = " ".join(["word"] * 30)


class Clock:
    def __init__(self, at=START):
        self.at = at

    def __call__(self):
        return self.at

    def advance(self, seconds):
        self.at += timedelta(seconds=seconds)


class SlowMock(MockLLM):
    """MockLLM that takes a while, so concurrent requests really overlap."""
    def __init__(self, delay=0.15):
        self.delay = delay

    def complete_json(self, *a, **k):
        time.sleep(self.delay)
        return super().complete_json(*a, **k)

    def complete_text(self, *a, **k):
        time.sleep(self.delay)
        return super().complete_text(*a, **k)


class DownLLM:
    """Every provider failed."""
    name = "down"

    def complete_json(self, *a, **k):
        raise RuntimeError("all providers failed")

    def complete_text(self, *a, **k):
        raise RuntimeError("all providers failed")


def use_postgres(url):
    global PG_BASE
    from app.db.engine import normalise_url
    PG_BASE = normalise_url(url)


def db_url_for(tmp_path):
    """The database URL a test should use. SQLite file in tmp_path by default. With --postgres: a schema of its own in the test database,
    named from tmp_path, so building the app twice on the same tmp_path (a simulated restart) shares one database, like the SQLite file."""
    if PG_BASE is None:
        return f"sqlite:///{tmp_path / 'viva.db'}"
    import hashlib
    import sqlalchemy as sa
    schema = "t_" + hashlib.sha1(str(tmp_path).encode()).hexdigest()[:16]
    if schema not in _SCHEMAS:
        engine = sa.create_engine(PG_BASE)
        with engine.begin() as c:
            c.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        engine.dispose()
        _SCHEMAS.add(schema)
    return str(sa.engine.make_url(PG_BASE).update_query_dict({"options": f"-csearch_path={schema}"}).render_as_string(hide_password=False))


def drop_schemas():
    if PG_BASE is None or not _SCHEMAS:
        return
    import sqlalchemy as sa
    engine = sa.create_engine(PG_BASE)
    with engine.begin() as c:
        for schema in sorted(_SCHEMAS):
            c.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
    engine.dispose()
    _SCHEMAS.clear()


def settings_for(tmp_path, **kw):
    base = dict(faculty_tokens={"tok-rao-0123456789": "dr-rao", "tok-iyer-0123456789": "dr-iyer"},
                access_code_pepper="pepper-pepper-0123456789", audio_signing_secret="audio-secret-0123456789",
                database_url=db_url_for(tmp_path))
    return Settings(**{**base, **kw})


def build(tmp_path, clock=None, llm=lambda spec: MockLLM(), **settings_kw):
    """-> (app, client, clock). Calling build() twice with the same tmp_path is a process restart on the same database."""
    clock = clock or Clock()
    app = create_app(settings_for(tmp_path, **settings_kw), llm_factory=llm, now=clock)
    return app, TestClient(app, raise_server_exceptions=False), clock


def make_viva(client, viva_id="demo-viva", students=("S1", "S2"), bank=SAMPLE_BANK, headers=RAO):
    """Create a viva, upload the sample bank and a roster. -> {student_id: access_code}."""
    r = client.post("/faculty/vivas", headers=headers, json={"viva_id": viva_id, "title": "T", "subject": "S", "topics": ["a"], "difficulty": "easy"})
    assert r.status_code == 201, r.text
    if bank is not None:
        r = client.post(f"/faculty/vivas/{viva_id}/questions", headers=headers, files={"file": ("bank.json", bank, "application/json")})
        assert r.status_code == 200, r.text
    csv = "student_id,name\n" + "".join(f"{s},Student {s}\n" for s in students)
    r = client.post(f"/faculty/vivas/{viva_id}/roster", headers=headers, files={"file": ("roster.csv", csv.encode(), "text/csv")})
    assert r.status_code == 200, r.text
    return {i["student_id"]: i["access_code"] for i in r.json()["items"]}


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def join(client, code, viva_id="demo-viva", student_id="S1"):
    r = client.post("/student/join", json={"viva_id": viva_id, "student_id": student_id, "access_code": code})
    assert r.status_code == 200, r.text
    body = r.json()
    return body["session_id"], auth(body["session_token"]), body


def start(client, sid, headers):
    rules = client.post(f"/student/sessions/{sid}/consent", headers=headers, json={"accepted": True, "rules_version": RULES_VERSION})
    assert rules.status_code == 200, rules.text
    r = client.post(f"/student/sessions/{sid}/start", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def answer(client, sid, headers, seq, text=LONG):
    return client.post(f"/student/sessions/{sid}/answer", headers=headers, json={"text": text, "client_seq": seq})


def begin(client, code, student_id="S1", viva_id="demo-viva"):
    """join + consent + start -> (sid, headers)."""
    sid, headers, _ = join(client, code, viva_id, student_id)
    start(client, sid, headers)
    return sid, headers


def finish(client, clock, sid, headers, first_seq=1, step=60, limit=40):
    """Answer until the viva ends. -> number of answers sent."""
    for seq in range(first_seq, first_seq + limit):
        clock.advance(step)
        r = answer(client, sid, headers, seq)
        if r.status_code != 200:
            return r
        if r.json()["turn"]["ended"]:
            return r
    raise AssertionError("viva never ended")


def db_of(app):
    return app.state.sessionmaker()


KEYS = ["conceptual", "depth", "problem", "practical", "communication"]
WEIGHTS = [30, 25, 20, 15, 10]


def ended_session(client, clock, codes, student_id="S1", viva_id="demo-viva", answers=2):
    """A session that ran out of time after a couple of answers. -> (sid, student headers)."""
    sid, h = begin(client, codes[student_id], student_id, viva_id)
    for seq in range(1, answers + 1):
        clock.advance(30)
        assert answer(client, sid, h, seq).status_code == 200
    clock.advance(901)
    assert client.get(f"/student/sessions/{sid}/status", headers=h).json()["status"] == "ended"
    return sid, h


def mark_scored(app, sid, scores=((4, 3, 3, 4, 4), (4, 3, 3, 3, 4), (4, 3, 3, 4, 4)), low=False, reasons=None, status="scored"):
    """Do what the T5 worker will: write one score row per run and move the session on."""
    from uuid import UUID
    from app.db import models as m
    with db_of(app) as db:
        for run, sc in enumerate(scores, start=1):
            total = round(sum(w * s / 5 for w, s in zip(WEIGHTS, sc)), 2)
            db.add(m.Score(session_id=UUID(sid), run=run, rubric_version="rubric-v1", prompt_version="scorer-v1", model="test-model",
                           dims={k: {"score": s, "reason": f"{k} reason (run {run})", "evidence": [1, 3]} for k, s in zip(KEYS, sc)},
                           total=total, confidence=0.9, low_confidence=low, low_confidence_reasons=reasons or [],
                           feedback=[{"text": f"feedback {i}", "evidence": [1]} for i in range(3)]))
        db.get(m.Session, UUID(sid)).status = status
        db.commit()
