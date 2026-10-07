import hmac
from dataclasses import dataclass

from fastapi import Depends, Request
from fastapi.security import HTTPBearer

from .errors import ApiError, ErrorCode

STUDENT_PREFIX = "st_"

faculty_scheme = HTTPBearer(auto_error=False, scheme_name="FacultyToken", description=(
    "Faculty bearer token. The server maps it to a reviewer name (from env FACULTY_TOKENS); "
    "that name is what the override log records. Never send a reviewer name in a body."))
student_scheme = HTTPBearer(auto_error=False, scheme_name="StudentToken", description=(
    "Student session token from POST /student/join. Starts with `st_`. Rejoining issues a new one "
    "and the old one stops working."))


@dataclass(frozen=True)
class Faculty:
    reviewer: str


@dataclass(frozen=True)
class Student:
    token: str


def _faculty_name(request: Request, token: str):
    found = None
    for known, name in request.app.state.settings.faculty_tokens.items():  # compare all: constant time per token
        if hmac.compare_digest(known.encode(), token.encode()):
            found = name
    return found


def require_faculty(request: Request, creds=Depends(faculty_scheme)) -> Faculty:
    if creds is None:
        raise ApiError(ErrorCode.unauthorized, details={"reason": "missing_token"})
    name = _faculty_name(request, creds.credentials)
    if name is not None:
        return Faculty(name)
    if creds.credentials.startswith(STUDENT_PREFIX):
        raise ApiError(ErrorCode.forbidden, "A student token cannot use faculty routes.")
    raise ApiError(ErrorCode.unauthorized, details={"reason": "invalid_token"})


def require_student(request: Request, creds=Depends(student_scheme)) -> Student:
    """Contract phase: any `st_` token passes. T2b swaps this for a hashed lookup and a check that the
    token belongs to the {sid} in the path (403 `forbidden` otherwise)."""
    if creds is None:
        raise ApiError(ErrorCode.unauthorized, details={"reason": "missing_token"})
    token = creds.credentials
    if token.startswith(STUDENT_PREFIX):
        return Student(token)
    if _faculty_name(request, token) is not None:
        raise ApiError(ErrorCode.forbidden, "A faculty token cannot use student routes.")
    raise ApiError(ErrorCode.unauthorized, details={"reason": "invalid_token"})
