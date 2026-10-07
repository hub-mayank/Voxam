"""Parse and validate the faculty CSV/JSON uploads. All or nothing: any bad row raises invalid_upload with every problem."""
import csv
import io
import json

from pydantic import ValidationError

from ..api.errors import ApiError, ErrorCode
from ..api.schemas.faculty import QuestionIn

MAX_BYTES = 1_000_000
MAX_ERRORS = 50
BANK_COLUMNS = ["id", "topic", "type", "difficulty", "text", "key_points"]


def _fail(rows):
    raise ApiError(ErrorCode.invalid_upload, f"{len(rows)} problem(s) in the upload; nothing was stored.",
                   {"rows": rows[:MAX_ERRORS]})


def _text(data: bytes) -> str:
    if len(data) > MAX_BYTES:
        _fail([{"row": 0, "field": "file", "message": f"file is larger than {MAX_BYTES} bytes"}])
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        _fail([{"row": 0, "field": "file", "message": "file is not valid UTF-8"}])


def _kind(filename: str, allowed) -> str:
    ext = (filename or "").rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""
    if ext not in allowed:
        _fail([{"row": 0, "field": "file", "message": f"file must be {' or '.join('.' + a for a in allowed)}, got {filename!r}"}])
    return ext


def _csv_rows(text: str, required, optional=()):
    reader = csv.DictReader(io.StringIO(text))
    header = [h.strip() for h in (reader.fieldnames or [])]
    problems = [{"row": 0, "field": c, "message": "missing column"} for c in required if c not in header]
    problems += [{"row": 0, "field": c, "message": "unknown column"} for c in header if c not in (*required, *optional)]
    if problems:
        _fail(problems)
    return [{(k or "").strip(): (v or "").strip() for k, v in row.items() if k} for row in reader]


def parse_bank(filename: str, data: bytes) -> list:
    """-> list[QuestionIn]. CSV: id,topic,type,difficulty,text,key_points (key points separated by |). JSON: array of objects."""
    text, kind = _text(data), _kind(filename, ("csv", "json"))
    if kind == "csv":
        rows = _csv_rows(text, BANK_COLUMNS)
        for r in rows:
            r["key_points"] = [p.strip() for p in r["key_points"].split("|") if p.strip()]
    else:
        try:
            rows = json.loads(text)
        except ValueError as e:
            _fail([{"row": 0, "field": "file", "message": f"not valid JSON: {e}"}])
        if not isinstance(rows, list):
            _fail([{"row": 0, "field": "file", "message": "JSON must be an array of question objects"}])
    problems, questions, seen = [], [], {}
    for n, row in enumerate(rows, start=1):
        try:
            q = QuestionIn.model_validate(row)
        except ValidationError as e:
            problems += [{"row": n, "field": ".".join(str(p) for p in err["loc"]) or "row", "message": err["msg"]} for err in e.errors()]
            continue
        if q.id in seen:
            problems.append({"row": n, "field": "id", "message": f"duplicate id {q.id!r} (first used in row {seen[q.id]})"})
        seen.setdefault(q.id, n)
        questions.append(q)
    if not rows:
        problems.append({"row": 0, "field": "file", "message": "no questions in the file"})
    if problems:
        _fail(problems)
    return questions


def parse_roster(filename: str, data: bytes) -> list:
    """-> list of (student_id, name or None). CSV header: student_id[,name]."""
    text = _text(data)
    _kind(filename, ("csv",))
    rows = _csv_rows(text, ["student_id"], ["name"])
    problems, out, seen = [], [], {}
    for n, row in enumerate(rows, start=1):
        sid, name = row.get("student_id", ""), row.get("name", "") or None
        if not sid:
            problems.append({"row": n, "field": "student_id", "message": "empty"})
        elif len(sid) > 40:
            problems.append({"row": n, "field": "student_id", "message": "longer than 40 characters"})
        elif sid in seen:
            problems.append({"row": n, "field": "student_id", "message": f"duplicate of row {seen[sid]}"})
        if name and len(name) > 120:
            problems.append({"row": n, "field": "name", "message": "longer than 120 characters"})
        seen.setdefault(sid, n)
        out.append((sid, name))
    if not rows:
        problems.append({"row": 0, "field": "file", "message": "no students in the file"})
    if problems:
        _fail(problems)
    return out
