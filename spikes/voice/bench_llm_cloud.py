"""Replay the interviewer's real prompts (saved by bench_e2e_real.py from the Ollama run) at a cloud provider, streaming, and measure per call:
time to first token, to the end of the first sentence, and to the end. Sequential pass (classify, then phrase, like the engine), then a
parallel pass (classify and phrase started together) on a few phrase turns. Every call is counted by the budget registry and logged.
The phrase prompt carries the action chosen in the Ollama run (the cloud model's own classification is not fed back): a latency replay.
Usage: python spikes/voice/bench_llm_cloud.py --provider groq --model openai/gpt-oss-20b --turns 20 --parallel-turns 6
       python spikes/voice/bench_llm_cloud.py --provider gemini --model gemini-3.5-flash-lite --turns 12 --parallel-turns 3"""
import argparse
import json
import os
import threading

from common import DATA, RESULTS, percentile, write_csv, write_meta
from counted import CallCapExceeded, counted, key
from llm_stream import gemini_stream, openai_stream

BASES = {"groq": "https://api.groq.com/openai/v1"}


def streamer(provider, model):
    k = key(f"{provider.upper()}_API_KEY")
    if provider == "gemini":
        return lambda c: gemini_stream(model, k, c["system"], c["user"], c["json_mode"], c["max_tokens"])
    effort = os.environ.get("GROQ_REASONING_EFFORT", "low") if "gpt-oss" in model else None
    return lambda c: openai_stream(provider, model, BASES[provider], k, c["system"], c["user"], c["json_mode"], c["max_tokens"], effort=effort)


def one(provider, model, stream, call):
    """Count and run one streaming call. -> row fields; errors are recorded, not raised (a refused or failed call still used budget)."""
    try:
        s, _ = counted(provider, model, call["kind"], lambda: stream(call))
        return dict(ttft=s.ttft_s, first_sentence=s.first_sentence_s, total=s.total_s, text=s.text, error="")
    except CallCapExceeded as e:
        return dict(ttft=None, first_sentence=None, total=None, text="", error=f"budget: {e}")
    except Exception as e:
        return dict(ttft=None, first_sentence=None, total=None, text="", error=f"{type(e).__name__}: {str(e)[:100]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", required=True, choices=["groq", "gemini"])
    ap.add_argument("--model", required=True)
    ap.add_argument("--turns", type=int, default=20, help="turns with at least one LLM call to replay")
    ap.add_argument("--parallel-turns", type=int, default=6)
    ap.add_argument("--prompts", default=str(DATA / "prompts_B.jsonl"))
    a = ap.parse_args()
    turns = [json.loads(l) for l in open(a.prompts)]
    turns = [t for t in turns if t["calls"]][:a.turns]
    stream = streamer(a.provider, a.model)
    rows, attempts = [], 0
    for t in turns:
        for call in t["calls"]:
            r = one(a.provider, a.model, stream, call)
            attempts += 1
            rows.append([t["turn"], call["kind"], "sequential", *(r[k] if r[k] is None else round(r[k], 4) for k in ("ttft", "first_sentence", "total")), r["error"]])
    phrase_turns = [t for t in turns if len(t["calls"]) == 2][:a.parallel_turns]
    for t in phrase_turns:
        got = {}

        def run(call):
            got[call["kind"]] = one(a.provider, a.model, stream, call)

        threads = [threading.Thread(target=run, args=(c,)) for c in t["calls"]]
        [th.start() for th in threads]
        [th.join() for th in threads]
        attempts += 2
        for kind, r in got.items():
            rows.append([t["turn"], kind, "parallel", *(r[k] if r[k] is None else round(r[k], 4) for k in ("ttft", "first_sentence", "total")), r["error"]])
    safe = a.model.replace("/", "_")
    out = RESULTS / f"llm_cloud_{a.provider}_{safe}.csv"
    write_csv(out, ["turn", "kind", "mode", "ttft_s", "first_sentence_s", "total_s", "error"], rows)
    write_meta(out, provider="live", model=f"{a.provider}:{a.model}", n=len(turns), n_unit="turns replayed with their real prompts", llm_calls=attempts,
               free_tier="yes (budget registry)", parallel_turns=len(phrase_turns), reasoning_effort=os.environ.get("GROQ_REASONING_EFFORT", "low") if "gpt-oss" in a.model else None,
               note="latency replay of prompts captured from the Ollama run; the cloud model's classification is not fed back into the phrase prompt")
    ok = [r for r in rows if not r[-1]]
    for kind in ("classify", "phrase"):
        for mode in ("sequential", "parallel"):
            sel = [r for r in ok if r[1] == kind and r[2] == mode]
            if sel:
                print(f"{a.provider}:{a.model} {kind:8} {mode:10} n={len(sel):2} ttft p50 {percentile([r[3] for r in sel], 50):.2f}s p95 {percentile([r[3] for r in sel], 95):.2f}s | "
                      f"first sentence p50 {percentile([r[4] for r in sel], 50):.2f}s | total p50 {percentile([r[5] for r in sel], 50):.2f}s")
    print(f"calls attempted: {attempts}; errors: {len(rows) - len(ok)}")


if __name__ == "__main__":
    main()
