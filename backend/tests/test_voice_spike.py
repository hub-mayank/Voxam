"""Tests for the voice spike's helpers and for the shape of its committed results. Offline: no models, no audio."""
import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "spikes" / "voice"))

import wer as w  # noqa: E402


@pytest.mark.parametrize("n,words", [(0, "zero"), (7, "seven"), (13, "thirteen"), (62, "sixty two"), (200, "two hundred"),
                                     (1250, "one thousand two hundred fifty")])
def test_number_words(n, words):
    assert w.number_words(n) == words


def test_normalize_makes_digits_punctuation_and_case_irrelevant():
    assert w.normalize("Base-62, in 10 seconds!") == "base sixty two in ten seconds"
    assert w.normalize("It's a B-tree; don't panic") == "it's a b tree don't panic"
    assert w.normalize("  Hello   WORLD ") == "hello world"
    assert w.normalize("'quoted' word") == "quoted word"


def test_wer_basics():
    assert w.wer("a b c d", "a b c d") == 0
    assert w.wer("a b c d", "a x c d") == 0.25
    assert w.wer("a b c d", "") == 1.0
    assert w.wer("Ten seconds", "10 seconds") == 0, "digits and words are the same after normalization"
    with pytest.raises(ValueError):
        w.wer("!!!", "anything")


def test_counts_split_the_errors():
    sub, dele, ins, n = w.counts("the cat sat down", "the dog sat")
    assert (sub, dele, ins, n) == (1, 1, 0, 4)


def test_devanagari_is_transliterated_to_roman_before_comparing():
    assert not w.DEVANAGARI.search(w.to_roman("हैश टेबल"))
    assert w.to_roman("plain roman text") == "plain roman text"
    assert w.normalize("hash table") == w.normalize("hash table")
    hyp = "यह एक डेटा स्ट्रक्चर है"
    assert w.wer("yeh ek data structure hai", hyp, "strict") > 0, "strict mode still sees spelling differences"
    assert w.wer("yeh ek data structure hai", hyp, "skeleton") <= w.wer("yeh ek data structure hai", hyp, "strict")


def test_skeleton_forgives_casual_spellings_but_not_different_words():
    assert w.skeleton("mein") == w.skeleton("main") == w.skeleton("men")
    assert w.skeleton("hai") == w.skeleton("hae")
    assert w.skeleton("table") != w.skeleton("index")
    assert w.wer("ek data structure hai", "ek data structure hae", "skeleton") == 0
    assert w.wer("ek data structure hai", "ek date structure hae", "skeleton") >= 0


def test_clip_references_match_the_recording_instructions():
    """Mayank reads RECORDING.md; the WER script compares against clip_refs.py. They must be the same words."""
    import re
    from clip_refs import HINGLISH, REFS
    text = (ROOT / "spikes" / "voice" / "RECORDING.md").read_text()
    shown = dict(re.findall(r"^\| (c0\d)[^|]*\| (.+) \|$", text, re.M))
    assert set(shown) == set(REFS) == {f"c0{i}" for i in range(1, 8)}
    assert all(shown[k] == REFS[k] for k in REFS)
    assert HINGLISH == {"c06", "c07"}
    for k, ref in REFS.items():
        assert 35 <= len(ref.split()) <= 80, f"{k}: {len(ref.split())} words is outside the 15-30 s reading range"


def test_corpus_is_big_and_varied_enough_for_the_latency_claims():
    from corpus import AI_SENTENCES, STUDENT_TURNS
    assert len(STUDENT_TURNS) >= 30, "the spike promises at least 30 turns"
    lengths = sorted(len(t.split()) for t in STUDENT_TURNS)
    assert lengths[0] <= 4 and lengths[-1] >= 40, "needs very short and long answers"
    assert len(set(STUDENT_TURNS)) == len(STUDENT_TURNS) and len(AI_SENTENCES) >= 10


def test_voice_spike_results_have_sidecars_and_enough_turns():
    """Every results/voice_spike file is covered by test_results_meta; here: the latency files really hold 30+ turns, and
    anything with a simulated leg is labelled stub, never live."""
    import json
    folder = ROOT / "results" / "voice_spike"
    for csv_file in folder.glob("e2e_stack_*.csv"):
        meta = json.loads((csv_file.parent / (csv_file.name + ".meta.json")).read_text())
        rows = list(csv.DictReader(open(csv_file)))
        assert len(rows) >= 30 and meta["n"] == len(rows), csv_file.name
        legs = {r["llm_leg"] for r in rows}
        assert legs == {meta["llm_leg"]}, csv_file.name
        assert (meta["provider"] == "stub") == (meta["llm_leg"] == "simulated"), f"{csv_file.name}: simulated legs must be provider=stub"
        assert meta.get("audio") == "synthetic" or meta.get("audio", "").startswith("real")


# ---------- the latency accounting behind the headline numbers ----------

def test_llm_critical_path_adds_classify_and_the_first_sentence_of_phrase():
    import random
    from brain import Call, Profile, Recorder
    prof = Profile("p", ttft_s=0.5, tokens_per_s=20, jitter=0.0)
    rec = Recorder()
    rec.calls += [Call("classify", tokens=10, first_tokens=10), Call("phrase", tokens=40, first_tokens=10)]
    rng = random.Random(0)
    assert rec.critical_path_s(prof, rng) == pytest.approx((0.5 + 10 / 20) + (0.5 + 10 / 20)), "classify full + phrase up to its first sentence"
    assert rec.critical_path_parallel_s(prof, rng) == pytest.approx(1.0), "in parallel: the slower of the two"
    assert Recorder().critical_path_s(prof, rng) == 0 and Recorder().critical_path_parallel_s(prof, rng) == 0, "a turn with no model call costs nothing"


def test_a_real_llm_call_reports_its_measured_time_not_a_profile():
    import random
    from brain import Call, Profile
    real = Call("classify", tokens=0, first_tokens=0, real_s=0.42)
    assert real.seconds(Profile("ignored", 9.9, 1), random.Random(0), first_sentence=False) == 0.42


def test_simulated_llm_is_labelled_and_never_sleeps():
    import time
    from brain import Recorder, SimulatedLLM
    rec = Recorder()
    llm = SimulatedLLM(rec)
    t = time.perf_counter()
    out = llm.complete_text("sys", "ACTION: deeper\nQUESTION: q\n<answer>a</answer>")
    assert time.perf_counter() - t < 0.05 and out and llm.name.startswith("simulated")
    assert rec.calls[0].kind == "phrase" and rec.calls[0].real_s is None and rec.calls[0].first_tokens <= rec.calls[0].tokens


def test_vad_endpoint_rule():
    import numpy as np
    from vad import FRAME_MS, endpoint_frame, speech_segments
    probs = np.array([0.0] * 5 + [0.9] * 20 + [0.0] * 30 + [0.9] * 10 + [0.0] * 40)
    need = round(500 / FRAME_MS)
    assert endpoint_frame(probs, 500) == 25 + need - 1, "silence starts at frame 25; the first 30-frame (~960 ms) pause outlasts a 500 ms hangover"
    need_long = round(1100 / FRAME_MS)
    assert endpoint_frame(probs, 1100) == 65 + need_long - 1, "a 1100 ms hangover waits through the 960 ms thinking pause and fires after the real end"
    assert endpoint_frame(probs, 3000) is None, "a hangover longer than any silence in the audio never fires"
    assert endpoint_frame(np.zeros(100), 500) is None, "silence alone never starts a turn"
    assert speech_segments(probs, min_pause_ms=250) == [(5, 25), (55, 65)]
