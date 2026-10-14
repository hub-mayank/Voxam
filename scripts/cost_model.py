"""T9: rupees per viva and a capacity plan, from measured tokens x priced rows. Nothing here is typed in by hand except the one
assumption flagged below (answers per viva).
Reads:  docs/pricing.csv (every price with its URL and retrieval date), results/groq_interview_tokens.csv (live classify/phrase calls),
        results/groq_live_tokens.csv (live scorer calls), results/load/*.csv and results/voice_spike/stt_concurrency.csv (measured capacity),
        config/free_tier_limits.json (provider limits).
Writes: results/cost_model.csv and results/capacity_plan.csv, each with a .meta.json sidecar.
Usage:  python scripts/cost_model.py [--answers 11] [--students 350] [--concurrent 150]"""
import argparse
import csv
import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.results_meta import write_meta  # noqa: E402

SCORER_RUNS = 3  # the median of 3 runs (D-scorer); each run is one score call
SECONDS_PER_ANSWER = 80  # assumption: a 15 minute viva is about 11 answers; the same figure the load report uses


def rows_of(path):
    with open(ROOT / path, newline="") as f:
        return list(csv.DictReader(f))


def mean_tokens(rows, kind):
    pick = [r for r in rows if r["kind"] == kind]
    return len(pick), statistics.mean(int(r["tokens_in"]) for r in pick), statistics.mean(int(r["tokens_out"]) for r in pick)


