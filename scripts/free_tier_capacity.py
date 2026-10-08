"""What do the free-tier limits in config/free_tier_limits.json allow? Arithmetic only: no provider is called.
Every number that is not in the limits file is an explicit argument and is ASSUMED until T1b measures it:
  --tokens-per-call        tokens (prompt + reply) of one live-interview LLM call (required)
  --tokens-per-score-call  tokens of one scoring LLM call over a whole transcript (required)
  --answers 11.3, --calls-per-answer 1.41  from the T3 voice run (stub-free: scripted voice, real Ollama), --runs 3 scoring runs per viva
For every chat model in the file: calls we may make per day (the smaller of floor(margin x rpd) and floor(margin x tpd / tokens per call)),
how many vivas that interviews or scores in a day, how many students can talk at once (the smaller of the requests-per-minute and the
tokens-per-minute limit), which limit binds, and the days needed for all 350 students.
The script refuses to run when it or the limits file has uncommitted changes, so the sidecar's git_sha names the code that made the numbers
(override with --allow-dirty for a scratch run; the sha then says +dirty or the run is not evidence).
Usage: python scripts/free_tier_capacity.py --tokens-per-call 400 --tokens-per-score-call 3300 [--answers 11.3] [--calls-per-answer 1.41] [--runs 3]"""
import argparse
import csv
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.llm.budget import margin  # noqa: E402
from app.llm.limits import DEFAULT_FILE, load_limits  # noqa: E402
from app.results_meta import write_meta  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--tokens-per-call", type=int, required=True)
ap.add_argument("--tokens-per-score-call", type=int, required=True)
ap.add_argument("--answers", type=float, default=11.3)
ap.add_argument("--calls-per-answer", type=float, default=1.41)
ap.add_argument("--runs", type=int, default=3)
ap.add_argument("--students", type=int, default=350)
ap.add_argument("--viva-seconds", type=int, default=900)
ap.add_argument("--allow-dirty", action="store_true")
ap.add_argument("--out", default=str(ROOT / "results" / "free_tier_capacity.csv"))
a = ap.parse_args()

if not a.allow_dirty:
    dirty = subprocess.run(["git", "status", "--porcelain", "--", str(Path(__file__).resolve()), str(DEFAULT_FILE)],
                           cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    if dirty:
        sys.exit(f"uncommitted or untracked: commit the script and the limits file first, so the sidecar's git_sha is honest\n{dirty}")

interview_calls = a.answers * a.calls_per_answer  # LLM calls in one viva
rows = []
for (provider, model), lim in sorted(load_limits().items()):
    if "tts" in model or "transcribe" in model or "whisper" in model or not lim.rpd:
        continue
    by_rpd = math.floor(margin() * lim.rpd)
    by_tpd = math.floor(margin() * lim.tpd / a.tokens_per_call) if lim.tpd else None
    day_calls = min(by_rpd, by_tpd) if by_tpd is not None else by_rpd
    day_limit = "tpd" if by_tpd is not None and by_tpd < by_rpd else "rpd"
    score_by_tpd = math.floor(margin() * lim.tpd / a.tokens_per_score_call) if lim.tpd else None
    score_day_calls = min(by_rpd, score_by_tpd) if score_by_tpd is not None else by_rpd
    calls_per_s = interview_calls / a.viva_seconds  # one student talking
    at_once_rpm = (lim.rpm / 60) / calls_per_s if lim.rpm else None
    at_once_tpm = (math.floor(margin() * lim.tpm) / 60) / (calls_per_s * a.tokens_per_call) if lim.tpm else None
    options = [(v, name) for v, name in ((at_once_rpm, "rpm"), (at_once_tpm, "tpm")) if v is not None]
    at_once, at_once_limit = min(options) if options else (None, "")
    vivas_interviewed = day_calls / interview_calls
    vivas_scored = score_day_calls / a.runs
    rows.append([provider, model, lim.rpm, lim.rpd, lim.tpm or "", lim.tpd or "", day_calls, day_limit, round(vivas_interviewed, 1),
                 round(vivas_scored, 1), round(at_once, 1) if at_once is not None else "", at_once_limit,
                 round(a.students / vivas_interviewed, 2), round(a.students / vivas_scored, 2)])
total = lambda col: round(sum(r[col] for r in rows if r[col] != ""), 1)  # noqa: E731
rows.append(["ALL", "every listed chat model together (calls spread perfectly across them)", "", "", "", "", sum(r[6] for r in rows), "", total(8),
             total(9), total(10), "", round(a.students / total(8), 2), round(a.students / total(9), 2)])
out = Path(a.out)
out.parent.mkdir(parents=True, exist_ok=True)
with open(out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["provider", "model", "rpm", "rpd", "tpm", "tpd", "usable_calls_per_day", "binding_daily_limit", "vivas_interviewed_per_day",
                "vivas_scored_per_day", "students_talking_at_once", "binding_per_minute_limit", "days_to_interview_all_students",
                "days_to_score_all_students", "basis"])
    w.writerows([r + [f"assumed: {a.tokens_per_call} tokens per interview call, {a.tokens_per_score_call} per scoring call (not measured)"] for r in rows])
write_meta(out, provider="stub", model="n/a (arithmetic on config/free_tier_limits.json)", n=len(rows), n_unit="models",
           assumptions={"tokens_per_interview_call": a.tokens_per_call, "tokens_per_score_call": a.tokens_per_score_call,
                        "answers_per_viva": a.answers, "llm_calls_per_answer": a.calls_per_answer, "scoring_runs": a.runs,
                        "students": a.students, "viva_seconds": a.viva_seconds, "margin": margin()},
           note="ASSUMED, not measured: tokens per call are unmeasured until T1b, and the limits were copied from the providers' consoles on 2026-10-08")
for r in rows:
    print(f"{r[0]}:{r[1][:26]:26} usable {r[6]:4}/day ({r[7] or '-'}) -> {r[8]:6} vivas interviewed/day, {r[9]:6} scored/day, "
          f"{r[10] or '-':>5} students at once ({r[11] or '-'}), {r[12]} days to interview {a.students}, {r[13]} days to score {a.students}  [assumed tokens]")
