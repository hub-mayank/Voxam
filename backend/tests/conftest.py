import pytest


def pytest_addoption(parser):
    parser.addoption("--live", action="store_true", default=False, help="run tests marked live (real provider calls)")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--live"):
        return
    skip = pytest.mark.skip(reason="live test; run with --live")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def isolate_state(request, tmp_path, monkeypatch):
    # offline tests never touch the real call counter or the real telemetry log
    if "live" not in request.keywords:
        monkeypatch.setenv("LLM_BUDGET_FILE", str(tmp_path / "budget.json"))
        monkeypatch.setenv("TELEMETRY_FILE", str(tmp_path / "telemetry.jsonl"))
