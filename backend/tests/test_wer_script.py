"""TJ-6: offline WER, strict manifest validation and honest evidence provenance."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import wave
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "wer.py"
@pytest.fixture
def script():
    pytest.importorskip("jiwer")
    pytest.importorskip("indic_transliteration")
    spec = importlib.util.spec_from_file_location("tejas_wer_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
@pytest.fixture
def files(tmp_path):
    refs, hypotheses, out = (tmp_path / name for name in ("refs.csv", "hyp.csv", "wer_test.csv"))
    refs.write_text('clip,kind,reference\nen,english,"the cat, sat down"\nhi,hinglish,mein data hai\n')
    hypotheses.write_text('clip,text\nen,the dog sat\nhi,main data hae\n')
    return refs, hypotheses, out
def cli(files, *extra):
    refs, hypotheses, out = files
    return subprocess.run([sys.executable, str(SCRIPT), "--refs", str(refs), "--hypotheses",
                           str(hypotheses), "--out", str(out), *extra], cwd=files[0].parent,
                          capture_output=True, text=True)
def test_help_needs_no_optional_dependencies():
    run = subprocess.run([sys.executable, "-S", str(SCRIPT), "--help"], capture_output=True, text=True)
    assert run.returncode == 0 and "--hypotheses" in run.stdout
@pytest.mark.parametrize("ref,hyp,expected,counts", [
    ("the cat sat down", "the dog sat", 0.5, (1, 1, 0, 4)),
    ("the cat sat down", "", 1.0, (0, 4, 0, 4)),
    ("Base-62, in 10 seconds!", "base sixty two in ten seconds", 0.0, (0, 0, 0, 6)),
    ("hai", "है", 0.0, (0, 0, 0, 1)),
    ("cat", "dog dog dog", 3.0, (1, 0, 2, 1)),
])
def test_normalized_wer_and_error_counts(script, ref, hyp, expected, counts):
    row = script.compare([{"clip": "c1", "kind": "hinglish", "reference": ref}], {"c1": hyp})[0]
    assert row["wer_strict"] == pytest.approx(expected)
    assert tuple(row[k] for k in ("substitutions", "deletions", "insertions", "ref_words")) == counts
def test_hinglish_skeleton_and_exact_clip_coverage(script, files):
    refs = script.read_refs(files[0])
    rows = {r["clip"]: r for r in script.compare(refs, script.read_hypotheses(files[1]))}
    assert rows["hi"]["wer_strict"] > 0 and rows["hi"]["wer_skeleton"] == 0
    for hypotheses in ({"en": "hello"}, {"en": "hello", "hi": "hi", "extra": "x"}):
        with pytest.raises(ValueError):
            script.compare(refs, hypotheses)
@pytest.mark.parametrize("text", ["", "clip,kind,reference\n", "clip,reference\nc1,text\n",
    "clip,kind,reference\nc1,english,hi\nc1,english,bye\n", "clip,kind,reference\nc1,other,hi\n",
    "clip,kind,reference\nc1,english,!!!\n", "clip,kind,reference\nc1,english\n"])
def test_bad_reference_manifests_are_rejected(script, tmp_path, text):
    path = tmp_path / "refs.csv"
    path.write_text(text)
    with pytest.raises(ValueError):
        script.read_refs(path)
def test_offline_cli_provenance_and_failure_preserves_existing_results(script, files):
    refs, hypotheses, out = files
    meta_path = Path(str(out) + ".meta.json")
    assert cli(files).returncode != 0, "offline evidence must identify its model"
    assert not out.exists() and not meta_path.exists()
    run = cli(files, "--model", "offline-test")
    assert run.returncode == 0, run.stderr
    meta = json.loads(meta_path.read_text())
    assert (meta["provider"], meta["model"], meta["n"], meta["n_unit"]) == ("stub", "offline-test", 2, "unique clips")
    assert meta["mode"] == "offline" and meta["normalization"] == "spike-v1"
    assert meta["refs_sha256"] == hashlib.sha256(refs.read_bytes()).hexdigest()
    assert meta["hypotheses_sha256"] == hashlib.sha256(hypotheses.read_bytes()).hexdigest()
    assert meta["normalization_sha256"] == hashlib.sha256((ROOT / "spikes/voice/wer.py").read_bytes()).hexdigest()
    assert len(list(csv.DictReader(out.open()))) == 2
    directory = out.with_name("directory.csv")
    directory.mkdir()
    sentinel = Path(str(directory) + ".meta.json")
    sentinel.write_text("preserve existing sidecar")
    assert cli((refs, hypotheses, directory), "--model", "offline-test").returncode != 0
    assert directory.is_dir() and sentinel.read_text() == "preserve existing sidecar"
    before = out.read_bytes(), meta_path.read_bytes()
    for text in ("clip,text\nen,hello\n", "clip,text\nen,a\nen,b\nhi,c\n"):
        hypotheses.write_text(text)
        assert cli(files, "--model", "offline-test").returncode != 0
        assert (out.read_bytes(), meta_path.read_bytes()) == before
    assert cli(files, "--model", "offline-test", "--provider", "live").returncode != 0
def test_local_adapter_and_wav_preflight(script, tmp_path, monkeypatch):
    from app.voice import local
    adapter = Mock(transcribe=Mock(return_value=("heard", 0.9)))
    adapter.name = "fake-local-model"
    constructor = Mock(return_value=adapter)
    monkeypatch.setattr(local, "WhisperCppSTT", constructor)
    def wav(path, rate, frames):
        with wave.open(str(path), "wb") as output:
            output.setparams((1, 2, rate, 0, "NONE", "not compressed"))
            output.writeframes(frames)
    good, bad = tmp_path / "good.wav", tmp_path / "bad.wav"
    wav(good, 16000, b"\0\0")
    ref = {"clip": "c1", "audio_path": str(good), "language_setting": "hi"}
    hypotheses, extra = script.recognize([ref], "auto")
    assert hypotheses == {"c1": "heard"} and constructor.call_args.args[0].whisper_lang == "hi"
    adapter.transcribe.assert_called_once_with(b"\0\0")
    assert extra["c1"]["model"] == adapter.name and extra["c1"]["audio_s"] == 1/16000
    assert extra["c1"]["decode_s"] >= 0 and extra["c1"]["audio_sha256"] == hashlib.sha256(good.read_bytes()).hexdigest()
    for rate, frames in ((8000, b"\0\0"), (16000, b""), (None, None), (16000, b"\0\0\0\0")):
        wav(bad, rate, frames) if rate else bad.unlink()
        if len(frames or b"") == 4: bad.write_bytes(bad.read_bytes()[:44])
        with pytest.raises((ValueError, OSError)):
            script.recognize([ref, {"clip": "c2", "audio_path": str(bad)}], "en")
        adapter.transcribe.assert_called_once_with(b"\0\0")
