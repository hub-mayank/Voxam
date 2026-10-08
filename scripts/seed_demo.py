"""Seed a labelled DEMO viva into the database the backend uses, so the frontend can run against the real backend.
Run from backend/ with the same env as the server (DATABASE_URL, ACCESS_CODE_PEPPER, AUDIO_SIGNING_SECRET, FACULTY_TOKENS):
    cd backend && python ../scripts/seed_demo.py
Everything it creates is fake and labelled DEMO. It refuses to run twice on one database."""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.api.settings import Settings  # noqa: E402
from app.envfile import load_env  # noqa: E402
from app.demo_seed import STUDENTS, VIVA_ID, seed  # noqa: E402

load_env()
settings = Settings.from_env()
if settings.contract_stub or not settings.faculty_tokens:
    sys.exit("set FACULTY_TOKENS (and the secrets), and unset CONTRACT_STUB: this seeds the real backend")
codes = seed(settings, lambda: datetime.now(timezone.utc))
print(f"seeded DEMO viva {VIVA_ID!r} (all data is fake). Student access codes:")
for student_id, name in STUDENTS:
    print(f"  {student_id}  {codes[student_id]}  {name}")
