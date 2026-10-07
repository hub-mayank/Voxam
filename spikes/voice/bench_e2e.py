"""End to end, per turn: 'student stops speaking' -> 'first AI audio chunk', for a full stack, on the synthetic turns.
  endpoint delay (VAD hangover, measured on the audio) + STT final decode (measured) + LLM critical path (simulated unless --llm real)
  + backend overhead (measured: the real answer endpoint, DB included) + TTS first chunk (measured)
The LLM leg is `simulated` (token counts from the real engine x an ASSUMED latency profile) until Ollama is installed; every row says so.
Usage: python spikes/voice/bench_e2e.py --stack B [--hangover 600] [--stt-mode batch|segmented] [--llm simulated|ollama]"""
import argparse
import csv
import os
import random
import statistics

import soundfile as sf

from bench_stt import pieces_for
from brain import Brain, Profile, Recorder, SimulatedLLM, TimedLLM
from common import RESULTS, SYNTH, percentile, write_csv, write_meta
from stt_fw import FasterWhisper
from tts_engines import Kokoro, MacSay, Piper
from vad import FRAME, FRAME_MS, endpoint_frame, speech_probs
from wer import wer

STACKS = {  # name: (whisper size, tts factory, description)
    "A": ("base", lambda: Piper("en_US-lessac-medium"), "Silero + faster-whisper base int8 + Piper lessac"),
    "B": ("small", lambda: Piper("en_US-lessac-medium"), "Silero + faster-whisper small int8 + Piper lessac"),
    "C": ("medium", lambda: Kokoro("af_heart", stream=True), "Silero + faster-whisper medium int8 + Kokoro af_heart"),
    "D": ("small", lambda: MacSay("Rishi"), "Silero + faster-whisper small int8 + macOS say (Rishi, en_IN)"),
}
PROFILES = [Profile("fast-0.2s", 0.2, 40), Profile("local-3b-0.4s", 0.4, 28), Profile("slow-0.8s", 0.8, 20), Profile("api-1.5s", 1.5, 40)]
DEFAULT_PROFILE = "local-3b-0.4s"
SPEC_START_MS = 300   # speculative STT starts after this much silence (and is thrown away if the student speaks again)


