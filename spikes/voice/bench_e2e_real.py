"""End to end with a REAL local LLM (Ollama): 'student stops speaking' -> 'first AI audio chunk', on the synthetic turns.
Every leg is measured: VAD endpoint, STT, the real backend POST .../answer (the Interviewer making its real classify and phrase calls to
Ollama), and Piper (en_GB alba). After each turn the same two prompts are replayed to measure what the adapters cannot see:
  streaming   time to first token and to the end of the first sentence, calls in sequence (classify, then phrase)
  parallel    classify and phrase started together (phrase for the action the engine actually chose: a best case)
Prompts are saved to data/prompts_<stack>.jsonl (gitignored: they contain private key points) so other providers can be replayed on them.
Usage: python spikes/voice/bench_e2e_real.py --stack B [--hangover 600]"""
import argparse
import csv
import json
import os
import threading

import soundfile as sf

os.environ.setdefault("OLLAMA_MODEL", "llama3.2:3b")

from brain import Brain, Recorder, TimedLLM  # noqa: E402
from common import DATA, RESULTS, SYNTH, percentile, write_csv, write_meta  # noqa: E402

os.environ.setdefault("TELEMETRY_FILE", str(DATA / "telemetry_t3b.jsonl"))

from app.llm.factory import make_llm  # noqa: E402
from llm_stream import ollama_stream  # noqa: E402
from stt_cpp import WhisperCpp  # noqa: E402
from stt_fw import FasterWhisper  # noqa: E402
from tts_engines import Piper  # noqa: E402
from vad import FRAME, FRAME_MS, endpoint_frame, speech_probs  # noqa: E402
from wer import wer  # noqa: E402

STACKS = {
    "A": ("fw", "base", "Silero + faster-whisper base int8 (CPU) + Ollama llama3.2:3b + Piper alba"),
    "B": ("fw", "small", "Silero + faster-whisper small int8 (CPU) + Ollama llama3.2:3b + Piper alba"),
    "E": ("cpp", "base", "Silero + whisper.cpp base q5_1 (Metal) + Ollama llama3.2:3b + Piper alba"),
    "F": ("cpp", "small", "Silero + whisper.cpp small q5_1 (Metal) + Ollama llama3.2:3b + Piper alba"),
}
SPEC_START_MS = 300


def first_sentence(text):
    import re
    return re.split(r"(?<=[.!?])\s", text.strip())[0]


