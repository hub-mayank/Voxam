"""Install the git pre-commit hook that runs the secret scan on staged files.
Run once per clone: python scripts/install_hooks.py"""
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
hooks = subprocess.run(["git", "rev-parse", "--git-path", "hooks"], cwd=root,
                       capture_output=True, text=True, check=True).stdout.strip()
hooks = Path(hooks) if Path(hooks).is_absolute() else root / hooks
hook = hooks / "pre-commit"
hook.write_text(f'#!/bin/sh\nexec python3 "{root}/scripts/check_secrets.py" --staged\n')
hook.chmod(0o755)
print(f"installed {hook}")
