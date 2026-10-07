from enum import Enum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErrorCode(str, Enum):
    unauthorized = "unauthorized"
    forbidden = "forbidden"
    not_found = "not_found"
    method_not_allowed = "method_not_allowed"
    validation_error = "validation_error"
    invalid_upload = "invalid_upload"
    invalid_credentials = "invalid_credentials"
    already_exists = "already_exists"
    invalid_state = "invalid_state"
    session_ended = "session_ended"
    deadline_passed = "deadline_passed"
    bad_client_seq = "bad_client_seq"
    rules_version_mismatch = "rules_version_mismatch"
    range_not_satisfiable = "range_not_satisfiable"
    rate_limited = "rate_limited"
    provider_unavailable = "provider_unavailable"
    internal_error = "internal_error"


HTTP_STATUS = {
    ErrorCode.unauthorized: 401,
    ErrorCode.forbidden: 403,
    ErrorCode.not_found: 404,
    ErrorCode.method_not_allowed: 405,
    ErrorCode.validation_error: 422,
    ErrorCode.invalid_upload: 422,
    ErrorCode.invalid_credentials: 403,
    ErrorCode.already_exists: 409,
    ErrorCode.invalid_state: 409,
    ErrorCode.session_ended: 409,
    ErrorCode.deadline_passed: 409,
    ErrorCode.bad_client_seq: 409,
    ErrorCode.rules_version_mismatch: 409,
    ErrorCode.range_not_satisfiable: 416,
    ErrorCode.rate_limited: 429,
    ErrorCode.provider_unavailable: 503,
    ErrorCode.internal_error: 500,
}

# what each code means, and the details keys it carries (these feed docs/API.md and the OpenAPI examples)
ERROR_EXAMPLES = {
    ErrorCode.unauthorized: ("Missing, malformed, unknown or replaced token.", {"reason": "missing_token"}),
    ErrorCode.forbidden: ("The token is valid but not allowed here (wrong role or someone else's session).", {}),
    ErrorCode.not_found: ("No such viva, session, student or audio.", {"resource": "viva"}),
    ErrorCode.method_not_allowed: ("This path does not support that HTTP method.", {}),
    ErrorCode.validation_error: ("The request body, query or path failed validation.",
                                 {"fields": [{"loc": ["body", "text"], "message": "Field required"}]}),
    ErrorCode.invalid_upload: ("A CSV/JSON upload had bad rows. Nothing was stored.",
                               {"rows": [{"row": 3, "field": "type", "message": "must be concept or applied"}]}),
    ErrorCode.invalid_credentials: ("Unknown student ID or wrong access code (deliberately not distinguished).", {}),
    ErrorCode.already_exists: ("That ID is already taken.", {"resource": "viva", "id": "dsa-midterm-2026"}),
    ErrorCode.invalid_state: ("The action is not allowed in the current state.",
                              {"status": "created", "required_status": "consented"}),
    ErrorCode.session_ended: ("The viva is over; the access code and session token no longer start or continue it.",
                              {"status": "ended"}),
    ErrorCode.deadline_passed: ("The 15 minutes are up. The answer was NOT recorded; show closing_text and finish.",
                                {"closing_text": "Time is up. Thank you, that's the end of the viva.",
                                 "deadline_at": "2026-10-12T05:45:12Z"}),
    ErrorCode.bad_client_seq: ("client_seq was reused with different text, or skipped ahead.",
                               {"expected": 4, "received": 6}),
    ErrorCode.rules_version_mismatch: ("The student consented to an older rules text. Show the current rules again.",
                                       {"current_rules_version": "rules-v1"}),
    ErrorCode.range_not_satisfiable: ("The Range header is outside the audio file.", {"size_bytes": 1048576}),
    ErrorCode.rate_limited: ("Too many attempts. Retry after the delay.", {"retry_after_ms": 30000}),
    ErrorCode.provider_unavailable: ("The language model is down after retries and fallback. Retry the same request "
                                     "(same client_seq); nothing was lost.", {"retry_after_ms": 3000}),
    ErrorCode.internal_error: ("Unexpected server error.", {}),
}


