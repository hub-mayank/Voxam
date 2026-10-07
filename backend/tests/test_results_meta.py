import json
from pathlib import Path
import pytest
from app.results_meta import check_meta_dict, check_results, git_sha, meta_path, write_meta

RESULTS = Path(__file__).resolve().parents[2] / "results"
GOOD = {"provider": "live", "model": "gemini-3.5-flash", "date": "2026-10-07", "git_sha": "89cabb2+dirty", "n": 3}


def test_every_file_in_results_carries_meta():
    # this is the rule from CLAUDE.md evidence rule 2; a new result without a sidecar fails here
    assert check_results(RESULTS) == {}


def test_file_without_sidecar_is_rejected(tmp_path):
    (tmp_path / "latency.csv").write_text("a,b\n1,2\n")
    assert list(check_results(tmp_path).values()) == [["no sidecar latency.csv.meta.json"]]


def test_each_missing_field_is_rejected(tmp_path):
    f = tmp_path / "x.csv"
    f.write_text("a\n")
    for field in GOOD:
        meta = {k: v for k, v in GOOD.items() if k != field}
        meta_path(f).write_text(json.dumps(meta))
        assert check_results(tmp_path)[str(f)] == [f"missing {field}"]


@pytest.mark.parametrize("change", [
    {"provider": "gemini"}, {"model": ""}, {"model": []}, {"date": "07/10/2026"}, {"git_sha": "unknown"},
    {"git_sha": ""}, {"n": 0}, {"n": "3"}, {"n": True}])
def test_bad_values_are_rejected(change):
    assert check_meta_dict({**GOOD, **change})


def test_valid_meta_variants():
    assert check_meta_dict(GOOD) == []
    assert check_meta_dict({**GOOD, "model": ["a", "b"], "provider": "mock", "git_sha": "a" * 40}) == []


def test_bad_json_sidecar_is_rejected(tmp_path):
    f = tmp_path / "x.json"
    f.write_text("{}")
    meta_path(f).write_text("{nope")
    assert check_results(tmp_path)[str(f)] == ["x.json.meta.json is not valid JSON"]


def test_invalid_dir_readmes_and_sidecars_are_exempt(tmp_path):
    (tmp_path / "_invalid").mkdir()
    (tmp_path / "_invalid" / "old.csv").write_text("a\n")
    (tmp_path / "README.txt").write_text("hi")
    assert check_results(tmp_path) == {}


def test_write_meta_records_real_git_sha(tmp_path):
    f = tmp_path / "run.csv"
    f.write_text("a\n")
    out = write_meta(f, "mock", "mock", 5, n_unit="turns")
    meta = json.loads(out.read_text())
    assert meta["git_sha"] == git_sha() and meta["n_unit"] == "turns"
    assert check_results(tmp_path) == {}


def test_write_meta_refuses_bad_input(tmp_path):
    with pytest.raises(ValueError):
        write_meta(tmp_path / "run.csv", "real", "m", 1)
