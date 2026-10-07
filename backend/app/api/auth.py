import hmac
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPBearer
from sqlalchemy import select

from ..db import models as m
from ..services.secrets_util import hash_token
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


def _owner_of(request: Request, token: str):
    with request.app.state.sessionmaker() as db:
        return db.scalar(select(m.Session.id).where(m.Session.token_hash == hash_token(token)))


def require_student(request: Request, creds=Depends(student_scheme)) -> Student:
    """Real mode: the token is looked up by its hash and must belong to the {sid} in the path. An unknown or replaced
    token is 401; a valid token on someone else's session is 403. Stub mode: any `st_` token passes."""
    if creds is None:
        raise ApiError(ErrorCode.unauthorized, details={"reason": "missing_token"})
    token = creds.credentials
    if token.startswith(STUDENT_PREFIX):
        if request.app.state.settings.contract_stub:
            return Student(token)
        owner = _owner_of(request, token)
        if owner is None:
            raise ApiError(ErrorCode.unauthorized, details={"reason": "invalid_or_replaced_token"})
        try:
            wanted = UUID(request.path_params.get("sid", ""))
        except ValueError:
            wanted = owner  # not a session path, or a bad id that the route's own validation rejects with 422
        if owner != wanted:
            raise ApiError(ErrorCode.forbidden, "This token belongs to another session.")
        return Student(token)
    if _faculty_name(request, token) is not None:
        raise ApiError(ErrorCode.forbidden, "A faculty token cannot use student routes.")
    raise ApiError(ErrorCode.unauthorized, details={"reason": "invalid_token"})
