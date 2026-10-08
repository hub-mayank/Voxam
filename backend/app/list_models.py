"""Lists models your GEMINI_API_KEY can call for generateContent. Pick from THIS list."""
import os
import httpx
from .envfile import load_env

load_env()  # GEMINI_API_KEY from the shell or the repo .env (never printed)

key = os.environ.get("GEMINI_API_KEY")
if not key:
    raise SystemExit("export GEMINI_API_KEY first (never commit it)")
r = httpx.get("https://generativelanguage.googleapis.com/v1beta/models", headers={"x-goog-api-key": key},
              params={"pageSize": 200}, timeout=15)
r.raise_for_status()
for m in r.json().get("models", []):
    if "generateContent" in m.get("supportedGenerationMethods", []):
        print(m["name"].removeprefix("models/"), "|", m.get("displayName", ""))
