"""Check a question bank file before uploading it: the same parser the faculty upload uses, then a few things that make a viva better.
Usage: python scripts/check_bank.py docs/qa/question_bank_template.csv [more files]
Exit code 1 if the upload would be refused; notes (not errors) never change it."""
import collections
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.api.errors import ApiError  # noqa: E402
from app.services.uploads import parse_bank  # noqa: E402

MIN_CONCEPT, MIN_APPLIED = 7, 3  # below this the interview falls back to generic questions (config.py)
ASKING = re.compile(r"\b(what|how|why|when|where|which)\b", re.I)
LONG_WORDS = 30  # a question this long is hard to hold in the head when it is spoken


def notes_for(questions) -> list[str]:
    notes = []
    concept = [q for q in questions if q.type.value == "concept"]
    applied = [q for q in questions if q.type.value == "applied"]
    if len(concept) < MIN_CONCEPT or len(applied) < MIN_APPLIED:
        notes.append(f"small bank: {len(concept)} concept and {len(applied)} applied; aim for at least {MIN_CONCEPT} and {MIN_APPLIED}")
    easy = [q for q in concept if q.difficulty <= 2]
    if len(easy) < 4:
        notes.append(f"only {len(easy)} concept questions of difficulty 1-2; the fundamentals phase wants about 4 so no one starts on a hard one")
    if not [q for q in concept if q.difficulty >= 3]:
        notes.append("no concept question of difficulty 3 or more; the depth phase has nothing hard to ask")
    for q in questions:
        words = len(q.text.split())
        if words > LONG_WORDS:
            notes.append(f"{q.id}: {words} words; shorter is easier to follow by ear")
        if len(q.key_points) < 3:
            notes.append(f"{q.id}: {len(q.key_points)} key point(s); the scorer and the markers work from 3 to 5")
        if q.text.count("?") > 1 or len(ASKING.findall(q.text)) >= 3:
            notes.append(f"{q.id}: looks like several questions in one; one clear question scores more fairly")
    texts = collections.Counter(q.text.strip().lower() for q in questions)
    notes += [f"duplicate question text: {t[:50]}" for t, n in texts.items() if n > 1]
    if any(q.source.value == "ai-draft" for q in questions):
        notes.append("some questions are ai-draft: someone must approve them in the faculty page before a viva can use them")
    return notes


def check(path: Path) -> bool:
    print(f"== {path}")
    try:
        questions = parse_bank(path.name, path.read_bytes())
    except ApiError as e:
        print(f"REFUSED by the upload: {e.message}")
        for row in (e.details or {}).get("rows", [])[:10]:
            print(f"  row {row.get('row')}: {row.get('message')}")
        return False
    by_type = collections.Counter(q.type.value for q in questions)
    print(f"ok: {len(questions)} questions ({by_type['concept']} concept, {by_type['applied']} applied), "
          f"{len({q.topic for q in questions})} topics, difficulty {dict(sorted(collections.Counter(q.difficulty for q in questions).items()))}")
    for note in notes_for(questions):
        print(f"  note: {note}")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    results = [check(Path(p)) for p in sys.argv[1:]]
    sys.exit(0 if all(results) else 1)