class ErrorBody(BaseModel):
    """The error payload. `code` is one of a fixed list so clients can branch on it; `message` is for humans."""
    code: ErrorCode = Field(description="Machine-readable error code (closed list).")
    message: str = Field(description="Short English explanation, safe to show to users.")
    details: dict[str, Any] = Field(default_factory=dict, description="Code-specific extras; may be empty.")
    model_config = ConfigDict(json_schema_extra={"examples": [
        {"code": "deadline_passed", "message": "The 15 minutes are up.",
         "details": {"closing_text": "Time is up. Thank you, that's the end of the viva.",
                     "deadline_at": "2026-10-12T05:45:12Z"}}]})


class ErrorResponse(BaseModel):
    """Every non-2xx response from this API has exactly this shape."""
    error: ErrorBody
    model_config = ConfigDict(json_schema_extra={"examples": [
        {"error": {"code": "not_found", "message": "No such viva.", "details": {"resource": "viva"}}}]})


class ApiError(Exception):
    def __init__(self, code: ErrorCode, message: str = None, details: dict = None):
        self.code = ErrorCode(code)
        self.message = message or ERROR_EXAMPLES[self.code][0]
        self.details = details if details is not None else {}
        super().__init__(self.message)


def error_json(code, message, details=None, headers=None):
    code = ErrorCode(code)
    body = ErrorResponse(error=ErrorBody(code=code, message=message, details=details or {}))
    return JSONResponse(body.model_dump(mode="json"), status_code=HTTP_STATUS[code], headers=headers)


def error_responses(*codes):
    """OpenAPI `responses=` entries for a route: one entry per HTTP status, one example per code."""
    out = {}
    for code in codes:
        code = ErrorCode(code)
        message, details = ERROR_EXAMPLES[code]
        entry = out.setdefault(HTTP_STATUS[code], {"model": ErrorResponse, "description": "", "content": {
            "application/json": {"examples": {}}}})
        entry["description"] += f"`{code.value}`: {message} "
        entry["content"]["application/json"]["examples"][code.value] = {
            "value": {"error": {"code": code.value, "message": message, "details": details}}}
    for entry in out.values():
        entry["description"] = entry["description"].strip()
    return out


def uniform_validation_errors(schema: dict):
    """FastAPI adds its own 422 body to routes with parameters; point those at ErrorResponse and drop its schemas."""
    fixed = error_responses(ErrorCode.validation_error)[422]
    for path in schema["paths"].values():
        for op in path.values():
            resp = op["responses"].get("422")
            if resp and "HTTPValidationError" in str(resp):
                op["responses"]["422"] = {"description": fixed["description"], "content": {"application/json": {
                    "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                    "examples": fixed["content"]["application/json"]["examples"]}}}
    for name in ("HTTPValidationError", "ValidationError"):
        schema["components"]["schemas"].pop(name, None)


def install_error_handlers(app: FastAPI):
    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError):
        headers = {"WWW-Authenticate": "Bearer"} if exc.code == ErrorCode.unauthorized else None
        return error_json(exc.code, exc.message, exc.details, headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        fields = [{"loc": list(e["loc"]), "message": e["msg"]} for e in exc.errors()]
        return error_json(ErrorCode.validation_error, "The request failed validation.", {"fields": fields})

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            return error_json(ErrorCode.not_found, "No such path.", {"resource": "path"})
        if exc.status_code == 405:
            return error_json(ErrorCode.method_not_allowed, ERROR_EXAMPLES[ErrorCode.method_not_allowed][0])
        return error_json(ErrorCode.internal_error, str(exc.detail))

    @app.exception_handler(Exception)
    async def crash(request: Request, exc: Exception):
        return error_json(ErrorCode.internal_error, ERROR_EXAMPLES[ErrorCode.internal_error][0])
