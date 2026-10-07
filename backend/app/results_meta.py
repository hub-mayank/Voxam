"""Every file in results/ has a sidecar <file>.meta.json with provider, model, date, git_sha, n
(CLAUDE.md evidence rule 2). provider is mock | stub | live. n is the sample size behind the numbers."""
import datetime
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQUIRED = ("provider", "model", "date", "git_sha", "n")
PROVIDERS = ("mock", "stub", "live")
SHA_FORMAT = re.compile(r"^[0-9a-f]{7,40}(\+dirty)?$")
SKIP_DIRS = ("_invalid",)


def meta_path(path) -> Path:
    path = Path(path)
    return path.with_name(path.name + ".meta.json")


def git_sha() -> str:
    """HEAD sha; +dirty when tracked files have uncommitted changes."""
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT,
                           capture_output=True, text=True, check=True).stdout.strip()
    return sha + ("+dirty" if dirty else "")


def write_meta(path, provider: str, model, n: int, **extra) -> Path:
    meta = {"provider": provider, "model": model, "date": datetime.date.today().isoformat(),
            "git_sha": git_sha(), "n": n, **extra}
    problems = check_meta_dict(meta)
    if problems:
        raise ValueError(f"bad results meta: {problems}")
    out = meta_path(path)
    out.write_text(json.dumps(meta, indent=2) + "\n")
    return out


def check_meta_dict(meta) -> list[str]:
    if not isinstance(meta, dict):
        return ["meta must be a JSON object"]
    problems = [f"missing {k}" for k in REQUIRED if k not in meta]
    if problems:
        return problems
    if meta["provider"] not in PROVIDERS:
        problems.append(f"provider must be one of {PROVIDERS}")
    model = meta["model"]
    if not ((isinstance(model, str) and model) or (isinstance(model, list) and model and all(isinstance(m, str) and m for m in model))):
        problems.append("model must be a non-empty string or list of strings")
    try:
        datetime.date.fromisoformat(str(meta["date"])[:10])
    except ValueError:
        problems.append("date must be ISO (YYYY-MM-DD)")
    if not (isinstance(meta["git_sha"], str) and SHA_FORMAT.match(meta["git_sha"])):
        problems.append("git_sha must be a hex sha, optionally +dirty")
    if type(meta["n"]) is not int or meta["n"] < 1:
        problems.append("n must be an int >= 1")
    return problems


def check_meta(path) -> list[str]:
    mp = meta_path(path)
    if not mp.exists():
        return [f"no sidecar {mp.name}"]
    try:
        return check_meta_dict(json.loads(mp.read_text()))
    except json.JSONDecodeError:
        return [f"{mp.name} is not valid JSON"]


def result_files(root) -> list[Path]:
    """Data files that need a sidecar: everything under root except _invalid/, READMEs, sidecars, dotfiles."""
    root = Path(root)
    return sorted(p for p in root.rglob("*")
                  if p.is_file() and not p.name.startswith(".") and not p.name.startswith("README")
                  and not p.name.endswith(".meta.json")
                  and not any(part in SKIP_DIRS for part in p.relative_to(root).parts))


def check_results(root) -> dict[str, list[str]]:
    """{file: problems} for every results file that is missing or has a bad sidecar."""
    return {str(p): probs for p in result_files(root) if (probs := check_meta(p))}
