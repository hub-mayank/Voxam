"""Seed the viva a local run starts with: the 30-question DSA bank (AI draft, approved here for local use only) and ten LOCAL students.
Used by scripts/seed_local.py (and so by scripts/run_local.sh). No fake sessions are created: students take the viva themselves."""
import json
from pathlib import Path

from fastapi.testclient import TestClient

from .api.main import create_app
from .db import models as m

VIVA_ID = "local-dsa"
STUDENTS = [(f"LOCAL{n:02d}", f"Local Student {n:02d}") for n in range(1, 11)]
ROOT = Path(__file__).resolve().parents[2]
BANK = ROOT / "config" / "question_bank.dsa.json"


class AlreadySeeded(Exception):
    pass


def seed_local(settings, now=None) -> dict:
    """-> {student_id: access_code}. Raises AlreadySeeded when the viva exists. The faculty token's reviewer name is recorded
    as the approver of the AI-draft bank: fine for a local run, not a substitute for real faculty approval."""
    app = create_app(settings, now=now)
    client = TestClient(app)
    with app.state.sessionmaker() as db:
        if db.get(m.Viva, VIVA_ID):
            raise AlreadySeeded(VIVA_ID)
    headers = {"Authorization": f"Bearer {next(iter(settings.faculty_tokens))}"}
    topics = sorted({q["topic"] for q in json.loads(BANK.read_text())})
    made = client.post("/faculty/vivas", headers=headers, json={
        "viva_id": VIVA_ID, "title": "[LOCAL] DSA viva (local run; AI-draft bank approved for local use only)",
        "subject": "Data Structures and Algorithms", "topics": topics, "difficulty": "medium", "results_visible_to_students": True})
    assert made.status_code == 201, made.text
    up = client.post(f"/faculty/vivas/{VIVA_ID}/questions", headers=headers, files={"file": ("bank.json", BANK.read_bytes(), "application/json")})
    assert up.status_code == 200, up.text
    approved = client.post(f"/faculty/vivas/{VIVA_ID}/questions/approve", headers=headers, json={})
    assert approved.status_code == 200, approved.text
    roster = "student_id,name\n" + "".join(f"{i},{n}\n" for i, n in STUDENTS)
    issued = client.post(f"/faculty/vivas/{VIVA_ID}/roster", headers=headers, files={"file": ("roster.csv", roster.encode(), "text/csv")})
    assert issued.status_code == 200, issued.text
    return {i["student_id"]: i["access_code"] for i in issued.json()["items"]}
