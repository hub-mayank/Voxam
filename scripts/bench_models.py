"""Benchmark LLMs as scorer on the 4 personas. One variable at a time, raw results saved.
Usage (from repo root, venv active; keys come from the environment or the repo's .env):
  python scripts/bench_models.py gemini-3.5-flash-lite --runs 3                 # bare names use --llm (default gemini)
  python scripts/bench_models.py groq:openai/gpt-oss-20b ollama:llama3.2:3b     # `provider:model` picks the provider
  python scripts/bench_models.py --llm mock          # dry run, no key
Free-tier budgets (config/free_tier_limits.json) apply: calls are paced and refused at 0.9 x the daily limit."""
import argparse
import csv
import datetime
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import load_config  # noqa: E402
from app.envfile import load_env  # noqa: E402
from app.scorer import score_session, ScoreError  # noqa: E402
from app.llm.factory import is_provider_name, make_llm  # noqa: E402
from app.results_meta import write_meta  # noqa: E402

PERSONAS = ["strong", "weak", "idk", "injection"]


class Timed:
    """Wraps an LLM: records per-call latency, and backs off longer than the llm layer on 429/503 (free-tier quotas)."""
    def __init__(self, inner, delay=0.0):
        self.inner, self.name, self.lat, self.throttled, self.delay = inner, inner.name, [], 0, delay
        self.last_body = ""

    def complete_json(self, system, user, max_tokens=200, **kw):
        for attempt, delay in enumerate([0, 20, 45, 70]):
            time.sleep(delay + self.delay)
            t = time.perf_counter()
            try:
                out = self.inner.complete_json(system, user, max_tokens, **kw)
                self.lat.append(time.perf_counter() - t)
                return out
            except Exception as e:
                self.last_body = getattr(e, "body", "")[:500]
                if getattr(e, "retryable", False) and attempt < 3:
                    self.throttled += 1
                    continue
                raise

    def complete_text(self, *a, **k):
        return self.inner.complete_text(*a, **k)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="*")
    ap.add_argument("--llm", default="gemini", help="provider for bare model names: gemini, ollama, groq, ... or mock (dry run)")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--personas", default="strong,weak,idk,injection", help="comma list, to re-run only some")
    ap.add_argument("--delay", type=float, default=0.0, help="seconds between calls (free tiers: try 6)")
    a = ap.parse_args()
    load_env()
    os.environ.setdefault("FREE_TIER_MAX_WAIT_S", "120")  # a benchmark may wait for its per-minute slot; the live interviewer may not
    cfg = load_config(ROOT / "config/viva.config.json")
    targets = ["mock"] if a.llm == "mock" else a.models
    if not targets:
        sys.exit("give at least one model name (from python -m app.list_models)")
    rows = []
    for m in targets:
        if a.llm == "mock":
            from app.llm.mock import MockLLM
            llm = Timed(MockLLM())
        else:
            head = m.partition(":")[0]
            spec = m if is_provider_name(head) else f"{a.llm}:{m}"  # `groq:openai/gpt-oss-20b` or a bare model name
            g = make_llm(spec, retries=0)  # retries live in Timed below (longer waits)
            pre_err = None
            for wait in (0, 20, 45):  # preflight, retried on transient errors only (404 = not callable: no retry)
                time.sleep(wait)
                try:
                    g.complete_text("Reply with the single word OK.", "ping", max_tokens=5)
                    pre_err = None
                    break
                except Exception as e:
                    pre_err = e
                    if not getattr(e, "retryable", False):
                        break
            if pre_err is not None:
                body = getattr(pre_err, "body", "")[:400].replace("\n", " ")
                print(f"SKIP {m}: preflight failed: {str(pre_err)[:120]} {body}\n")
                continue
            llm = Timed(g, delay=a.delay)
        for p in a.personas.split(","):
            events = [json.loads(l) for l in open(ROOT / f"backend/tests/personas/{p}.jsonl")]
            row = {"model": m, "persona": p, "total": "", "spread": "", "low_conf": "", "error": ""}
            try:
                r = score_session(llm, cfg, events, runs=a.runs)
                row.update(total=r["total"], spread=r["total_spread"], low_conf=r["low_confidence"])
            except ScoreError as e:
                row["error"] = str(e)[:120]
            rows.append(row)
            print(f"{m:34} {p:10} total={row['total']!s:6} spread={row['spread']!s:5} {row['error']}", flush=True)
            if row["error"] and llm.last_body:
                print("    last API error body:", llm.last_body.replace("\n", " ")[:500], flush=True)
        lat = sorted(llm.lat)
        med = statistics.median(lat) if lat else float("nan")
        p95 = lat[int(0.95 * (len(lat) - 1))] if lat else float("nan")
        tot = {r["persona"]: r["total"] for r in rows if r["model"] == m and r["total"] != ""}
        ok = (len(tot) == 4 and tot["strong"] >= 60 and tot["strong"] > tot["weak"] > tot["idk"]
              and tot["injection"] <= tot["weak"] + 5)
        print(f"  -> {m}: latency p50={med:.1f}s p95={p95:.1f}s throttled={llm.throttled} "
              f"{'PASS' if ok else 'FAIL'} (heuristic: strong>=60, strong>weak>idk, injection<=weak+5)\n")
    if not rows:
        sys.exit("no model passed preflight; nothing to save")
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    f = out / f"bench_{datetime.datetime.now():%Y%m%d_%H%M%S}.csv"
    with open(f, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    models = sorted({r["model"] for r in rows})
    write_meta(f, "mock" if a.llm == "mock" else "live", models, a.runs, n_unit="scorer runs per persona row")
    print("saved", f)


if __name__ == "__main__":
    main()
