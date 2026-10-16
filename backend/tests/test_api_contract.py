import inspect
import json
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.api import errors
from app.api.errors import ERROR_EXAMPLES, HTTP_STATUS, ErrorCode
from app.api.main import create_app, openapi_json
from app.api.schemas import common, faculty, student
from app.api.settings import Settings, parse_faculty_tokens

ROOT = Path(__file__).resolve().parents[2]
FACULTY = {"tok-rao-0123456789": "dr-rao", "tok-iyer-0123456789": "dr-iyer"}
RAO = {"Authorization": "Bearer tok-rao-0123456789"}
IYER = {"Authorization": "Bearer tok-iyer-0123456789"}
STUDENT = {"Authorization": "Bearer st_Zk3vQ0m1pWw8s2dYb7nX4cL9tRfJ6aHeUoGiVyMq5NA"}
SID = "7c9e6679-7425-40de-944b-e07fc1f90ae7"
SAMPLE = {"viva_id": "dsa-midterm-2026", "viva": "dsa-midterm-2026", "sid": SID, "student_id": "S2024002"}


def make_app(**kw):
    return create_app(Settings(dict(FACULTY), **{"contract_stub": True, **kw}))


@pytest.fixture()
def client():
    return TestClient(make_app(), raise_server_exceptions=False)


def all_models():
    found = []
    for module in (faculty, student, common, errors):
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if issubclass(cls, BaseModel) and cls.__module__ == module.__name__ and cls not in (common.ApiRequest, common.ApiResponse):
                found.append(cls)
    return found


def operations(app):
    spec = app.openapi()
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            yield path, method, op


def url_for(path):
    return re.sub(r"\{(\w+)\}", lambda m: SAMPLE.get(m.group(1), "x"), path)


def walk(value):
    if isinstance(value, dict):
        for v in value.values():
            yield from walk(v)
    elif isinstance(value, list):
        for v in value:
            yield from walk(v)
    else:
        yield value


# ---------- schemas ----------

@pytest.mark.parametrize("model", all_models(), ids=lambda m: m.__name__)
def test_every_model_has_a_description_and_a_valid_example(model):
    schema = model.model_json_schema()
    assert (model.__doc__ or "").strip(), "needs a docstring (becomes the description)"
    assert schema.get("examples"), "needs json_schema_extra examples"
    for example in schema["examples"]:
        parsed = model.model_validate(example)
        assert parsed.model_dump(mode="json") == json.loads(json.dumps(example)), "example must round-trip unchanged"


def test_all_example_timestamps_are_utc_z():
    stamp = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
    seen = 0
    for model in all_models():
        for example in model.model_json_schema().get("examples", []):
            for v in walk(example):
                if isinstance(v, str) and stamp.match(v):
                    seen += 1
                    assert v.endswith("Z"), f"{model.__name__}: {v}"
    assert seen > 10


def test_naive_datetimes_are_rejected_and_offsets_become_z():
    with pytest.raises(ValueError):
        student.ConsentResponse(status="consented", consent_at="2026-10-12T05:29:40")
    out = student.ConsentResponse(status="consented", consent_at="2026-10-12T11:00:00+05:30").model_dump(mode="json")
    assert out["consent_at"] == "2026-10-12T05:30:00Z"


def test_durations_are_milliseconds_not_seconds():
    for model in all_models():
        for name in model.model_fields:
            assert not re.search(r"(_s|_sec|_secs|_seconds)$", name), f"{model.__name__}.{name}: use *_ms"


def test_requests_reject_unknown_fields(client):
    body = {"new_total": 50, "reason": "because", "reviewer": "someone-else"}
    r = client.post(f"/faculty/sessions/{SID}/override", json=body, headers=RAO)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_session_detail_example_is_internally_consistent():
    d = common.example_of(faculty.SessionDetail)
    student_turns = {t.idx for t in d.turns if t.role == "student"}
    assert [t.idx for t in d.turns] == list(range(len(d.turns)))
    s = d.scoring
    assert all(set(x.evidence) <= student_turns for x in s.dimensions)
    assert all(set(x.evidence) <= student_turns for x in s.feedback) and 3 <= len(s.feedback) <= 5
    assert sum(x.weight for x in s.dimensions) == 100
    assert round(sum(x.weight * x.score / 5 for x in s.dimensions), 2) == s.median_total
    for run in s.runs:
        weights = {x.key: x.weight for x in s.dimensions}
        assert round(sum(weights[k] * v / 5 for k, v in run.dimension_scores.items()), 2) == run.total
    assert s.total_spread == max(r.total for r in s.runs) - min(r.total for r in s.runs)
    assert d.effective_total == d.overrides[-1].new_total and d.effective_source == "override"
    assert d.overrides[-1].old_total == s.median_total


