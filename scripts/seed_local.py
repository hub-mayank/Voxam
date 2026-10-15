"""Seed the LOCAL viva (30 DSA questions, 10 students) into the database the backend uses and save the access codes to .local/codes.txt.
Needs the same env as the server (DATABASE_URL, FACULTY_TOKENS, ACCESS_CODE_PEPPER, AUDIO_SIGNING_SECRET); scripts/run_local.sh sets it.
Run twice on one database: it says so and shows the saved codes (codes cannot be read back from the database)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.api.settings import Settings  # noqa: E402
from app.envfile import load_env  # noqa: E402
from app.local_seed import STUDENTS, VIVA_ID, WEBDEV_ID, WEBDEV_STUDENTS, AlreadySeeded, seed_local, seed_webdev  # noqa: E402

CODES = ROOT / ".local" / "codes.txt"


def show(codes, viva_id=VIVA_ID, students=STUDENTS):
    print(f"LOCAL viva {viva_id!r}: students and one-time access codes")
    for student_id, name in students:
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
else:
    CODES.parent.mkdir(exist_ok=True)
    CODES.write_text("".join(f"{i}  {codes[i]}  {n}\n" for i, n in STUDENTS))
    show(codes)

# the second pilot subject: its bank stays AI-draft until a faculty member approves it in the dashboard
try:
    web = seed_webdev(settings)
except AlreadySeeded:
    pass
else:
    with open(CODES, "a") as f:
        f.write("".join(f"{i}  {web[i]}  {n}\n" for i, n in WEBDEV_STUDENTS))
    show(web, WEBDEV_ID, WEBDEV_STUDENTS)
    print(f"  ({WEBDEV_ID!r} questions are drafts: approve them in the faculty dashboard before a student joins)")
