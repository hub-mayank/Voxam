import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(path):
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "check_bank.py"), str(path)], capture_output=True, text=True)


def test_a_good_file_passes_and_a_small_bank_gets_notes():
    out = run(ROOT / "docs" / "qa" / "question_bank_template.csv")
    assert out.returncode == 0 and "ok: 3 questions" in out.stdout and "small bank" in out.stdout


def test_the_shipped_banks_pass_the_same_check_the_upload_uses():
    for name in ("question_bank.dsa.csv", "question_bank.webdev.csv", "question_bank.webd-team.csv", "question_bank.dsa-team.csv"):
        out = run(ROOT / "config" / name)
        assert out.returncode == 0 and "ok: 30 questions" in out.stdout, name


def test_a_file_the_upload_would_refuse_exits_with_the_row(tmp_path):
    bad = tmp_path / "bank.csv"
    bad.write_text("id,topic,type,difficulty,text,key_points,source\nq1,t,concept,9,Why?,a|b|c,bank\n")
    out = run(bad)
    assert out.returncode == 1 and "REFUSED" in out.stdout and "row" in out.stdout
