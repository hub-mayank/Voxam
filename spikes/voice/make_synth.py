"""Voice the STUDENT_TURNS with macOS `say` (Indian-English voices) -> 16 kHz mono WAV in data/synth/ plus manifest.csv.
These are synthetic stand-ins for speech (clean, no accent variation inside a voice): labelled `synthetic` everywhere.
Every third turn gets thinking pauses after commas, and every fourth gets mild background noise.
Usage: python spikes/voice/make_synth.py"""
import csv
import subprocess

import numpy as np
import soundfile as sf

from common import SAMPLE_RATE, SYNTH
from corpus import STUDENT_TURNS

VOICES = ["Rishi", "Aman", "Tara"]  # the en_IN voices installed on this Mac (`say -v '?'`)
TAIL_SILENCE_S = 2.0


def main():
    SYNTH.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7)
    rows = []
    for i, text in enumerate(STUDENT_TURNS):
        voice = VOICES[i % len(VOICES)]
        spoken = text.replace(", ", ", [[slnc 450]] ") if i % 3 == 2 else text
        aiff, wav = SYNTH / f"t{i:02d}.aiff", SYNTH / f"t{i:02d}.wav"
        subprocess.run(["say", "-v", voice, "-r", "165", "-o", str(aiff), spoken], check=True)
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(aiff), str(wav)], check=True)
        aiff.unlink()
        audio, sr = sf.read(wav, dtype="float32")
        assert sr == SAMPLE_RATE
        lead = np.zeros(int(0.3 * SAMPLE_RATE), dtype="float32")
        speech = np.concatenate([lead, audio])
        speech_end = len(speech) / SAMPLE_RATE
        out = np.concatenate([speech, np.zeros(int(TAIL_SILENCE_S * SAMPLE_RATE), dtype="float32")])
        noisy = i % 4 == 3
        if noisy:
            out = out + rng.normal(0, 0.004, out.shape).astype("float32")  # about 35 dB below a typical speech peak
        sf.write(wav, out, SAMPLE_RATE, subtype="PCM_16")
        rows.append([f"t{i:02d}", voice, int(i % 3 == 2), int(noisy), round(speech_end, 3), round(len(out) / SAMPLE_RATE, 3), len(text.split()), text])
    with open(SYNTH / "manifest.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "voice", "has_pauses", "noisy", "speech_end_s", "duration_s", "words", "text"])
        w.writerows(rows)
    print(f"{len(rows)} turns, speech {min(r[4] for r in rows):.1f}-{max(r[4] for r in rows):.1f} s")


if __name__ == "__main__":
    main()
