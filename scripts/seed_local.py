"""Seed the LOCAL viva (30 DSA questions, 10 students) into the database the backend uses and save the access codes to .local/codes.txt.
Needs the same env as the server (DATABASE_URL, FACULTY_TOKENS, ACCESS_CODE_PEPPER, AUDIO_SIGNING_SECRET); scripts/run_local.sh sets it.
Run twice on one database: it says so and shows the saved codes (codes cannot be read back from the database)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.api.settings import Settings  # noqa: E402
from app.envfile import load_env  # noqa: E402
from app.local_seed import STUDENTS, VIVA_ID, AlreadySeeded, seed_local  # noqa: E402

CODES = ROOT / ".local" / "codes.txt"


def show(codes):
    print(f"LOCAL viva {VIVA_ID!r}: students and one-time access codes")
    for student_id, name in STUDENTS:
        print(f"  {student_id}  {codes[student_id]}  {name}")


load_env()
settings = Settings.from_env()
if settings.contract_stub or not settings.faculty_tokens:
    sys.exit("set FACULTY_TOKENS (and the secrets) and unset CONTRACT_STUB: this seeds the real backend")
try:
    codes = seed_local(settings)
except AlreadySeeded:
    print(f"{VIVA_ID!r} is already in this database (run scripts/run_local.sh --fresh to start over).")
    if CODES.exists():
        print(f"Saved codes ({CODES.relative_to(ROOT)}):")
        print(CODES.read_text(), end="")
    sys.exit(0)
CODES.parent.mkdir(exist_ok=True)
CODES.write_text("".join(f"{i}  {codes[i]}  {n}\n" for i, n in STUDENTS))
show(codes)
