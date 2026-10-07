"""Word error rate with an explicit, tested normalization. Used on English clips and on Hinglish (Roman-script) references.

Normalization (applied to reference AND hypothesis, so only real differences count):
  1. Unicode NFKC, lowercase.
  2. Devanagari in the text is transliterated to Roman (ITRANS-like, casual spelling) because Whisper often writes Hindi words
     in Devanagari while our Hinglish references are Roman. See `to_roman`.
  3. Digits become words ("62" -> "sixty two") because references are spelled out.
  4. Hyphens and punctuation become spaces, except apostrophes inside words. Whitespace collapsed.
Three numbers are reported: `strict` (words must match), and for Hinglish also `skeleton` (each word reduced to its consonant
skeleton, which forgives casual-spelling variants like mein/main/men but also hides some real errors). Hinglish has no standard
Roman spelling, so `strict` is a pessimistic number and `skeleton` an optimistic one; neither is a clean accuracy measure."""
import re
import unicodedata

import jiwer
from indic_transliteration import sanscript

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def number_words(n: int) -> str:
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + (" " + ONES[n % 10] if n % 10 else "")
    if n < 1000:
        return ONES[n // 100] + " hundred" + (" " + number_words(n % 100) if n % 100 else "")
    if n < 1_000_000:
        return number_words(n // 1000) + " thousand" + (" " + number_words(n % 1000) if n % 1000 else "")
    return " ".join(ONES[int(d)] for d in str(n))  # very long numbers: digit by digit


def to_roman(text: str) -> str:
    """Devanagari -> casual Roman: ITRANS, then drop case and diacritic marks (aa->a, ii->i, uu->u, M->n)."""
    if not DEVANAGARI.search(text):
        return text
    roman = sanscript.transliterate(text, sanscript.DEVANAGARI, sanscript.ITRANS)
    roman = roman.replace("M", "n").replace("N", "n").replace("~n", "n").replace(".h", "").replace("H", "h")
    roman = roman.lower()
    for a, b in (("aa", "a"), ("ii", "i"), ("uu", "u"), ("ee", "i"), ("oo", "u"), ("shh", "sh"), (".n", "n")):
        roman = roman.replace(a, b)
    return roman


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = to_roman(text)
    text = re.sub(r"\d+", lambda m: " " + number_words(int(m.group())) + " ", text)
    text = text.replace("-", " ").replace("’", "'")
    text = re.sub(r"(?<![a-z])'|'(?![a-z])", " ", text)  # apostrophes that are not inside a word
    text = re.sub(r"[^a-z' ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def skeleton(word: str) -> str:
    """Consonant skeleton for forgiving Roman spelling variants: keep the first letter, drop vowels and y/w/h after it."""
    if not word:
        return word
    rest = re.sub(r"[aeiouywh']", "", word[1:])
    rest = re.sub(r"(.)\1+", r"\1", rest)
    return word[0] + rest


def wer(reference: str, hypothesis: str, mode: str = "strict") -> float:
    ref, hyp = normalize(reference), normalize(hypothesis)
    if mode == "skeleton":
        ref, hyp = " ".join(skeleton(w) for w in ref.split()), " ".join(skeleton(w) for w in hyp.split())
    if not ref:
        raise ValueError("empty reference after normalization")
    if not hyp:
        return 1.0
    return jiwer.wer(ref, hyp)


def counts(reference: str, hypothesis: str):
    """-> (substitutions, deletions, insertions, reference_words) after normalization."""
    ref, hyp = normalize(reference), normalize(hypothesis)
    out = jiwer.process_words(ref, hyp or "")
    return out.substitutions, out.deletions, out.insertions, len(ref.split())
