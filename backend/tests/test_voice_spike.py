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
