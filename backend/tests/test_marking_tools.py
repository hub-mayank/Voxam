"""scripts/marking_packet.py and scripts/compare_markers.py: blind packets, then the comparison of AI marks with two human markers."""
import csv
import importlib.util
import sys
from pathlib import Path

import pytest

from harness import build, db_of, ended_session, make_viva, mark_scored

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def world(tmp_path, monkeypatch):
    app, client, clock = build(tmp_path)
    codes = make_viva(client, students=("S1", "S2", "S3"))
    audio = tmp_path / "rec"
    audio.mkdir()
    sids = {}
    plans = {"S1": ((5, 5, 5, 5, 5),) * 3, "S2": ((3, 3, 3, 3, 3),) * 3, "S3": ((1, 1, 1, 1, 1),) * 3}
    for student, scores in plans.items():
        sid, _ = ended_session(client, clock, codes, student_id=student, answers=4)
        mark_scored(app, sid, scores=scores)
        wav = audio / f"{student}.wav"
        wav.write_bytes(b"RIFF")
        with db_of(app) as db:
            from uuid import UUID
            from app.db import models as m
            db.get(m.Session, UUID(sid)).audio_uri = f"file://{wav}"
            db.commit()
        sids[student] = sid
    monkeypatch.setenv("DATABASE_URL", app.state.settings.database_url)
    monkeypatch.setenv("AI_VIVA_NO_DOTENV", "1")
    return sids, tmp_path


def run_packets(monkeypatch, out):
    monkeypatch.setattr(sys, "argv", ["marking_packet", "--viva", "demo-viva", "--out", str(out), "--min-answers", "2"])
    load("marking_packet").main()


def test_packets_are_blind_complete_and_kept_outside_the_repository(world, monkeypatch, tmp_path):
    sids, base = world
    out = base / "private-marking"
    run_packets(monkeypatch, out)
    labels = sorted(p.name for p in (out / "for_markers").iterdir() if p.is_dir())
    assert labels == ["P01", "P02", "P03"]
    text = (out / "for_markers" / "P01" / "packet.md").read_text()
    assert "Marking packet P01" in text and "**[1] STUDENT" in text and "0 to 5" in text and "conceptual" in text
    for secret in ("reason (run", "feedback 0", "test-model", "S1", "S2", "S3", "low_confidence"):
        assert secret not in text, f"the packet must not reveal {secret!r}"
    assert (out / "for_markers" / "P01" / "audio.wav").read_bytes() == b"RIFF"
    mapping = list(csv.DictReader(open(out / "_private" / "mapping.csv")))
    assert {r["student_id"] for r in mapping} == {"S1", "S2", "S3"} and "_private" not in str(out / "for_markers")
    sheet = list(csv.reader(open(out / "for_markers" / "marking_sheet.csv")))
    assert sheet[0][0] == "session_id" and [r[0] for r in sheet[1:]] == labels and all(not any(r[1:]) for r in sheet[1:])


def test_it_refuses_to_write_inside_the_repository(world, monkeypatch):
    with pytest.raises(SystemExit) as stop:
        run_packets(monkeypatch, ROOT / "marking-out")
    assert "inside the repository" in str(stop.value)


def write_sheet(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["session_id", "marker", "conceptual_0_5", "depth_0_5", "problem_0_5", "practical_0_5", "communication_0_5", "total_100", "notes"])
        for label, ratings in rows.items():
            total = sum(wt * r / 5 for wt, r in zip((30, 25, 20, 15, 10), ratings))
            w.writerow([label, "m", *ratings, round(total), ""])


def test_two_markers_against_the_ai(world, monkeypatch):
    sids, base = world
    out = base / "private-marking"
    run_packets(monkeypatch, out)
    labels = {r["student_id"]: r["label"] for r in csv.DictReader(open(out / "_private" / "mapping.csv"))}
    a, b = base / "a.csv", base / "b.csv"
    # the AI gave S1 100, S2 60, S3 20; marker A agrees exactly, marker B is 10 points harsher on S1 and S2
    write_sheet(a, {labels["S1"]: (5, 5, 5, 5, 5), labels["S2"]: (3, 3, 3, 3, 3), labels["S3"]: (1, 1, 1, 1, 1)})
    write_sheet(b, {labels["S1"]: (4, 5, 4, 5, 4), labels["S2"]: (3, 2, 3, 3, 3), labels["S3"]: (1, 1, 1, 1, 1)})
    result = base / "accuracy.csv"
    monkeypatch.setattr(sys, "argv", ["compare_markers", "--mapping", str(out / "_private" / "mapping.csv"), "--sheet", str(a),
                                      "--sheet", str(b), "--out", str(result)])
    load("compare_markers").main()
    rows = {r["comparison"]: r for r in csv.DictReader(open(result))}
    assert rows["AI vs marker 1"]["n"] == "3" and rows["AI vs marker 1"]["mean_abs_gap"] == "0.0" and rows["AI vs marker 1"]["pearson_r"] == "1.0"
    assert float(rows["AI vs marker 2"]["mean_abs_gap"]) > 0 and float(rows["AI vs marker 2"]["bias_first_minus_second"]) > 0
    assert rows["marker 1 vs marker 2"]["n"] == "3" and "ceiling" in rows["marker 1 vs marker 2"]["note"]
    assert "AI vs mean of the two markers" in rows
    assert not any(s in open(result).read() for s in ("S1", "S2", "S3")), "labels only: no student ids in the output"
    meta = __import__("json").load(open(str(result) + ".meta.json"))
    assert meta["markers"] == 2 and meta["n_unit"] == "sessions marked by humans" and meta["provider"] in ("live", "mock")


def test_a_sheet_whose_total_disagrees_with_the_formula_or_has_a_bad_rating_is_rejected(world, monkeypatch):
    sids, base = world
    out = base / "private-marking"
    run_packets(monkeypatch, out)
    mod = load("compare_markers")
    bad = base / "bad.csv"
    bad.write_text("session_id,marker,conceptual_0_5,depth_0_5,problem_0_5,practical_0_5,communication_0_5,total_100,notes\nP01,m,5,5,5,5,5,60,\n")
    with pytest.raises(SystemExit) as stop:
        mod.read_sheet(bad)
    assert "weighted formula" in str(stop.value)
    bad.write_text("session_id,marker,conceptual_0_5,depth_0_5,problem_0_5,practical_0_5,communication_0_5,total_100,notes\nP01,m,7,5,5,5,5,,\n")
    with pytest.raises(SystemExit) as stop:
        mod.read_sheet(bad)
    assert "0 to 5" in str(stop.value)
    blank = base / "blank.csv"
    blank.write_text("session_id,marker,conceptual_0_5,depth_0_5,problem_0_5,practical_0_5,communication_0_5,total_100,notes\nP01,,,,,,,,\n")
    assert mod.read_sheet(blank) == {}, "an unrated template row is ignored"
