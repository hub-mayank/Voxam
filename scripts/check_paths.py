"""Did this branch touch only its owner's files? (docs/ownership.json, docs/TEAM_PLAN.md section 3)
Usage: python scripts/check_paths.py parth|bhavesh|tejas [--base origin/main]
Exit 1 and a list when a changed file is outside the owner's paths. A guard against AI tools editing files nobody asked them to."""
import argparse
import fnmatch
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "docs" / "ownership.json"


def violations(owner: str, files: list, rules: dict) -> list:
    """Files in `files` that `owner` may not change."""
    if owner not in rules or owner.startswith("_"):
        raise KeyError(f"unknown owner {owner!r}; known: {sorted(k for k in rules if not k.startswith('_') and k != 'common')}")
    mine, common = rules[owner], rules.get("common", [])

    def matches(path, patterns):
        return any(fnmatch.fnmatch(path, p) for p in patterns)
    return [f for f in files if not (matches(f, common) or (matches(f, mine["allow"]) and not matches(f, mine.get("deny", []))))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("owner")
    ap.add_argument("--base", default="origin/main")
    a = ap.parse_args()
    rules = json.loads(RULES.read_text())
    files = subprocess.run(["git", "diff", "--name-only", f"{a.base}...HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    bad = violations(a.owner, files, rules)
    if bad:
        print(f"{len(bad)} file(s) changed outside {a.owner}'s paths (docs/TEAM_PLAN.md section 3):")
        print("\n".join(f"  {f}" for f in bad))
        print("Revert them (git checkout origin/main -- <file>) or ask in the PR why they are needed.")
        sys.exit(1)
    print(f"ok: {len(files)} changed file(s), all inside {a.owner}'s paths")


if __name__ == "__main__":
    main()
