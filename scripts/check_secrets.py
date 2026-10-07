"""Scan for API-key shapes. Exit 1 on a hit. Never prints the secret, only file:line and the kind.
  python scripts/check_secrets.py            scan all tracked + untracked (not ignored) files
  python scripts/check_secrets.py --staged   scan staged content (used by the pre-commit hook)
  python scripts/check_secrets.py a.py b.txt scan the given files"""
import re
import subprocess
import sys
from pathlib import Path

patterns = {
    "google api key": r"AIza[0-9A-Za-z_\-]{35}",
    "anthropic key": r"sk-ant-[0-9A-Za-z_\-]{20,}",
    "openai-style key": r"sk-(?:proj-)?[0-9A-Za-z_\-]{32,}",
    "github token": r"gh[pousr]_[0-9A-Za-z]{36,}",
    "github fine-grained token": r"github_pat_[0-9A-Za-z_]{40,}",
    "aws access key": r"AKIA[0-9A-Z]{16}",
    "slack token": r"xox[abprs]-[0-9A-Za-z\-]{10,}",
    "private key": r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----",
}
compiled = {name: re.compile(p) for name, p in patterns.items()}


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, check=True).stdout


def scan(name, data):
    hits = []
    if b"\0" in data[:8000]:
        return hits
    for n, line in enumerate(data.decode("utf-8", "ignore").splitlines(), 1):
        for kind, rx in compiled.items():
            if rx.search(line):
                hits.append(f"{name}:{n}: looks like a {kind}")
    return hits


def main(argv):
    hits = []
    if argv == ["--staged"]:
        for name in git("diff", "--cached", "--name-only", "--diff-filter=ACM", "-z").decode().split("\0"):
            if name:
                hits += scan(name, git("show", f":{name}"))
    else:
        if argv:
            files = argv
        else:
            files = git("ls-files", "--cached", "--others", "--exclude-standard", "-z").decode().split("\0")
        for name in files:
            path = Path(name)
            if name and path.is_file():
                hits += scan(name, path.read_bytes())
    for hit in hits:
        print(hit)
    if hits:
        print("secret scan failed; remove the key and revoke it", file=sys.stderr)
        return 1
    print("secret scan clean")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
