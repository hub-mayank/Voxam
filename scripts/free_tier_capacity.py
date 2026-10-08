"""What do the free-tier limits in config/free_tier_limits.json allow? Arithmetic only: no provider is called.
Assumptions (arguments, defaults from the T3 voice spike's end-to-end run on the branch task/T3-voice-spike):
  answers per 15-minute viva 11.3, LLM calls per answer 1.41 (classify, then phrase when the policy needs one), 3 scoring runs per viva.
For every chat model in the file: calls we may make per day (floor(margin x rpd)), how many vivas that interviews or scores in a day,
how many students can talk at once under the per-minute limit, and the days needed for all 350 students.
Usage: python scripts/free_tier_capacity.py [--answers 11.3] [--calls-per-answer 1.41] [--runs 3] [--students 350]"""
import argparse
import csv
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.llm.budget import margin  # noqa: E402
from app.llm.limits import load_limits  # noqa: E402
from app.results_meta import write_meta  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--answers", type=float, default=11.3)
ap.add_argument("--calls-per-answer", type=float, default=1.41)
ap.add_argument("--runs", type=int, default=3)
ap.add_argument("--students", type=int, default=350)
ap.add_argument("--viva-seconds", type=int, default=900)
ap.add_argument("--out", default=str(ROOT / "results" / "free_tier_capacity.csv"))
a = ap.parse_args()

interview_calls = a.answers * a.calls_per_answer
rows = []
for (provider, model), lim in sorted(load_limits().items()):
    if "tts" in model or "transcribe" in model or "whisper" in model or not lim.rpd:
        continue
    day = math.floor(margin() * lim.rpd)
    per_student_calls_per_s = interview_calls / a.viva_seconds
    concurrent = (lim.rpm / 60) / per_student_calls_per_s if lim.rpm else None
    rows.append([provider, model, lim.rpm, lim.rpd, day, round(day / interview_calls, 1), round(day / a.runs, 1),
                 round(concurrent, 1) if concurrent else "", round(a.students * interview_calls / day, 2), round(a.students * a.runs / day, 2)])
total_day = sum(r[4] for r in rows)
total_conc = sum(r[7] for r in rows if r[7] != "")
rows.append(["ALL", "every listed chat model together (calls spread perfectly across them)", "", "", total_day, round(total_day / interview_calls, 1),
             round(total_day / a.runs, 1), round(total_conc, 1), round(a.students * interview_calls / total_day, 2), round(a.students * a.runs / total_day, 2)])
out = Path(a.out)
out.parent.mkdir(parents=True, exist_ok=True)
with open(out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["provider", "model", "rpm", "rpd", "usable_calls_per_day", "vivas_interviewed_per_day", "vivas_scored_per_day",
                "students_talking_at_once_by_rpm", "days_to_interview_all_students", "days_to_score_all_students"])
    w.writerows(rows)
write_meta(out, provider="stub", model="n/a (arithmetic on config/free_tier_limits.json)", n=len(rows), n_unit="models",
           assumptions={"answers_per_viva": a.answers, "llm_calls_per_answer": a.calls_per_answer, "scoring_runs": a.runs, "students": a.students,
                        "viva_seconds": a.viva_seconds, "margin": margin()},
           note="not a measurement; the limits were copied from the providers' consoles on 2026-10-08 and must be re-verified")
for r in rows:
    print(f"{r[0]}:{r[1][:26]:26} usable {r[4]:4}/day -> {r[5]:6} vivas interviewed/day, {r[6]:6} scored/day, {r[7] or '-':>5} students at once, "
          f"{r[8]} days to interview {a.students}, {r[9]} days to score {a.students}")