def probe(model, calls):
    """-> dict of streaming and parallel measurements for one turn's real calls (classify, then maybe phrase)."""
    out = {}
    seq = [ollama_stream(model, c.system, c.user, c.json_mode, c.max_tokens) for c in calls]
    for c, s in zip(calls, seq):
        out[f"{c.kind}_ttft"], out[f"{c.kind}_first_sentence"], out[f"{c.kind}_total"] = s.ttft_s, s.first_sentence_s, s.total_s
    classify = next(s for c, s in zip(calls, seq) if c.kind == "classify")
    phrase = next((s for c, s in zip(calls, seq) if c.kind == "phrase"), None)
    out["seq_streamed"] = classify.total_s + (phrase.first_sentence_s if phrase else 0.0)
    if phrase is None:
        out["parallel"] = out["seq_streamed"]
        return out
    got = {}

    def run(c):
        got[c.kind] = ollama_stream(model, c.system, c.user, c.json_mode, c.max_tokens)

    threads = [threading.Thread(target=run, args=(c,)) for c in calls]
    [t.start() for t in threads]
    [t.join() for t in threads]
    out["parallel"] = max(got["classify"].total_s, got["phrase"].first_sentence_s)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stack", required=True, choices=STACKS)
    ap.add_argument("--hangover", type=int, default=600)
    ap.add_argument("--turns", type=int, default=0, help="limit (default: all 34)")
    a = ap.parse_args()
    kind, size, desc = STACKS[a.stack]
    stt = FasterWhisper(size) if kind == "fw" else WhisperCpp(size)
    tts = Piper("en_GB-alba-medium")
    model = os.environ["OLLAMA_MODEL"]
    rec = Recorder()
    brain = Brain(lambda spec: TimedLLM(make_llm("ollama"), rec))
    manifest = list(csv.DictReader(open(SYNTH / "manifest.csv")))
    if a.turns:
        manifest = manifest[:a.turns]
    stt.transcribe(sf.read(SYNTH / f"{manifest[5]['id']}.wav", dtype="float32")[0][:16000 * 3])
    tts.first_chunk("Warm up.")
    for _ in range(2):  # warm the model: the first Ollama call includes loading it into memory
        brain.say("I built a chat application with websockets and postgres.")
        ollama_stream(model, "Reply JSON.", "ANSWER: x", True, 20)
    rows, saved = [], []
    prompts_file = DATA / f"prompts_{a.stack}.jsonl"
    for m in manifest:
        audio, _ = sf.read(SYNTH / f"{m['id']}.wav", dtype="float32")
        probs, _ = speech_probs(audio)
        f = endpoint_frame(probs, a.hangover)
        end = (f + 1) * FRAME if f is not None else len(audio)
        true_end = float(m["speech_end_s"])
        endpoint_delay = (f + 1) * FRAME_MS / 1000 - true_end
        text, stt_s = stt.transcribe(audio[:end])
        rec.clear()
        reply, ended, backend_wall, _ = brain.say(text)
        calls = list(rec.calls)
        real = {c.kind: c.real_s for c in calls}
        llm_real = sum(real.values())
        overhead = max(0.0, backend_wall - llm_real)
        tts_first, _, _, _ = tts.first_chunk(first_sentence(reply))
        p = probe(model, calls) if calls else {}
        base = endpoint_delay + stt_s + overhead + tts_first
        e2e = base + llm_real
        streamed = base + p["seq_streamed"] if p else base
        parallel = base + p["parallel"] if p else base
        spec = max(endpoint_delay, SPEC_START_MS / 1000 + stt_s) + overhead + tts_first + (p["parallel"] if p else 0.0)  # speculative STT + parallel LLM
        brain.clock.advance(true_end + e2e + len(reply.split()) / 2.7)
        saved.append({"turn": m["id"], "calls": [{"kind": c.kind, "system": c.system, "user": c.user, "json_mode": c.json_mode, "max_tokens": c.max_tokens} for c in calls]})
        rows.append([m["id"], m["words"], round(endpoint_delay * 1000), round(stt_s, 3), round(wer(m["text"], text), 3), len(calls), round(real.get("classify", 0), 3),
                     round(real.get("phrase", 0), 3), round(overhead * 1000, 1), round(tts_first, 3), round(e2e, 3),
                     *(round(p.get(k), 3) if p.get(k) is not None else "" for k in ("classify_ttft", "classify_total", "phrase_ttft", "phrase_first_sentence", "phrase_total")),
                     round(p["seq_streamed"], 3) if p else "", round(p["parallel"], 3) if p else "", round(streamed, 3), round(parallel, 3), round(spec, 3), first_sentence(reply)])
    prompts_file.write_text("\n".join(json.dumps(s) for s in saved) + "\n")
    tag = f"{a.stack}_h{a.hangover}"
    out = RESULTS / f"e2e_real_ollama_{tag}.csv"
    write_csv(out, ["turn", "words", "endpoint_delay_ms", "stt_final_s", "wer", "llm_calls", "classify_s", "phrase_s", "backend_overhead_ms", "tts_first_chunk_s", "e2e_s",
                    "classify_ttft_s", "classify_stream_total_s", "phrase_ttft_s", "phrase_first_sentence_s", "phrase_stream_total_s", "llm_seq_streamed_s",
                    "llm_parallel_s", "e2e_streamed_s", "e2e_parallel_s", "e2e_parallel_speculative_stt_s", "reply_first_sentence"], rows)
    write_meta(out, provider="live", model=["silero-vad", stt.name, f"ollama:{model}", tts.name], n=len(rows), n_unit="turns (synthetic speech, macOS say)",
               audio="synthetic", stack=desc, hangover_ms=a.hangover, llm_leg="real (Ollama, local)", sessions=brain.sessions,
               note="e2e_s: adapters as shipped (no streaming, classify then phrase, full phrase); *_streamed_s: first sentence of the phrase; *_parallel_s: classify and phrase started together")
    col = lambda i: [r[i] for r in rows if r[i] != ""]  # noqa: E731
    print(f"stack {a.stack} [{desc}] n={len(rows)} sessions={brain.sessions}")
    for name, i in (("E2E as shipped", 10), ("E2E first-sentence streamed", 18), ("E2E parallel classify+phrase", 19), ("E2E parallel + speculative STT", 20)):
        v = col(i)
        print(f"   {name:34} p50 {percentile(v, 50):.2f}s p95 {percentile(v, 95):.2f}s")
    print(f"   classify real p50 {percentile(col(6), 50):.2f}s | phrase real p50 {percentile(col(7), 50):.2f}s (turns with a phrase: {len(col(7))}) | "
          f"ttft classify {percentile(col(11), 50):.2f}s phrase {percentile(col(13), 50):.2f}s | stt p50 {percentile(col(3), 50):.2f}s")


if __name__ == "__main__":
    main()
