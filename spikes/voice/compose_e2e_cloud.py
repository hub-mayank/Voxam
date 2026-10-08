"""Build end-to-end latency for a cloud LLM from MEASURED legs: for each replayed turn, the non-LLM legs (endpoint wait, STT, backend overhead,
TTS) come from the real Ollama run of the chosen stack, and the LLM leg is the cloud provider's streamed time on that turn's own prompts.
  sequential: classify total + phrase first sentence       parallel: max(classify total, phrase first sentence) from the concurrent pass
Usage: python spikes/voice/compose_e2e_cloud.py --stack F --llm llm_cloud_groq_openai_gpt-oss-20b"""
import argparse
import csv
import json

from common import RESULTS, percentile, write_csv, write_meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stack", required=True)
    ap.add_argument("--llm", required=True, help="stem of a results/voice_spike/llm_cloud_*.csv")
    a = ap.parse_args()
    base = {r["turn"]: r for r in csv.DictReader(open(RESULTS / f"e2e_real_ollama_{a.stack}_h600.csv"))}
    cloud = list(csv.DictReader(open(RESULTS / f"{a.llm}.csv")))
    meta = json.loads((RESULTS / f"{a.llm}.csv.meta.json").read_text())
    rows = []
    for turn in sorted({r["turn"] for r in cloud}):
        b = base[turn]
        fixed = (float(b["endpoint_delay_ms"]) / 1000 + float(b["stt_final_s"]) + float(b["backend_overhead_ms"]) / 1000 + float(b["tts_first_chunk_s"]))
        seq = {r["kind"]: r for r in cloud if r["turn"] == turn and r["mode"] == "sequential" and not r["error"]}
        par = {r["kind"]: r for r in cloud if r["turn"] == turn and r["mode"] == "parallel" and not r["error"]}
        if "classify" not in seq or (b["phrase_s"] not in ("", "0.0", "0") and "phrase" not in seq):
            continue
        llm_seq = float(seq["classify"]["total_s"]) + (float(seq["phrase"]["first_sentence_s"]) if "phrase" in seq else 0.0)
        llm_par = max(float(par["classify"]["total_s"]), float(par["phrase"]["first_sentence_s"])) if {"classify", "phrase"} <= set(par) else ""
        rows.append([turn, round(fixed, 3), round(llm_seq, 3), llm_par if llm_par == "" else round(llm_par, 3), round(fixed + llm_seq, 3),
                     "" if llm_par == "" else round(fixed + llm_par, 3), seq["classify"]["ttft_s"], seq["phrase"]["ttft_s"] if "phrase" in seq else ""])
    out = RESULTS / f"e2e_real_{a.llm.replace('llm_cloud_', '')}_stack{a.stack}.csv"
    write_csv(out, ["turn", "non_llm_legs_s", "llm_sequential_streamed_s", "llm_parallel_s", "e2e_sequential_streamed_s", "e2e_parallel_s", "classify_ttft_s", "phrase_ttft_s"], rows)
    write_meta(out, provider="live", model=meta["model"], n=len(rows), n_unit="turns (non-LLM legs from the Ollama run of this stack, LLM leg from the cloud replay)",
               stack=a.stack, llm_calls=meta.get("llm_calls"), note="composed from measured legs; cloud LLM latency measured from this Mac on the free tier")
    seq = [float(r[4]) for r in rows]
    par = [float(r[5]) for r in rows if r[5] != ""]
    print(f"stack {a.stack} + {meta['model']}: n={len(rows)} E2E sequential(streamed) p50 {percentile(seq, 50):.2f}s p95 {percentile(seq, 95):.2f}s"
          + (f" | parallel (n={len(par)}) p50 {percentile(par, 50):.2f}s p95 {percentile(par, 95):.2f}s" if par else ""))


if __name__ == "__main__":
    main()