# ---------- errors ----------

def test_every_error_code_has_a_status_and_an_example():
    assert set(HTTP_STATUS) == set(ErrorCode) == set(ERROR_EXAMPLES)
    spec = make_app().openapi()
    assert spec["components"]["schemas"]["ErrorCode"]["enum"] == [c.value for c in ErrorCode]
    assert "HTTPValidationError" not in json.dumps(spec)


def assert_error_body(r, code):
    body = r.json()
    assert set(body) == {"error"} and set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == code and isinstance(body["error"]["details"], dict)


def test_all_failures_use_the_uniform_error_body(client):
    assert_error_body(client.get("/nope"), "not_found")
    assert_error_body(client.delete("/health"), "method_not_allowed")
    assert_error_body(client.post(f"/student/sessions/{SID}/answer", json={"text": "x", "client_seq": 0}, headers=STUDENT),
                      "validation_error")
    assert_error_body(client.get("/faculty/vivas"), "unauthorized")
    assert_error_body(client.get("/faculty/vivas", headers=STUDENT), "forbidden")
    r = client.get("/faculty/sessions/not-a-uuid", headers=RAO)
    assert r.status_code == 422 and r.json()["error"]["details"]["fields"]


@pytest.mark.parametrize("code", [c.value for c in ErrorCode])
def test_mock_error_header_returns_each_code(client, code):
    r = client.get("/faculty/vivas", headers={**RAO, "X-Mock-Error": code})
    assert r.status_code == HTTP_STATUS[ErrorCode(code)]
    assert_error_body(r, code)


def test_deadline_passed_carries_the_closing_text(client):
    r = client.post(f"/student/sessions/{SID}/answer", json={"text": "late", "client_seq": 5},
                    headers={**STUDENT, "X-Mock-Error": "deadline_passed"})
    assert r.status_code == 409
    assert r.json()["error"]["details"]["closing_text"] and r.json()["error"]["details"]["deadline_at"].endswith("Z")


def test_unknown_mock_error_is_rejected(client):
    assert client.get("/faculty/vivas", headers={**RAO, "X-Mock-Error": "boom"}).status_code == 422


# ---------- auth ----------

def test_auth_matrix_over_every_route():
    app = make_app()
    client = TestClient(app, raise_server_exceptions=False)
    checked = {"faculty": 0, "student": 0, "public": 0}
    for path, method, op in operations(app):
        schemes = {name for req in op.get("security", []) for name in req}
        url = url_for(path)
        send = lambda headers: client.request(method.upper(), url, headers=headers)  # noqa: E731
        if "FacultyToken" in schemes:
            checked["faculty"] += 1
            assert send({}).status_code == 401, path
            assert send({"Authorization": "Bearer wrong"}).status_code == 401, path
            assert send({"Authorization": "Basic abc"}).status_code == 401, path
            assert send(STUDENT).status_code == 403, path
            assert send(RAO).status_code not in (401, 403), path
        elif "StudentToken" in schemes:
            checked["student"] += 1
            assert send({}).status_code == 401, path
            assert send({"Authorization": "Bearer wrong"}).status_code == 401, path
            assert send(RAO).status_code == 403, path
            assert send(STUDENT).status_code not in (401, 403), path
        else:
            checked["public"] += 1
            assert path in ("/health", "/student/join"), f"{path} has no auth"
    assert checked == {"faculty": 19, "student": 5, "public": 2}


def test_no_faculty_tokens_configured_means_everything_is_401():
    client = TestClient(create_app(Settings({}, contract_stub=True)), raise_server_exceptions=False)
    assert client.get("/faculty/vivas", headers=RAO).status_code == 401


def test_reviewer_comes_from_the_token(client):
    body = {"new_total": 80, "reason": "reviewed the audio"}
    assert client.post(f"/faculty/sessions/{SID}/override", json=body, headers=RAO).json()["override"]["reviewer"] == "dr-rao"
    assert client.post(f"/faculty/sessions/{SID}/override", json=body, headers=IYER).json()["override"]["reviewer"] == "dr-iyer"