def first_sentence(text):
    import re
    return re.split(r"(?<=[.!?])\s", text.strip())[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stack", required=True, choices=STACKS)
    ap.add_argument("--hangover", type=int, default=600)
    ap.add_argument("--stt-mode", default="batch", choices=["batch", "segmented"])
    ap.add_argument("--llm", default="simulated", choices=["simulated", "ollama"])
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--tag", default="", help="suffix for the output files (e.g. a repeat run)")
    args = ap.parse_args()
    size, tts_factory, desc = STACKS[args.stack]
    stt, tts = FasterWhisper(size, cpu_threads=args.threads), tts_factory()
    rec = Recorder()
    simulated = args.llm == "simulated"
    if simulated:
        factory = lambda spec: SimulatedLLM(rec)  # noqa: E731
    else:
        from app.llm.factory import make_llm
        os.environ.setdefault("OLLAMA_MODEL", "llama3.2:3b")
        factory = lambda spec: TimedLLM(make_llm("ollama"), rec)  # noqa: E731
    brain = Brain(factory)
    manifest = list(csv.DictReader(open(SYNTH / "manifest.csv")))
    stt.transcribe(sf.read(SYNTH / f"{manifest[5]['id']}.wav", dtype="float32")[0][:16000 * 3])  # warm-ups, not recorded
    tts.first_chunk("Warm up.")
    brain.say("I built a chat application with websockets.")
    rngs = {p.name: random.Random(11) for p in PROFILES}
    rngs_par = {p.name: random.Random(11) for p in PROFILES}
    rows, sens = [], {p.name: [] for p in PROFILES}
    par_e2e = []
    for m in manifest:
        audio, _ = sf.read(SYNTH / f"{m['id']}.wav", dtype="float32")
        probs, costs = speech_probs(audio)
        f = endpoint_frame(probs, args.hangover)
        end = (f + 1) * FRAME if f is not None else len(audio)
        true_end = float(m["speech_end_s"])
        endpoint_delay = (f + 1) * FRAME_MS / 1000 - true_end if f is not None else float("nan")
        heard = audio[:end]
        if args.stt_mode == "batch":
            text, stt_s = stt.transcribe(heard)
        else:
            texts, times = [], []
            for a, b in [p for p in pieces_for(heard, probs[:f + 1], len(heard)) if (p[1] - p[0]) / 16000 >= 0.3]:
                t, s = stt.transcribe(heard[a:b])
                texts.append(t), times.append(s)
            text, stt_s = " ".join(texts), times[-1]  # only the last piece is decoded after the endpoint
        rec.clear()
        reply, ended, backend_wall, _ = brain.say(text)
        llm_prof = {p.name: rec.critical_path_s(p if simulated else None, rngs[p.name]) for p in PROFILES} if simulated else {DEFAULT_PROFILE: rec.critical_path_s(None, None)}
        par_llm = rec.critical_path_parallel_s(next(p for p in PROFILES if p.name == DEFAULT_PROFILE), rngs_par[DEFAULT_PROFILE]) if simulated else None
        first = first_sentence(reply)
        tts_first, tts_audio, _, _ = tts.first_chunk(first)
        overhead = backend_wall  # the simulated LLM never sleeps, so this is the engine + database only (real LLM: includes its wall time)
        if not simulated:
            overhead = max(0.0, backend_wall - llm_prof[DEFAULT_PROFILE])
        for name, llm_s in llm_prof.items():
            e2e = endpoint_delay + stt_s + llm_s + overhead + tts_first
            spec = max(endpoint_delay, SPEC_START_MS / 1000 + stt_s) + llm_s + overhead + tts_first
            sens[name].append((e2e, spec))
        e2e, spec = sens[DEFAULT_PROFILE][-1]
        par_e2e.append(None if par_llm is None else endpoint_delay + stt_s + par_llm + overhead + tts_first)
        brain.clock.advance(true_end + e2e + len(reply.split()) / 2.7)
        rows.append([m["id"], m["words"], round(len(heard) / 16000, 2), round(endpoint_delay * 1000), round(stt_s, 3), round(wer(m["text"], text), 3), len(rec.calls),
                     round(llm_prof[DEFAULT_PROFILE], 3), round(overhead * 1000, 1), round(tts_first, 3), round(e2e, 3), round(spec, 3), "simulated" if simulated else "real", first, "" if par_e2e[-1] is None else round(par_e2e[-1], 3)])
    tag = f"{args.stack}_{args.stt_mode}_h{args.hangover}" + ("" if simulated else "_ollama") + args.tag
    out = RESULTS / f"e2e_stack_{tag}.csv"
    write_csv(out, ["turn", "words", "audio_to_endpoint_s", "endpoint_delay_ms", "stt_final_s", "wer", "llm_calls", "llm_critical_path_s", "backend_overhead_ms",
                    "tts_first_chunk_s", "e2e_s", "e2e_speculative_stt_s", "llm_leg", "reply_first_sentence", "e2e_parallel_llm_s"], rows)
    models = ["silero-vad", stt.name, ("simulated-llm (profile %s)" % DEFAULT_PROFILE) if simulated else os.environ.get("OLLAMA_MODEL", "ollama"), tts.name]
    write_meta(out, provider="stub" if simulated else "live", model=models, n=len(rows), n_unit="turns (synthetic speech, macOS say)", audio="synthetic",
               stack=desc, hangover_ms=args.hangover, stt_mode=args.stt_mode, llm_leg="simulated" if simulated else "real",
               llm_profile=({"name": DEFAULT_PROFILE, "ttft_s": 0.4, "tokens_per_s": 28, "note": "assumed, not measured"} if simulated else None),
               legs_measured=["vad endpoint", "stt", "backend answer endpoint", "tts"] , sessions=brain.sessions)
    e = [r[10] for r in rows]
    print(f"stack {args.stack} [{desc}] stt={args.stt_mode} H={args.hangover}ms llm={'SIMULATED' if simulated else 'real'} n={len(rows)} sessions={brain.sessions}")
    print(f"  E2E p50 {percentile(e, 50):.2f}s p95 {percentile(e, 95):.2f}s | components p50: endpoint {percentile([r[3] for r in rows], 50):.0f} ms, stt {percentile([r[4] for r in rows], 50):.2f}s, "
          f"llm {percentile([r[7] for r in rows], 50):.2f}s, backend {percentile([r[8] for r in rows], 50):.0f} ms, tts {percentile([r[9] for r in rows], 50):.3f}s | with speculative STT p50 {percentile([r[11] for r in rows], 50):.2f}s p95 {percentile([r[11] for r in rows], 95):.2f}s")
    if simulated:
        print(f"  with classify and phrase in parallel (speculative phrasing): E2E p50 {percentile(par_e2e, 50):.2f}s p95 {percentile(par_e2e, 95):.2f}s")
        sout = RESULTS / f"e2e_sensitivity_{tag}.csv"
        srows = [[name, round(percentile([x[0] for x in v], 50), 3), round(percentile([x[0] for x in v], 95), 3), round(percentile([x[1] for x in v], 50), 3),
                  round(percentile([x[1] for x in v], 95), 3)] for name, v in sens.items()]
        write_csv(sout, ["llm_profile_assumed", "e2e_p50_s", "e2e_p95_s", "e2e_speculative_p50_s", "e2e_speculative_p95_s"], srows)
        write_meta(sout, provider="stub", model=models, n=len(rows), n_unit="turns per assumed LLM profile", llm_leg="simulated",
                   profiles=[{"name": p.name, "ttft_s": p.ttft_s, "tokens_per_s": p.tokens_per_s} for p in PROFILES], note="LLM latency profiles are assumptions")
        for r in srows:
            print(f"  LLM assumed {r[0]:15} -> E2E p50 {r[1]:.2f}s p95 {r[2]:.2f}s | speculative STT p50 {r[3]:.2f}s p95 {r[4]:.2f}s")


if __name__ == "__main__":
    main()
