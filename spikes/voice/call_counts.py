"""How many provider calls did T3b make? Counted from the telemetry log written by every counted call (spikes/voice/data/telemetry_t3b.jsonl)
and cross-checked against the budget registry. Local Ollama calls are listed but never count against a quota.
Usage: python spikes/voice/call_counts.py"""
import collections
import json

from common import DATA, RESULTS, write_csv, write_meta
from counted import usage_snapshot

LIMITS = {"groq": 60, "gemini": 30, "azure-speech": 200}  # what Mayank authorised for T3b


def main():
    rows = [json.loads(l) for l in open(DATA / "telemetry_t3b.jsonl")]
    c = collections.Counter((r["provider"], r["model"], r["kind"], r["status"]) for r in rows)
    out_rows = [[p, m, k, s, n] for (p, m, k, s), n in sorted(c.items())]
    per_provider = collections.Counter()
    for (p, m, k, s), n in c.items():
        per_provider[p] += n
    summary = [[p, "", "TOTAL", "", per_provider[p], LIMITS.get(p, "not metered (local)")] for p in sorted(per_provider)]
    out = RESULTS / "t3b_call_counts.csv"
    write_csv(out, ["provider", "model", "kind", "status", "calls", "authorised_limit"],
              [r + [""] for r in out_rows] + summary)
    budget = usage_snapshot()
    write_meta(out, provider="live", model="n/a (call accounting)", n=len(rows), n_unit="logged provider attempts", budget_registry_24h=budget,
               note="from the telemetry log; the budget registry counts the same attempts per (provider, model) in a rolling 24 h")
    for r in summary:
        print(f"{r[0]:14} {r[4]:4} calls (authorised: {r[5]})")
    print("budget registry (rolling 24 h):", budget)


if __name__ == "__main__":
    main()
