"""Consolidate results/voice_spike/*.csv into one table (summary.csv) and print it. The T3 report quotes numbers from summary.csv only.
Each row says where it came from and whether the leg is measured or simulated.
Usage: python spikes/voice/summarize.py"""
import csv
import json
import statistics
from pathlib import Path

from common import RESULTS, percentile, write_csv, write_meta

rows = []


def add(area, config, metric, value, unit, source, label="measured"):
    rows.append([area, config, metric, round(value, 4) if isinstance(value, float) else value, unit, source, label])


def load(path):
    return list(csv.DictReader(open(path)))


def meta(path):
    return json.loads(Path(str(path) + ".meta.json").read_text())


def main():
    for f in sorted(RESULTS.glob("vad_endpoint.csv")):
        data = load(f)
        for h in sorted({int(r["hangover_ms"]) for r in data}):
            sel = [r for r in data if int(r["hangover_ms"]) == h]
            d = [float(r["endpoint_delay_ms_after_true_end"]) for r in sel if r["endpoint_delay_ms_after_true_end"]]
            add("vad", f"silero hangover {h} ms", "endpoint_delay_p50", percentile(d, 50), "ms", f.name)
            add("vad", f"silero hangover {h} ms", "endpoint_delay_p95", percentile(d, 95), "ms", f.name)
            add("vad", f"silero hangover {h} ms", "premature_cuts_all_turns", f"{sum(int(r['premature_cut']) for r in sel)}/{len(sel)}", "turns", f.name)
            pa = [r for r in sel if r["has_pauses"] == "1"]
            add("vad", f"silero hangover {h} ms", "premature_cuts_turns_with_thinking_pauses", f"{sum(int(r['premature_cut']) for r in pa)}/{len(pa)}", "turns", f.name)
        add("vad", "silero", "cost_per_32ms_frame_mean", statistics.mean(float(r["vad_ms_per_32ms_frame"]) for r in data), "ms", f.name)

    for f in sorted(RESULTS.glob("stt_faster_whisper_*.csv")):
        data, m = load(f), meta(f)
        b = [float(r["batch_decode_s"]) for r in data]
        last = [float(r["last_piece_decode_s"]) for r in data]
        cfg = m["model"]
        add("stt", cfg, "batch_decode_p50", percentile(b, 50), "s", f.name)
        add("stt", cfg, "batch_decode_p95", percentile(b, 95), "s", f.name)
        add("stt", cfg, "last_piece_decode_p50", percentile(last, 50), "s", f.name)
        add("stt", cfg, "last_piece_decode_p95", percentile(last, 95), "s", f.name)
        add("stt", cfg, "batch_decode_p50_audio_under_4s", percentile([float(r["batch_decode_s"]) for r in data if float(r["audio_s"]) < 4], 50), "s", f.name)
        add("stt", cfg, "batch_decode_p50_audio_over_10s", percentile([float(r["batch_decode_s"]) for r in data if float(r["audio_s"]) > 10], 50), "s", f.name)
        add("stt", cfg, "wer_batch_mean_synthetic", statistics.mean(float(r["wer_batch"]) for r in data), "ratio", f.name)
        add("stt", cfg, "wer_segmented_mean_synthetic", statistics.mean(float(r["wer_segmented"]) for r in data), "ratio", f.name)
        add("stt", cfg, "model_load", m["model_load_s"], "s", f.name)

    for f in sorted(RESULTS.glob("tts_*.csv")):
        data, m = load(f), meta(f)
        first = [float(r["first_chunk_s"]) for r in data]
        add("tts", m["model"], "first_chunk_p50", percentile(first, 50), "s", f.name)
        add("tts", m["model"], "first_chunk_p95", percentile(first, 95), "s", f.name)
        add("tts", m["model"], "rtf_mean", statistics.mean(float(r["rtf"]) for r in data), "ratio", f.name)

    for f in sorted(RESULTS.glob("e2e_stack_*.csv")):
        data, m = load(f), meta(f)
        label = "simulated-llm" if m.get("llm_leg") == "simulated" else "measured"
        cfg = f"{f.stem.replace('e2e_stack_', '')} ({m['stack']})"
        for col, name in (("e2e_s", "e2e"), ("e2e_speculative_stt_s", "e2e_speculative_stt"), ("e2e_parallel_llm_s", "e2e_parallel_llm_calls")):
            vals = [float(r[col]) for r in data if r.get(col)]
            if vals:
                add("e2e", cfg, f"{name}_p50", percentile(vals, 50), "s", f.name, label)
                add("e2e", cfg, f"{name}_p95", percentile(vals, 95), "s", f.name, label)
        for col, name, unit, scale in (("endpoint_delay_ms", "endpoint_delay_p50", "ms", 1), ("stt_final_s", "stt_p50", "s", 1), ("llm_critical_path_s", "llm_p50", "s", 1),
                                       ("backend_overhead_ms", "backend_p50", "ms", 1), ("tts_first_chunk_s", "tts_first_p50", "s", 1)):
            add("e2e", cfg, name, percentile([float(r[col]) for r in data], 50), unit, f.name, label if name == "llm_p50" else "measured")
        add("e2e", cfg, "turns", len(data), "turns", f.name)
        add("e2e", cfg, "llm_calls_per_turn_mean", statistics.mean(int(r["llm_calls"]) for r in data), "calls", f.name)
        add("e2e", cfg, "stt_wer_on_synthetic_mean", statistics.mean(float(r["wer"]) for r in data), "ratio", f.name)

    for f in sorted(RESULTS.glob("e2e_sensitivity_*.csv")):
        for r in load(f):
            add("e2e_llm_sensitivity", f"{f.stem.replace('e2e_sensitivity_', '')} / assumed LLM {r['llm_profile_assumed']}", "e2e_p50", float(r["e2e_p50_s"]), "s", f.name, "simulated-llm")
            add("e2e_llm_sensitivity", f"{f.stem.replace('e2e_sensitivity_', '')} / assumed LLM {r['llm_profile_assumed']}", "e2e_p95", float(r["e2e_p95_s"]), "s", f.name, "simulated-llm")

    for f in sorted(RESULTS.glob("stt_concurrency.csv")):
        for r in load(f):
            cfg = f"{r['model']} x{r['concurrent_decodes']} concurrent"
            add("stt_concurrency", cfg, "decode_p50", float(r["decode_p50_s"]), "s", f.name)
            add("stt_concurrency", cfg, "decode_p95", float(r["decode_p95_s"]), "s", f.name)
            add("stt_concurrency", cfg, "decodes_per_s", float(r["decodes_per_s"]), "1/s", f.name)

    for f in sorted(RESULTS.glob("transport_ws.csv")):
        data, m = load(f), meta(f)
        fa = [float(r["first_reply_audio_ms_after_speech_end"]) for r in data]
        add("transport_ws", "FastAPI WebSocket, real-time paced audio, canned reply", "first_reply_audio_p50", percentile(fa, 50), "ms", f.name)
        add("transport_ws", "FastAPI WebSocket, real-time paced audio, canned reply", "first_reply_audio_p95", percentile(fa, 95), "ms", f.name)
        add("transport_ws", "FastAPI WebSocket, real-time paced audio, canned reply", "endpoint_delay_p50", percentile([float(r["endpoint_delay_ms_seen_by_client"]) for r in data], 50), "ms", f.name)
        add("transport_ws", "FastAPI WebSocket, real-time paced audio, canned reply", "server_stt_p50", percentile([float(r["server_stt_s"]) for r in data], 50), "s", f.name)
        add("transport_ws", "FastAPI WebSocket, real-time paced audio, canned reply", "barge_in_interrupt_after_first_sample", m["barge_in_interrupt_ms"], "ms", f.name)

    for f in sorted(RESULTS.glob("wer_real_clips.csv")):
        data = load(f)
        for model in sorted({r["model"] for r in data}):
            for kind, lang in (("english", "en"), ("hinglish", "en"), ("hinglish", "hi"), ("hinglish", "auto")):
                sel = [r for r in data if r["model"] == model and r["kind"] == kind and r["language_setting"] == lang]
                if sel:
                    add("wer_real_clips", f"{model} {kind} language={lang}", "wer_strict_mean", statistics.mean(float(r["wer_strict"]) for r in sel), "ratio", f.name)
                    add("wer_real_clips", f"{model} {kind} language={lang}", "wer_skeleton_mean", statistics.mean(float(r["wer_skeleton"]) for r in sel), "ratio", f.name)
                    add("wer_real_clips", f"{model} {kind} language={lang}", "clips", len(sel), "clips", f.name)

    out = RESULTS / "summary.csv"
    write_csv(out, ["area", "config", "metric", "value", "unit", "source_file", "label"], rows)
    write_meta(out, provider="stub", model="n/a (consolidation of the other files)", n=len(rows), n_unit="summary rows",
               note="rows labelled simulated-llm use an ASSUMED LLM latency profile; everything else is measured. See each source_file's own sidecar.")
    for r in rows:
        print(" | ".join(str(x) for x in r))


if __name__ == "__main__":
    main()
