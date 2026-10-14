"""Offline report-generator verification; run with Python's stdlib unittest."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_report.py"


class BuildReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("build_report", SCRIPT)
        cls.report = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.report)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.results = self.base / "results"
        self.results.mkdir()
        self.out = self.base / "reports/test.md"

    def result(self, name="run.csv", text="server_latency_ms,wer\n10,0.1\n30,0.3\n,\n", **extra):
        path = self.results / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        meta = {"provider": "live", "model": "measured-model", "date": "2026-10-14",
                "git_sha": "123abcd", "n": 17, "n_unit": "requests", **extra}
        Path(str(path) + ".meta.json").write_text(json.dumps(meta), encoding="utf-8")
        return path

    def cli(self, out=None):
        return subprocess.run([sys.executable, str(SCRIPT), "--results-dir", str(self.results),
                               "--out", str(out or self.out)], capture_output=True, text=True)

    def test_provenance_relative_encoded_links_and_declared_sample_size(self):
        self.result("voice clips/a] #α.csv", model=["STT", "mock-llm"], audio="synthetic")
        self.result("mock.csv", provider="mock")
        self.result("stub.csv", provider="stub")
        self.result("grouped.csv", "model,server_latency_ms\nA,10\nA,30\nB,900\n")
        self.result("scores.csv", "transcript,run,total\ns,1,1\ns,2,3\n", provider="mock")
        self.result("wer.csv", "substitutions,deletions,insertions,ref_words\n3,0,0,10\n0,0,0,90\n")
        report = self.report.build_report(self.results, self.out)
        self.assertFalse(self.out.exists(), "build_report must not write output")
        for value in ("../results/voice%20clips/a%5D%20%23%CE%B1.csv", "csv.meta.json", "sample variance=2",
                      "requests", "17", "mock", "stub", "live", "synthetic", "mock-llm", "n=1 p50=900 p95=900", "word-weighted strict WER=0.03"):
            self.assertIn(value, report)
        self.assertNotIn(str(self.base), report)
        self.assertRegex(report, r"server_latency_ms: n=2 p50=20(?:\.0+)? p95=30(?:\.0+)?")
        self.assertIn("reported n", report.lower())
        self.assertIn("gaps", report.lower())
        self.assertNotIn("synthetic input", self.report.qualifiers({"provider": "live", "model": "tts", "git_sha": "123abcd", "n_unit": "synthesis runs"}, Path("tts.csv")))
        self.assertEqual(self.cli().returncode, 0)
        self.assertTrue(self.out.read_text().startswith("#"))

    def test_discovery_ignores_invalid_directory_readmes_and_dotfiles(self):
        self.result()
        for name in ("_invalid/bad.csv", "README.md", ".private.csv"):
            path = self.results / name
            path.parent.mkdir(exist_ok=True)
            path.write_text("not results")
        self.assertEqual(self.cli().returncode, 0)

    def test_invalid_metadata_and_csv_preserve_existing_report(self):
        bad_csv = ("", "a,b\n", "a,b\n1\n", "a,b\n1,2,3\n", 'a,b\n1,"unterminated',
                   "a,a\n1,2\n", "server_latency_ms\nnan\n", "server_latency_ms\noops\n")
        for text in bad_csv:
            with self.subTest(csv=text):
                self.result(text=text)
                self.assert_rejected_without_write()
        for bad_meta in (None, "{broken", json.dumps({}), json.dumps({"provider": "real"})):
            with self.subTest(meta=bad_meta):
                path = self.result()
                sidecar = Path(str(path) + ".meta.json")
                sidecar.unlink() if bad_meta is None else sidecar.write_text(bad_meta)
                self.assert_rejected_without_write()

    def assert_rejected_without_write(self):
        self.out.parent.mkdir(exist_ok=True)
        self.out.write_text("existing report")
        run = self.cli()
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual(self.out.read_text(), "existing report")
        self.assertTrue(run.stderr.strip(), "failure must explain the problem")

    def test_no_results_and_report_inside_results_are_rejected(self):
        self.assertNotEqual(self.cli().returncode, 0)
        self.result()
        target = self.results / "new/report.md"
        self.assertNotEqual(self.cli(target).returncode, 0)
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
