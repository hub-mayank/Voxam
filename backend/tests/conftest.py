import os
import re
from pathlib import Path

import pytest


def pytest_addoption(parser):
    parser.addoption("--live", action="store_true", default=False, help="run tests marked live (real provider calls)")
    parser.addoption("--postgres", action="store_true", default=False,
                     help="run the suite on PostgreSQL (TEST_DATABASE_URL from the shell or the repo .env; a fresh schema per test)")


def pytest_configure(config):
    config.addinivalue_line("markers", "postgres: runs only with --postgres (needs a PostgreSQL TEST_DATABASE_URL)")
    config.addinivalue_line("markers", "sqlite_only: tests something specific to SQLite; skipped with --postgres")
    if config.getoption("--postgres"):
        import harness
        url = os.environ.get("TEST_DATABASE_URL")
        if not url:
            from app.envfile import read_var  # reads only this one variable; the rest of .env is not imported
            url = read_var("TEST_DATABASE_URL")
        if not url:
            pytest.exit("--postgres needs TEST_DATABASE_URL (shell or .env), e.g. postgresql+psycopg://USER@localhost/ai_viva_test", returncode=2)
        harness.use_postgres(url)


def pytest_collection_modifyitems(config, items):
    pg = config.getoption("--postgres")
    for item in items:
        if "live" in item.keywords and not config.getoption("--live"):
            item.add_marker(pytest.mark.skip(reason="live test; run with --live"))
        if "postgres" in item.keywords and not pg:
            item.add_marker(pytest.mark.skip(reason="needs PostgreSQL; run with --postgres"))
        if "sqlite_only" in item.keywords and pg:
            item.add_marker(pytest.mark.skip(reason="SQLite-specific (pragmas / SQLite error behaviour)"))


@pytest.fixture(autouse=True)
def isolate_state(request, tmp_path, monkeypatch):
    # offline tests never touch the real call counter or the real telemetry log
    monkeypatch.setenv("AI_VIVA_NO_DOTENV", "1")  # tests never read the real .env
    if "live" not in request.keywords:
        monkeypatch.setenv("LLM_BUDGET_FILE", str(tmp_path / "budget.json"))
        monkeypatch.setenv("TELEMETRY_FILE", str(tmp_path / "telemetry.jsonl"))


@pytest.fixture(autouse=True)
def drop_postgres_schemas():
    """With --postgres every test gets its own schema (see harness.db_url_for); drop them afterwards."""
    yield
    import harness
    harness.drop_schemas()