def test_faculty_token_parsing():
    assert parse_faculty_tokens("a:one, b:two:with:colons") == {"one": "a", "two:with:colons": "b"}
    assert parse_faculty_tokens("") == {}
    for bad in ("nocolon", ":token", "name:", "a:x,b:x", "a:st_abc"):
        with pytest.raises(ValueError):
            parse_faculty_tokens(bad)


def test_settings_from_env():
    s = Settings.from_env({"FACULTY_TOKENS": "a:t1", "CORS_ORIGINS": "http://x.test, http://y.test", "REQUIRE_ACCESS_CODE": "false"})
    assert s.faculty_tokens == {"t1": "a"} and s.cors_origins == ("http://x.test", "http://y.test") and not s.require_access_code
    assert Settings.from_env({}).require_access_code is True


def test_cors_origins_come_from_settings():
    on = TestClient(make_app(cors_origins=("http://localhost:5173",)))
    r = on.options("/faculty/vivas", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
    off = TestClient(make_app()).get("/health", headers={"Origin": "http://evil.test"})
    assert "access-control-allow-origin" not in off.headers


# ---------- stub behaviour ----------

def test_stubs_return_their_example_with_the_stub_header(client):
    r = client.get(f"/faculty/sessions/{SID}", headers=RAO)
    assert r.status_code == 200 and r.headers["X-Contract-Stub"] == "1"
    assert r.json() == faculty.SessionDetail.model_json_schema()["examples"][0]
    assert "X-Contract-Stub" not in client.get("/health").headers


def test_every_stub_response_validates_against_its_own_schema():
    app = make_app()
    client = TestClient(app, raise_server_exceptions=False)
    spec = app.openapi()
    models = {m.__name__: m for m in all_models()}
    checked = 0
    for path, method, op in operations(app):
        ok = next((c for c in ("200", "201", "202") if c in op["responses"]), None)
        ref = op["responses"][ok].get("content", {}).get("application/json", {}).get("schema", {}).get("$ref")
        if not ref:
            continue
        schema = ref.rsplit("/", 1)[-1]
        headers = RAO if "FacultyToken" in str(op.get("security")) else STUDENT
        body = {"json": {"new_total": 50, "reason": "ok ok"}} if path.endswith("/override") else {}
        body = {"json": {"viva_id": "dsa-midterm-2026", "student_id": "S1", "access_code": "K7M2-9QXP"}} if path == "/student/join" else body
        body = {"json": {"note": "checked it"}} if path.endswith("/review") else body
        body = {"json": {"question_ids": ["q001"]}} if path.endswith("/questions/approve") else body
        body = {"json": {"syllabus": "Arrays and hashing", "count": 2}} if path.endswith("/questions/generate") else body
        body = {"json": {"results_visible_to_students": True}} if method == "patch" else body
        body = {"json": {"accepted": True, "rules_version": "rules-v1"}} if path.endswith("/consent") else body
        body = {"json": {"text": "hello", "client_seq": 1}} if path.endswith("/answer") else body
        body = {"json": {"title": "t", "subject": "s", "topics": ["a"], "difficulty": "easy"}} if path == "/faculty/vivas" and method == "post" else body
        body = {"files": {"file": ("x.csv", b"a,b\n", "text/csv")}} if path.endswith(("/questions", "/roster")) and method == "post" else body
        r = client.request(method.upper(), url_for(path), headers=headers, **body)
        assert r.status_code == int(ok), (path, r.text[:200])
        models[schema].model_validate(r.json())
        checked += 1
    assert checked >= 15 and spec


def test_join_needs_a_code_unless_the_flag_is_off():
    body = {"viva_id": "dsa-midterm-2026", "student_id": "S2024001"}
    strict = TestClient(make_app(), raise_server_exceptions=False)
    r = strict.post("/student/join", json=body)
    assert r.status_code == 422 and r.json()["error"]["details"]["fields"][0]["loc"] == ["body", "access_code"]
    assert strict.post("/student/join", json=body | {"access_code": "K7M2-9QXP"}).status_code == 200
    lax = TestClient(make_app(require_access_code=False))
    assert lax.post("/student/join", json=body).status_code == 200


def test_uploads_are_multipart_files(client):
    spec = client.get("/openapi.json").json()
    for path in ("/faculty/vivas/{viva_id}/questions", "/faculty/vivas/{viva_id}/roster"):
        assert "multipart/form-data" in spec["paths"][path]["post"]["requestBody"]["content"]
    assert client.post(f"/faculty/vivas/x/roster", headers=RAO).status_code == 422  # file is required


def test_audio_range_support(client):
    url = f"/faculty/sessions/{SID}/audio"
    full = client.get(url, headers=RAO)
    assert full.status_code == 200 and full.headers["accept-ranges"] == "bytes" and full.content[:4] == b"RIFF"
    part = client.get(url, headers={**RAO, "Range": "bytes=0-99"})
    assert part.status_code == 206 and len(part.content) == 100
    assert part.headers["content-range"] == f"bytes 0-99/{len(full.content)}"
    assert client.get(url, headers={**RAO, "Range": "bytes=-10"}).content == full.content[-10:]
    assert client.get(url, headers={**RAO, "Range": f"bytes={len(full.content)}-"}).status_code == 416
    assert_error_body(client.get(url, headers={**RAO, "Range": "bytes=abc"}), "range_not_satisfiable")


def test_audio_signed_url_works_without_a_header(client):
    url = f"/faculty/sessions/{SID}/audio?exp=1791784800&sig=9f2c1ab77e0d4c35"
    assert client.get(url).status_code == 200
    assert client.get(f"/faculty/sessions/{SID}/audio").status_code == 401
    assert client.get(f"/faculty/sessions/{SID}/audio", headers=STUDENT).status_code == 403
    example_url = faculty.AudioRef.model_json_schema()["examples"][0]["url"]
    assert re.fullmatch(r"/faculty/sessions/[0-9a-f-]{36}/audio\?exp=\d+&sig=[0-9a-f]+", example_url)


def test_csv_export_is_text_csv(client):
    r = client.get("/faculty/vivas/dsa-midterm-2026/export.csv", headers=RAO)
    assert r.headers["content-type"].startswith("text/csv") and r.text.startswith("student_id,")


# ---------- the freeze ----------

def test_committed_openapi_json_matches_the_code():
    committed = (ROOT / "docs" / "openapi.json").read_text()
    assert committed == openapi_json(create_app(Settings({}, contract_stub=True))), \
        "API contract changed: run `python scripts/export_openapi.py`. After G0 this needs supervisor approval."


def test_openapi_is_independent_of_the_environment():
    assert openapi_json(make_app()) == openapi_json(make_app(require_access_code=False, cors_origins=("http://a.test",)))


def test_openapi_basics():
    spec = make_app().openapi()
    ids = [op["operationId"] for _, _, op in operations(make_app())]
    assert len(ids) == len(set(ids)) == 26
    assert all(op.get("summary") for _, _, op in operations(make_app()))
    assert set(spec["components"]["securitySchemes"]) == {"FacultyToken", "StudentToken"}
    assert "Voice" in spec["info"]["description"] and "VOICE_PROTOCOL.md" in spec["info"]["description"]


# ---------- the mock server really boots ----------

def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_mock_server_boots_with_uvicorn(tmp_path):
    port = free_port()
    env = {"PATH": "/usr/bin:/bin", "FACULTY_TOKENS": "demo:demo-token-0123456789", "HOME": str(tmp_path), "CONTRACT_STUB": "1", "AI_VIVA_NO_DOTENV": "1"}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.api.main:app", "--port", str(port), "--log-level", "warning"],
                            cwd=ROOT / "backend", env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(60):
            try:
                if httpx.get(f"{base}/health", timeout=0.5).status_code == 200:
                    break
            except httpx.TransportError:
                time.sleep(0.1)
        else:
            pytest.fail("server did not start: " + proc.stdout.read().decode()[:500])
        auth = {"Authorization": "Bearer demo-token-0123456789"}
        vivas = httpx.get(f"{base}/faculty/vivas", headers=auth)
        assert vivas.status_code == 200 and vivas.headers["x-contract-stub"] == "1"
        assert httpx.get(f"{base}/faculty/vivas").status_code == 401
        join = httpx.post(f"{base}/student/join", json={"viva_id": "dsa-midterm-2026", "student_id": "S1", "access_code": "K7M2-9QXP"})
        assert join.status_code == 200 and join.json()["session_token"].startswith("st_")
        assert httpx.get(f"{base}/openapi.json").json() == json.loads((ROOT / "docs" / "openapi.json").read_text())
    finally:
        proc.terminate()
        proc.wait(timeout=5)
