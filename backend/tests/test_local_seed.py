"""The local profile's seed (scripts/run_local.sh): a viva with the approved DSA bank and ten students, ready for a real viva."""
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.main import create_app
from app.db import models as m
from app.local_seed import STUDENTS, VIVA_ID, AlreadySeeded, seed_local
from harness import RAO, settings_for

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def seeded(tmp_path):
    settings = settings_for(tmp_path)
    return settings, seed_local(settings)


def test_the_seed_creates_the_viva_the_approved_bank_and_ten_students(seeded):
    settings, codes = seeded
    app = create_app(settings)
    with app.state.sessionmaker() as db:
        questions = list(db.scalars(select(m.Question).where(m.Question.viva_id == VIVA_ID)))
        assert len(questions) == 30
        assert {(q.source, q.approved_by) for q in questions} == {("bank", "dr-rao")}, "every AI draft was approved by the faculty token"
        assert db.scalar(select(m.Viva).where(m.Viva.id == VIVA_ID)).results_visible_to_students
    assert sorted(codes) == sorted(s for s, _ in STUDENTS) and len(set(codes.values())) == 10


def test_a_seeded_student_can_start_the_viva(seeded):
    settings, codes = seeded
    client = TestClient(create_app(settings))
    j = client.post("/student/join", json={"viva_id": VIVA_ID, "student_id": "LOCAL01", "access_code": codes["LOCAL01"]}).json()
    h = {"Authorization": f"Bearer {j['session_token']}"}
    sid = j["session_id"]
    assert client.post(f"/student/sessions/{sid}/consent", headers=h, json={"accepted": True, "rules_version": j["rules_version"]}).status_code == 200
    start = client.post(f"/student/sessions/{sid}/start", headers=h).json()
    assert start["status"] == "in_progress" and start["turn"]["text"]
    assert client.get("/faculty/vivas", headers=RAO).json()["items"][0]["question_count"] == 30


def test_seeding_twice_is_refused_and_changes_nothing(seeded):
    settings, codes = seeded
    with pytest.raises(AlreadySeeded):
        seed_local(settings)
    client = TestClient(create_app(settings))
    assert client.get(f"/faculty/vivas/{VIVA_ID}/roster", headers=RAO).json()["items"].__len__() == 10


def test_the_run_script_is_valid_shell_and_keeps_its_state_out_of_git():
    assert subprocess.run(["bash", "-n", str(ROOT / "scripts" / "run_local.sh")]).returncode == 0
    ignored = subprocess.run(["git", "check-ignore", ".local/viva.db", ".local/codes.txt"], cwd=ROOT, capture_output=True, text=True)
    assert ignored.returncode == 0 and len(ignored.stdout.split()) == 2
