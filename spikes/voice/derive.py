"""Arithmetic on the measured files plus stated assumptions: what the measurements imply for 150 concurrent vivas, for Groq's free tier,
and for Plan B (push-to-talk). Every row says its inputs. Nothing here is a measurement of a loaded system.
Usage: python spikes/voice/derive.py"""
import csv
import json
import math
import statistics

from common import RESULTS, percentile, write_csv, write_meta

GROQ = {"rpm": 20, "rpd": 2000, "audio_s_per_day": 28800}   # https://console.groq.com/docs/rate-limits, retrieved 2026-10-08 (see SOURCES.md)
VIVA_S, STUDENTS_LIVE, STUDENTS_TOTAL = 900, 150, 350        # SPEC
rows = []


def add(topic, quantity, value, unit, inputs):
    rows.append([topic, quantity, round(value, 3) if isinstance(value, float) else value, unit, inputs])


def main():
    e2e = list(csv.DictReader(open(RESULTS / "e2e_stack_A_batch_h600.csv")))
    meta = json.loads((RESULTS / "e2e_stack_A_batch_h600.csv.meta.json").read_text())
    turns_per_viva = len(e2e) / meta["sessions"]
    audio_s = statistics.mean(float(r["audio_to_endpoint_s"]) for r in e2e)
    conc = list(csv.DictReader(open(RESULTS / "stt_concurrency.csv")))
    for turns in (turns_per_viva, 18.0):
        rate = turns / VIVA_S                                  # decodes per second per student
        need = STUDENTS_LIVE * rate
        label = f"{turns:.1f} answers per 15-min viva ({'measured in the E2E run: turns / sessions' if turns == turns_per_viva else 'assumed upper figure'})"
        add("150 live students", "STT decodes per second needed", need, "1/s", label)
        for model in ("faster-whisper-base-int8", "faster-whisper-small-int8"):
            best = max(float(r["decodes_per_s"]) for r in conc if r["model"] == model)
            add("150 live students", f"{model}: max students at 100% STT CPU (measured ceiling {best} decodes/s)", math.floor(best / rate), "students", label)
            add("150 live students", f"{model}: STT CPU utilisation at 150 students", need / best, "ratio", label)
    rate = turns_per_viva / VIVA_S
    add("Groq free tier", "simultaneous students the 20 requests/min limit allows", GROQ["rpm"] / 60 / rate, "students", f"{GROQ['rpm']} rpm, {turns_per_viva:.1f} answers/viva")
    add("Groq free tier", "vivas per day by the 2K requests/day limit", GROQ["rpd"] / turns_per_viva, "vivas", f"{GROQ['rpd']} rpd")
    add("Groq free tier", "vivas per day by the 28.8K audio-seconds/day limit", GROQ["audio_s_per_day"] / (turns_per_viva * audio_s), "vivas",
        f"mean {audio_s:.1f} s of audio per answer (E2E run)")
    add("Groq free tier", "days to run 350 vivas (binding limit)", STUDENTS_TOTAL / min(GROQ["rpd"] / turns_per_viva, GROQ["audio_s_per_day"] / (turns_per_viva * audio_s)), "days",
        "min of the two daily limits")
    a = [float(r["e2e_s"]) for r in e2e]
    hang = statistics.median(float(r["endpoint_delay_ms"]) for r in e2e) / 1000
    add("Plan B (push-to-talk)", "stack A E2E p50 with simulated LLM", percentile(a, 50), "s", "e2e_stack_A_batch_h600.csv")
    add("Plan B (push-to-talk)", "stack A E2E p50 without the endpoint wait (release of the button is the endpoint)", percentile(a, 50) - hang, "s",
        f"minus median endpoint delay {hang:.3f} s")
    add("Plan B (push-to-talk)", "stack A E2E p95 without the endpoint wait", percentile(a, 95) - hang, "s", "same")
    add("Plan B (push-to-talk)", "student time spent pressing the button over one viva, if each press costs 0.7 s (ASSUMED)", 0.7 * turns_per_viva, "s", "assumption, not measured")
    out = RESULTS / "derived_capacity.csv"
    write_csv(out, ["topic", "quantity", "value", "unit", "inputs"], rows)
    write_meta(out, provider="stub", model="n/a (arithmetic on measured files + stated assumptions)", n=len(rows), n_unit="derived quantities",
               note="not measurements of a loaded system; inputs are in each row")
    for r in rows:
        print(" | ".join(str(x) for x in r))


if __name__ == "__main__":
    main()
