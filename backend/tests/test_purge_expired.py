"""scripts/purge_expired_sessions.py: it previews by default, deletes only finished sessions at or before the cutoff, with their
rows and local recording, and refuses anything outside AUDIO_DIR."""
import importlib.util
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import func, select, update

from app.db import models as m
from harness import begin, build, db_of, finish, make_viva

ROOT = Path(__file__).resolve().parents[2]


def load_script():
    spec = importlib.util.spec_from_file_location("purge_script", ROOT / "scripts" / "purge_expired_sessions.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def world(tmp_path, monkeypatch):
    """Three students: S1 finished long ago, S2 finished recently, S3 still in progress. S1 and S2 each have a recording."""
    app, client, clock = build(tmp_path)
    codes = make_viva(client, students=("S1", "S2", "S3"))
    audio = tmp_path / "audio"
    audio.mkdir()
    sessions = {}
    for student in ("S1", "S2"):
        sid, h = begin(client, codes[student], student_id=student)
        finish(client, clock, sid, h)
        wav = audio / f"{student}.wav"
        wav.write_bytes(b"RIFF")
        sessions[student] = (sid, wav)
        with db_of(app) as db:
            db.execute(update(m.Session).where(m.Session.id == uuid.UUID(sid)).values(audio_uri=f"file://{wav}"))
            db.commit()
    sid3, _ = begin(client, codes["S3"], student_id="S3")
    sessions["S3"] = (sid3, None)
    old = datetime.now(timezone.utc) - timedelta(days=40)
    with db_of(app) as db:
        db.execute(update(m.Session).where(m.Session.id == uuid.UUID(sessions["S1"][0])).values(ended_at=old))
        db.execute(update(m.Session).where(m.Session.id == uuid.UUID(sessions["S2"][0])).values(ended_at=datetime.now(timezone.utc)))
        db.commit()
    cache = audio / "tts_cache"
    cache.mkdir()
    (cache / "a.wav").write_bytes(b"x")
    monkeypatch.setenv("DATABASE_URL", app.state.settings.database_url)
    monkeypatch.setenv("AUDIO_DIR", str(audio))
    monkeypatch.setenv("TTS_CACHE", str(cache))
    monkeypatch.setenv("AI_VIVA_NO_DOTENV", "1")
    return app, sessions, audio, cache


def counts(app):
    with db_of(app) as db:
        return {t.__tablename__: db.scalar(select(func.count()).select_from(t)) for t in (m.Session, m.Turn, m.Job, m.AccessCode, m.RosterEntry)}


def test_a_dry_run_changes_nothing(world, capsys):
    app, sessions, audio, cache = world
    before = counts(app)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    assert load_script().main(["--before", cutoff]) == 0
    assert counts(app) == before
    assert sessions["S1"][1].exists() and (cache / "a.wav").exists()
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "Eligible terminal sessions: 1" in out


def test_apply_removes_only_the_old_finished_session_with_its_rows_and_recording(world):
    app, sessions, audio, cache = world
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    assert load_script().main(["--before", cutoff, "--apply"]) == 0
    with db_of(app) as db:
        left = {s.student_id for s in db.scalars(select(m.Session))}
        assert left == {"S2", "S3"}, "the recent and the in-progress sessions stay"
        assert db.scalar(select(func.count()).select_from(m.Turn).where(m.Turn.session_id == uuid.UUID(sessions["S1"][0]))) == 0
        assert db.scalar(select(func.count()).select_from(m.Job).where(m.Job.session_id == uuid.UUID(sessions["S1"][0]))) == 0
        assert db.get(m.RosterEntry, ("demo-viva", "S1")) is None and db.get(m.RosterEntry, ("demo-viva", "S2")) is not None
    assert not sessions["S1"][1].exists() and sessions["S2"][1].exists()
    assert not (cache / "a.wav").exists(), "the disposable speech cache is cleared"


def test_a_cutoff_without_a_timezone_is_refused(world):
    with pytest.raises(SystemExit):
        load_script().main(["--before", "2026-09-15T00:00:00"])


def test_a_recording_outside_the_audio_directory_stops_everything_before_any_change(world, tmp_path):
    app, sessions, audio, cache = world
    outside = tmp_path / "elsewhere.wav"
    outside.write_bytes(b"keep")
    with db_of(app) as db:
        db.execute(update(m.Session).where(m.Session.id == uuid.UUID(sessions["S1"][0])).values(audio_uri=f"file://{outside}"))
        db.commit()
    before = counts(app)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    with pytest.raises(SystemExit):
        load_script().main(["--before", cutoff, "--apply"])
    assert counts(app) == before and outside.exists()
