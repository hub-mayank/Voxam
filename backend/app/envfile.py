"""Load KEY=VALUE pairs from the repo's .env into os.environ, with no dependency.

Rules: a variable that is already set in the environment is never overridden; empty values (placeholders such as `KEY=`) are
treated as unset; comments and blank lines are ignored; values are never printed or logged, only names are reported.
A git worktree has no .env of its own, so the main checkout's file is used when the worktree has none.
AI_VIVA_NO_DOTENV=1 disables loading (the test suite sets it).
`python -m app.envfile [NAME ...]` prints "NAME: set|unset" for each name: a way to check configuration without showing a secret."""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
DEFAULT_NAMES = ("GEMINI_API_KEY", "GROQ_API_KEY", "AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION", "OLLAMA_MODEL", "DATABASE_URL",
                 "TEST_DATABASE_URL", "ACCESS_CODE_PEPPER", "AUDIO_SIGNING_SECRET", "FACULTY_TOKENS")


def find_env_file(root: Path = ROOT):
    own = root / ".env"
    if own.is_file():
        return own
    try:
        common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=root, capture_output=True,
                                text=True, check=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    main = Path(common).parent / ".env"
    return main if main.is_file() else None


def parse(text: str) -> dict:
    """-> {name: value} for the non-empty assignments in `text`."""
    out = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        name, sep, rest = line.partition("=")
        name = name.strip()
        if not sep or not KEY.match(name):
            continue
        rest = rest.strip()
        if rest[:1] in ("'", '"'):
            end = rest.find(rest[0], 1)
            value = rest[1:end] if end != -1 else rest[1:]
        else:
            value = re.split(r"\s+#", rest, maxsplit=1)[0].strip()
        if value:
            out[name] = value
    return out


def read_var(name: str, path=None):
    """One variable's value straight from the file, without touching os.environ (None if absent). For callers that must not import the
    whole file into the environment, e.g. the test suite reading only TEST_DATABASE_URL."""
    path = Path(path) if path else find_env_file()
    if path is None or not path.is_file():
        return None
    return parse(path.read_text()).get(name)


def load_env(path=None, environ=None, only=None) -> list:
    """Copy variables from the file into `environ` (default os.environ) unless already set. -> sorted names that were set."""
    environ = os.environ if environ is None else environ
    if environ.get("AI_VIVA_NO_DOTENV"):  # tests and subprocesses that must stay hermetic
        return []
    path = Path(path) if path else find_env_file()
    if path is None or not path.is_file():
        return []
    loaded = []
    for name, value in parse(path.read_text()).items():
        if only is not None and name not in only:
            continue
        if environ.get(name):
            continue
        environ[name] = value
        loaded.append(name)
    return sorted(loaded)


if __name__ == "__main__":
    load_env()
    for name in (sys.argv[1:] or DEFAULT_NAMES):
        print(f"{name}: {'set' if os.environ.get(name) else 'unset'}")
