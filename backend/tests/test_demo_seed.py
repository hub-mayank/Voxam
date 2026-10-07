import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.main import create_app
from app.demo_seed import STUDENTS, VIVA_ID, seed
from app.db import models as m
from harness import Clock, RAO, settings_for

REAL_NOW = datetime(2026, 10, 12, 9, 0, tzinfo=timezone.utc)


@pytest.fixture()
def seeded(tmp_path):
    settings = settings_for(tmp_path)
    codes = seed(settings, lambda: REAL_NOW)
    clock = Clock(REAL_NOW + timedelta(minutes=1))
    app = create_app(settings, now=clock)
    return app, TestClient(app), clock, codes


def sessions(client):
    items = client.get(f"/faculty/vivas/{VIVA_ID}/sessions?limit=50", headers=RAO).json()["items"]
    return {i["student_id"]: i for i in items}


def test_everything_seeded_is_labelled_demo(seeded):
    app, client, clock, codes = seeded
    viva = client.get(f"/faculty/vivas/{VIVA_ID}", headers=RAO).json()
    assert viva["id"].startswith("demo-") and viva["title"].startswith("[DEMO]") and "DEMO" in viva["subject"]
    assert viva["roster_count"] == 6 and viva["question_count"] == 7
    roster = client.get(f"/faculty/vivas/{VIVA_ID}/roster", headers=RAO).json()["items"]
    assert all(r["student_id"].startswith("DEMO") and r["name"].startswith("DEMO") for r in roster)
    with app.state.sessionmaker() as db:
        assert {s.model for s in db.scalars(select(m.Score))} == {"demo-mock"}
        assert {o.reviewer for o in db.scalars(select(m.Override))} == {"demo-seed"}
        answers = [t.text for t in db.scalars(select(m.Turn).where(m.Turn.role == "student"))]
        assert answers and all(a.startswith("[demo answer]") for a in answers)


def test_the_seeded_sessions_cover_the_dashboard_states(seeded):
    app, client, clock, codes = seeded
    by = sessions(client)
    assert set(by) == {"DEMO001", "DEMO002", "DEMO003", "DEMO004", "DEMO005"}
    assert by["DEMO001"]["status"] == "scored" and by["DEMO001"]["ai_total"] is not None and by["DEMO001"]["needs_review"] is False
    assert by["DEMO002"]["status"] == "scored" and by["DEMO002"]["low_confidence"] and by["DEMO002"]["needs_review"]
    assert by["DEMO002"]["ai_total"] < by["DEMO001"]["ai_total"], "weak answers score below strong ones (mock scorer: plumbing, not quality)"
    assert by["DEMO003"]["overridden"] and by["DEMO003"]["effective_total"] == 88.0
    assert by["DEMO004"]["status"] == "in_progress" and by["DEMO005"]["status"] == "created"
    detail = client.get(f"/faculty/sessions/{by['DEMO001']['session_id']}", headers=RAO).json()
    assert len(detail["scoring"]["runs"]) == 3 and detail["scoring"]["model"] == "demo-mock" and len(detail["turns"]) > 10
    assert detail["low_confidence_reasons"] == []


def test_the_printed_codes_work_and_students_can_continue(seeded):
    app, client, clock, codes = seeded
    for student in ("DEMO004", "DEMO005", "DEMO006"):
        r = client.post("/student/join", json={"viva_id": VIVA_ID, "student_id": student, "access_code": codes[student]})
        assert r.status_code == 200, (student, r.text)
    assert client.post("/student/join", json={"viva_id": VIVA_ID, "student_id": "DEMO001", "access_code": codes["DEMO001"]}).status_code == 409
    assert [s for s, _ in STUDENTS] == list(codes)


def test_seeding_twice_refuses(seeded, tmp_path):
    app, client, clock, codes = seeded
    with pytest.raises(SystemExit, match="already exists"):
        seed(settings_for(tmp_path), lambda: REAL_NOW)


def test_the_script_needs_the_real_backends_environment():
    import subprocess
    root = Path(__file__).resolve().parents[2]
    r = subprocess.run([sys.executable, str(root / "scripts" / "seed_demo.py")], capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})
    assert r.returncode != 0 and "FACULTY_TOKENS" in r.stderr
