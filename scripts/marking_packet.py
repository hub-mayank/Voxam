"""Blind marking packets for the human markers (T8 scoring accuracy, TJ-5).
For every finished session of a viva it writes a folder P01, P02, ... with `packet.md` (the questions, their key points, the rubric,
the transcript with turn numbers and times) and `audio.wav`, plus one blank marking sheet. Nothing the AI decided is included: no
marks, reasons, feedback, flags or overrides. The mapping from P01 to the real session and student is written to `_private/` for
the coordinator only. Output must be OUTSIDE the git repository (recordings and names never go into git).
Usage (same environment as the server: DATABASE_URL, AUDIO_DIR):
  python scripts/marking_packet.py --viva local-dsa --out ~/Documents/voxam-private/marking [--min-answers 4]"""
import argparse
import csv
import shutil
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.db import models as m  # noqa: E402
from app.db.engine import make_engine  # noqa: E402
from app.envfile import load_env  # noqa: E402

FINISHED = ("ended", "scoring", "scored", "failed")
SHEET_COLUMNS = ["session_id", "marker", "conceptual_0_5", "depth_0_5", "problem_0_5", "practical_0_5", "communication_0_5", "total_100", "notes"]


def clock(ms) -> str:
    if ms is None:
        return "--:--"
    s = int(ms // 1000)
    return f"{s // 60}:{s % 60:02d}"


def audio_file(uri):
    if not uri:
        return None
    path = Path(unquote(urlparse(uri).path)) if urlparse(uri).scheme == "file" else Path(uri)
    return path if path.is_file() else None


def packet_text(label, viva, dims, questions, turns) -> str:
    out = [f"# Marking packet {label}", "",
           f"Viva: {viva.title} ({viva.subject}). Mark the STUDENT only, on the five dimensions below, **0 to 5 in whole numbers**.",
           "Listen to `audio.wav` where the transcript is unclear (the times are offsets into the recording). Accent, grammar and mixing "
           "Hindi with English must not lower the first four dimensions; they may affect Communication only for clarity and structure.",
           "", "| Dimension | Weight | What 5/5 looks like |", "|---|---:|---|"]
    out += [f"| {d['key']} | {d['weight']}% | {d.get('five_means', '')} |" for d in dims]
    out += ["", "Total (0-100) = " + " + ".join(f"{d['weight'] / 5:g} x {d['key']}" for d in dims),
            "", "Give brief reasons in `notes` with the turn numbers you relied on.", "", "## Conversation", ""]
    for t in turns:
        who = "INTERVIEWER" if t.role == "ai" else "STUDENT"
        out.append(f"**[{t.idx}] {who} ({clock(t.t_start_ms)})** {t.text}")
        q = questions.get(t.question_id) if t.role == "ai" and t.action in ("new_question", "open", None) else None
        if q and q.key_points:
            out.append(f"  - question `{q.id}` key points (private to markers): " + "; ".join(q.key_points))
        out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--viva", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--min-answers", type=int, default=4, help="skip sessions with fewer student answers (nothing to mark)")
    a = ap.parse_args()
    out = a.out.expanduser().resolve()
    if out == ROOT or ROOT in out.parents:
        sys.exit(f"refusing to write recordings and names inside the repository: {out}")
    load_env()
    with sessionmaker(make_engine())() as db:
        viva = db.get(m.Viva, a.viva)
        if viva is None:
            sys.exit(f"no viva {a.viva!r} in this database")
        dims = viva.config["rubric"]["dimensions"]
        questions = {q.id: q for q in db.scalars(select(m.Question).where(m.Question.viva_id == a.viva))}
        sessions = list(db.scalars(select(m.Session).where(m.Session.viva_id == a.viva, m.Session.status.in_(FINISHED))
                                   .order_by(m.Session.started_at, m.Session.id)))
        packets, skipped = [], []
        for s in sessions:
            turns = list(db.scalars(select(m.Turn).where(m.Turn.session_id == s.id).order_by(m.Turn.idx)))
            if sum(t.role == "student" for t in turns) < a.min_answers:
                skipped.append(s.student_id)
                continue
            packets.append((s, turns))
        shown, private = out / "for_markers", out / "_private"
        shown.mkdir(parents=True, exist_ok=True)
        private.mkdir(parents=True, exist_ok=True)
        rows = []
        for i, (s, turns) in enumerate(packets, start=1):
            label = f"P{i:02d}"
            folder = shown / label
            folder.mkdir(exist_ok=True)
            (folder / "packet.md").write_text(packet_text(label, viva, dims, questions, turns))
            wav = audio_file(s.audio_uri)
            if wav:
                shutil.copyfile(wav, folder / "audio.wav")
            rows.append({"label": label, "session_id": str(s.id), "student_id": s.student_id, "has_audio": bool(wav)})
        with open(private / "mapping.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["label", "session_id", "student_id", "has_audio"])
            w.writeheader()
            w.writerows(rows)
        with open(shown / "marking_sheet.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(SHEET_COLUMNS)
            for r in rows:
                w.writerow([r["label"], "", "", "", "", "", "", "", ""])
    print(f"{len(rows)} packets in {shown} (skipped {len(skipped)} with too few answers: {skipped})")
    print(f"mapping (coordinator only): {private / 'mapping.csv'}")
    missing = [r["label"] for r in rows if not r["has_audio"]]
    if missing:
        print(f"no recording found for {missing}: markers will have the transcript only")


if __name__ == "__main__":
    main()
