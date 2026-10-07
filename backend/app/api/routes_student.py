from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request

from .auth import require_student
from .errors import ApiError, ErrorCode, error_responses
from .schemas.common import example_of
from .schemas.student import (AnswerRequest, AnswerResponse, ConsentRequest, ConsentResponse, JoinRequest,
                              JoinResponse, StartResponse, StatusResponse)
from .stub import stub_marker

AUTH = (ErrorCode.unauthorized, ErrorCode.forbidden)
SID = Path(description="Session ID (UUID) from join.", examples=["7c9e6679-7425-40de-944b-e07fc1f90ae7"])

join_router = APIRouter(prefix="/student", tags=["student"], dependencies=[Depends(stub_marker)])
router = APIRouter(prefix="/student", tags=["student"], dependencies=[Depends(require_student), Depends(stub_marker)])


@join_router.post("/join", response_model=JoinResponse, summary="Log in with student ID and access code",
                  responses=error_responses(ErrorCode.validation_error, ErrorCode.invalid_credentials,
                                            ErrorCode.session_ended, ErrorCode.rate_limited))
def student_join(body: JoinRequest, request: Request):
    """No Authorization header. Creates the student's one session for this viva, or **rejoins** it: rejoining with
    the same code is allowed while the session is `created`, `consented` or `in_progress`, returns `resumed: true`
    and a **new token (the old one stops working, 401)**. Once the session has ended the code is dead
    (409 `session_ended`). Wrong ID and wrong code both give the same 403 `invalid_credentials`; repeated failures
    give 429 `rate_limited`. The access code is required (D10)."""
    if request.app.state.settings.require_access_code and not body.access_code:
        raise ApiError(ErrorCode.validation_error, "access_code is required.",
                       {"fields": [{"loc": ["body", "access_code"], "message": "Field required"}]})
    return example_of(JoinResponse)


@router.post("/sessions/{sid}/consent", response_model=ConsentResponse, summary="Accept the rules and recording",
             responses=error_responses(*AUTH, ErrorCode.not_found, ErrorCode.rules_version_mismatch, ErrorCode.invalid_state))
def student_consent(body: ConsentRequest, sid: UUID = SID):
    """accepted=true: `created` -> `consented` (repeating it is a no-op). accepted=false: nothing changes, no recording,
    the student cannot start. `rules_version` must be the one from join, else 409 `rules_version_mismatch`."""
    return example_of(ConsentResponse)


@router.post("/sessions/{sid}/start", response_model=StartResponse, summary="Start the viva clock",
             responses=error_responses(*AUTH, ErrorCode.not_found, ErrorCode.invalid_state, ErrorCode.session_ended))
def student_start(sid: UUID = SID):
    """Needs consent (else 409 `invalid_state`). Sets `started_at` on the server, so `deadline_at` = started_at + 15 min
    and cannot be changed by the client. Returns the first AI turn. Calling it again while `in_progress` is safe: it
    returns the original times and the current AI turn."""
    return example_of(StartResponse)


@router.post("/sessions/{sid}/answer", response_model=AnswerResponse, summary="Send an answer, get the next AI turn",
             responses=error_responses(*AUTH, ErrorCode.not_found, ErrorCode.validation_error, ErrorCode.invalid_state,
                                       ErrorCode.deadline_passed, ErrorCode.session_ended, ErrorCode.bad_client_seq,
                                       ErrorCode.provider_unavailable))
def student_answer(body: AnswerRequest, sid: UUID = SID):
    """**Idempotent on `client_seq`**: sending the same `client_seq` with the same `text` again returns the same reply
    (`replayed: true`) and records nothing twice, so retry freely after a timeout. A reused `client_seq` with different
    text, or one that skips ahead, is 409 `bad_client_seq` (`details.expected`). After the deadline the answer is
    rejected with 409 `deadline_passed` and `details.closing_text`; the session is ended and later calls get
    `session_ended`. `turn.ended: true` marks the closing turn. On 503 `provider_unavailable` retry the same request."""
    return example_of(AnswerResponse)


@router.get("/sessions/{sid}/status", response_model=StatusResponse, summary="Timer and where the student is",
            responses=error_responses(*AUTH, ErrorCode.not_found))
def student_status(sid: UUID = SID):
    """Poll for the timer: `remaining_ms` is computed from the server clock; show `server_now` skew-corrected.
    After a reload or rejoin use `current_turn` and `last_client_seq` to resume."""
    return example_of(StatusResponse)


# Voice (WebSocket) is reserved and NOT part of this contract yet: see the API description (task T4).