def prices():
    table = {}
    for r in rows_of("docs/pricing.csv"):
        table[(r["item"], r["provider"], r["model"])] = float(r["usd_per_unit"])
    return table


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--answers", type=int, default=11, help="answers per viva (assumption: 900 s / 80 s)")
    ap.add_argument("--students", type=int, default=350)
    ap.add_argument("--concurrent", type=int, default=150)
    a = ap.parse_args()
    price = prices()
    fx = price[("fx", "usd_inr", "")]
    interview = rows_of("results/groq_interview_tokens.csv")
    scorer = [r for r in rows_of("results/groq_live_tokens.csv") if r["kind"] == "score"]
    answers_seen = sum(len(rows_of(f"results/{n}.csv")) for n in ("voice_e2e_local_groq", "voice_e2e_local_groq_strict_pacing"))
    n_c, c_in, c_out = mean_tokens(interview, "classify")
    n_p, p_in, p_out = mean_tokens(interview, "phrase")
    classify_per_answer, phrase_per_answer = n_c / answers_seen, n_p / answers_seen
    s_in = statistics.mean(int(r["tokens_in"]) for r in scorer)
    s_out = statistics.mean(int(r["tokens_out"]) for r in scorer)
    interview_in = a.answers * (classify_per_answer * c_in + phrase_per_answer * p_in)
    interview_out = a.answers * (classify_per_answer * c_out + phrase_per_answer * p_out)
    score_in, score_out = SCORER_RUNS * s_in, SCORER_RUNS * s_out

    def llm_usd(provider, model, tokens_in, tokens_out):
        return (tokens_in * price[("llm_input", provider, model)] + tokens_out * price[("llm_output", provider, model)]) / 1e6

    # interview model x scorer model; the interview token counts were measured on groq gpt-oss-20b, so other interview models are
    # priced on the same token counts (an approximation, stated in the note)
    scenarios = [
        ("all local (Ollama + whisper.cpp + Piper)", None, None),
        ("groq gpt-oss-20b interview + groq gpt-oss-20b scorer", ("groq", "openai/gpt-oss-20b"), ("groq", "openai/gpt-oss-20b")),
        ("groq gpt-oss-20b interview + groq gpt-oss-120b scorer", ("groq", "openai/gpt-oss-20b"), ("groq", "openai/gpt-oss-120b")),
        ("groq gpt-oss-20b interview + gemini 2.5 flash-lite scorer", ("groq", "openai/gpt-oss-20b"), ("gemini", "gemini-2.5-flash-lite")),
        ("groq gpt-oss-20b interview + gemini 3.1 flash-lite scorer", ("groq", "openai/gpt-oss-20b"), ("gemini", "gemini-3.1-flash-lite")),
        ("gemini 2.5 flash-lite interview + gemini 2.5 flash-lite scorer", ("gemini", "gemini-2.5-flash-lite"), ("gemini", "gemini-2.5-flash-lite")),
    ]
    out = []
    for name, iv, sc in scenarios:
        usd_iv = llm_usd(*iv, interview_in, interview_out) if iv else 0.0
        usd_sc = llm_usd(*sc, score_in, score_out) if sc else 0.0
        total = usd_iv + usd_sc
        out.append({"scenario": name, "interview_usd": round(usd_iv, 5), "scoring_usd": round(usd_sc, 5), "usd_per_viva": round(total, 5),
                    "inr_per_viva": round(total * fx, 3), f"inr_per_{a.students}": round(total * fx * a.students, 1)})
    stt_hour = price[("stt", "groq", "whisper-large-v3-turbo")]
    out.append({"scenario": "optional: groq whisper-large-v3-turbo instead of local STT (15 min of audio, added to any row)",
                "interview_usd": round(0.25 * stt_hour, 5), "scoring_usd": 0.0, "usd_per_viva": round(0.25 * stt_hour, 5),
                "inr_per_viva": round(0.25 * stt_hour * fx, 3), f"inr_per_{a.students}": round(0.25 * stt_hour * fx * a.students, 1)})
    path = ROOT / "results" / "cost_model.csv"
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    write_meta(path, provider="live", model="derived: measured groq gpt-oss-20b tokens x docs/pricing.csv", n=len(interview) + len(scorer),
               n_unit="live calls the token means come from", answers_per_viva=a.answers, scorer_runs=SCORER_RUNS, fx_inr_per_usd=fx,
               mean_tokens={"classify": [round(c_in, 1), round(c_out, 1)], "phrase": [round(p_in, 1), round(p_out, 1)],
                            "score": [round(s_in, 1), round(s_out, 1)]},
               calls_per_answer={"classify": round(classify_per_answer, 3), "phrase": round(phrase_per_answer, 3)},
               note="arithmetic over measured token counts; other models are priced on gpt-oss-20b's token counts; local providers cost "
                    "nothing marginal (D15) but hardware and electricity are not included; answers per viva is an assumption")

    # ---- capacity plan for `concurrent` students (quota arithmetic against measured limits) ----
    limits = json.load(open(ROOT / "config" / "free_tier_limits.json"))["limits"]
    lim = next(r for r in limits if r["provider"] == "groq" and r["model"] == "openai/gpt-oss-20b")
    answers_s = a.concurrent / SECONDS_PER_ANSWER
    calls_min = answers_s * (classify_per_answer + phrase_per_answer) * 60
    tokens_min = answers_s * 60 * (classify_per_answer * (c_in + c_out) + phrase_per_answer * (p_in + p_out))
    rpm_cap = math.floor(0.9 * lim["rpm"])
    tpm_cap = math.floor(0.9 * lim["tpm"])
    score_tokens_all = a.concurrent * SCORER_RUNS * (s_in + s_out)
    stt = [r for r in rows_of("results/voice_spike/stt_concurrency.csv") if r["model"] == "faster-whisper-base-int8"]
    best = max(stt, key=lambda r: int(r["concurrent_decodes"]) / float(r["decode_p50_s"]))
    stt_per_s = int(best["concurrent_decodes"]) / float(best["decode_p50_s"])
    stt_answers_per_s = stt_per_s * float(best["clip_audio_s"]) / 7.0  # a typical answer is taken as 7 s of speech (assumption)
    piper = rows_of("results/load/piper_procs.csv")
    piper_best = max(float(r["sentences_per_s"]) for r in piper)
    plan = [
        ("interview LLM calls per minute", round(calls_min, 1), f"{a.concurrent} students / {SECONDS_PER_ANSWER} s per answer x measured calls per answer"),
        ("interview tokens per minute", round(tokens_min), "same arithmetic x measured tokens per call"),
        (f"groq {lim['model']} requests/min allowed (0.9 x rpm)", rpm_cap, "config/free_tier_limits.json"),
        (f"groq {lim['model']} tokens/min allowed (0.9 x tpm)", tpm_cap, "config/free_tier_limits.json"),
        ("model keys needed for requests", math.ceil(calls_min / rpm_cap), "each free model key has its own limits"),
        ("model keys needed for tokens", math.ceil(tokens_min / tpm_cap), "each free model key has its own limits"),
        ("scoring tokens if all end together", round(score_tokens_all), f"{a.concurrent} x {SCORER_RUNS} runs x measured tokens"),
        (f"days of one groq model's token cap (0.9 x {lim['tpd']}) to score them", round(score_tokens_all / (0.9 * lim["tpd"]), 1), "tpd"),
        ("STT answers per second one machine decodes (measured plateau)", round(stt_answers_per_s, 2),
         "stt_concurrency.csv best throughput; a 7 s answer is an assumption"),
        ("answers per second needed", round(answers_s, 2), f"{a.concurrent} / {SECONDS_PER_ANSWER}"),
        ("Piper sentences per second one machine makes (measured best)", round(piper_best, 2), "results/load/piper_procs.csv"),
    ]
    path = ROOT / "results" / "capacity_plan.csv"
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["quantity", "value", "source"])
        w.writerows(plan)
    write_meta(path, provider="live", model="derived: measured tokens, limits and capacities", n=len(plan), n_unit="quantities",
               concurrent=a.concurrent, note="arithmetic only; students per answer interval and answer length are assumptions; no machine "
                                             "was run at this load with real models")
    print(f"{'scenario':70} {'INR/viva':>9} {'INR/' + str(a.students):>10}")
    for r in out:
        print(f"{r['scenario'][:70]:70} {r['inr_per_viva']:>9} {r[f'inr_per_{a.students}']:>10}")
    for q, v, s in plan:
        print(f"{q:70} {v}")


if __name__ == "__main__":
    main()
