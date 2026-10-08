import subprocess
import sys
from pathlib import Path

from app import envfile

SAMPLE = """# comment line
GEMINI_API_KEY=abc123
export GROQ_API_KEY = "quoted value # not a comment"
OLLAMA_MODEL=llama3.2:3b   # trailing comment
EMPTY=
SPACED = 'single quoted'
not a valid line
1BAD=nope
URL=postgresql+psycopg://u@localhost/db?x=1#frag
"""


def test_parse_handles_comments_quotes_export_and_empty_values():
    got = envfile.parse(SAMPLE)
    assert got == {"GEMINI_API_KEY": "abc123", "GROQ_API_KEY": "quoted value # not a comment", "OLLAMA_MODEL": "llama3.2:3b",
                   "SPACED": "single quoted", "URL": "postgresql+psycopg://u@localhost/db?x=1#frag"}


def test_load_sets_only_what_is_missing_and_never_overrides(tmp_path):
    f = tmp_path / ".env"
    f.write_text(SAMPLE)
    environ = {"GEMINI_API_KEY": "already-set-in-the-shell"}
    loaded = envfile.load_env(f, environ)
    assert environ["GEMINI_API_KEY"] == "already-set-in-the-shell"
    assert "GEMINI_API_KEY" not in loaded and set(loaded) == {"GROQ_API_KEY", "OLLAMA_MODEL", "SPACED", "URL"}
    assert environ["OLLAMA_MODEL"] == "llama3.2:3b"
    assert envfile.load_env(f, environ) == [], "a second load changes nothing"


def test_an_empty_shell_variable_counts_as_unset_so_the_file_fills_it(tmp_path):
    f = tmp_path / ".env"
    f.write_text("A=from-file\n")
    environ = {"A": ""}
    assert envfile.load_env(f, environ) == ["A"] and environ["A"] == "from-file"


def test_only_restricts_which_names_are_loaded(tmp_path):
    f = tmp_path / ".env"
    f.write_text("A=1\nB=2\n")
    environ = {}
    assert envfile.load_env(f, environ, only={"B"}) == ["B"] and environ == {"B": "2"}


def test_read_var_does_not_touch_the_environment(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("TEST_DATABASE_URL=postgresql://x/y\n")
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    assert envfile.read_var("TEST_DATABASE_URL", f) == "postgresql://x/y" and envfile.read_var("NOPE", f) is None
    import os
    assert "TEST_DATABASE_URL" not in os.environ


def test_missing_file_is_fine(tmp_path):
    assert envfile.load_env(tmp_path / "nope.env", {}) == []
    assert envfile.read_var("X", tmp_path / "nope.env") is None


def test_values_are_never_printed(tmp_path, capfd):
    f = tmp_path / ".env"
    f.write_text("GEMINI_API_KEY=super-secret-value-123\n")
    code = ("import sys; sys.path.insert(0, %r); from app import envfile; "
            "envfile.load_env(%r); import runpy; sys.argv=['x','GEMINI_API_KEY','NOT_THERE']; runpy.run_module('app.envfile', run_name='__main__')"
            % (str(Path(envfile.__file__).parents[1]), str(f)))
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})
    assert "GEMINI_API_KEY: unset" in out.stdout or "GEMINI_API_KEY: set" in out.stdout
    assert "NOT_THERE: unset" in out.stdout and "super-secret-value-123" not in out.stdout + out.stderr


def test_a_worktree_falls_back_to_the_main_checkouts_env(tmp_path):
    main = tmp_path / "main"
    main.mkdir()
    run = lambda *a, cwd=main: subprocess.run(a, cwd=cwd, check=True, capture_output=True, text=True)  # noqa: E731
    run("git", "init", "-q", "-b", "main")
    run("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x")
    (main / ".env").write_text("K=v\n")
    wt = tmp_path / "wt"
    run("git", "worktree", "add", "-q", str(wt), "-b", "other")
    assert envfile.find_env_file(wt) == (main / ".env").resolve() or envfile.find_env_file(wt).resolve() == (main / ".env").resolve()
    (wt / ".env").write_text("K=own\n")
    assert envfile.find_env_file(wt) == wt / ".env", "a worktree's own .env wins"
