from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Path, Query, Request, Response, UploadFile

from ..services.stubs import CSV_EXAMPLE
from ..session_state import SessionStatus
from .auth import faculty_scheme, require_faculty
from ..services.secrets_util import audio_signature_ok
from .errors import ErrorCode, error_responses
from .schemas.faculty import (ApproveQuestions, GenerateQuestionsRequest, OverrideRequest, OverrideResult, QuestionList, RescoreResult, ResetCodeResult, ReviewRequest,
                              ReviewResult, RosterEntry, RosterList, RosterUploadResult, SessionDetail, SessionList, Viva, VivaCreate,
                              VivaList, VivaUpdate)
from .deps import faculty_ops
from .stub import byte_range, stub_marker

AUTH = (ErrorCode.unauthorized, ErrorCode.forbidden)
VIVA = Path(description="Viva ID (slug).", examples=["dsa-midterm-2026"])
SID = Path(description="Session ID (UUID).", examples=["7c9e6679-7425-40de-944b-e07fc1f90ae7"])
MAX_UPLOAD = 1_000_001  # read one byte past the 1 MB limit so the parser can reject oversized files without loading them

router = APIRouter(prefix="/faculty", tags=["faculty"], dependencies=[Depends(require_faculty), Depends(stub_marker)])
audio_router = APIRouter(prefix="/faculty", tags=["faculty"], dependencies=[Depends(stub_marker)])


@router.post("/vivas", response_model=Viva, status_code=201, summary="Create a viva",
             responses=error_responses(*AUTH, ErrorCode.validation_error, ErrorCode.already_exists))
def create_viva(body: VivaCreate, ops=Depends(faculty_ops), faculty=Depends(require_faculty)):
    """Creates a viva with the platform's fixed 15-minute structure and rubric. Then upload the question bank and the roster."""
    return ops.create_viva(body, faculty)


@router.get("/vivas", response_model=VivaList, summary="List vivas", responses=error_responses(*AUTH))
def list_vivas(ops=Depends(faculty_ops)):
    """Newest first. A cheap way for the dashboard to check that a pasted token works."""
    return ops.list_vivas()


@router.get("/vivas/{viva_id}", response_model=Viva, summary="Get one viva",
            responses=error_responses(*AUTH, ErrorCode.not_found))
def get_viva(viva_id: str = VIVA, ops=Depends(faculty_ops)):
    return ops.get_viva(viva_id)


@router.patch("/vivas/{viva_id}", response_model=Viva, summary="Update a viva",
              responses=error_responses(*AUTH, ErrorCode.not_found, ErrorCode.validation_error))
def update_viva(body: VivaUpdate, viva_id: str = VIVA, ops=Depends(faculty_ops)):
    """Only `results_visible_to_students` can change after creation (release or hide student results)."""
    return ops.update_viva(viva_id, body)


@router.post("/vivas/{viva_id}/questions", response_model=QuestionList, summary="Upload the question bank",
             responses=error_responses(*AUTH, ErrorCode.not_found, ErrorCode.invalid_upload, ErrorCode.invalid_state))
def upload_questions(viva_id: str = VIVA, file: UploadFile = File(description="A .csv or .json file (picked by file extension)."),
                     ops=Depends(faculty_ops)):
    """Replaces the whole bank, atomically: if any row is invalid nothing changes and the response is a 422
    `invalid_upload` with `details.rows` = [{row, field, message}] (row is 1-based, the CSV header is row 0).

    - **JSON**: an array of `QuestionIn` objects.
    - **CSV**: header `id,topic,type,difficulty,text,key_points` plus an optional `source` column (`bank` or `ai-draft`); `key_points` are separated by `|`.

    Locked (409 `invalid_state`) once any student has joined. A small bank is allowed but returns `warnings`."""
    return ops.upload_questions(viva_id, file.filename, file.file.read(MAX_UPLOAD))


@router.post("/vivas/{viva_id}/questions/generate", response_model=QuestionList, summary="Generate review-only questions from a syllabus",
             responses=error_responses(*AUTH, ErrorCode.not_found, ErrorCode.invalid_state, ErrorCode.provider_unavailable))
def generate_questions(body: GenerateQuestionsRequest, request: Request, viva_id: str = VIVA, ops=Depends(faculty_ops)):
    """Generates a bounded set of `ai-draft` questions using the configured LLM chain. Faculty must review and approve drafts
    before the student interviewer can use them. Syllabus text is not stored; the endpoint is locked after any student joins."""
    return ops.generate_questions(viva_id, body, request.app.state.llm_factory(None))


@router.get("/vivas/{viva_id}/questions", response_model=QuestionList, summary="Get the question bank",
            responses=error_responses(*AUTH, ErrorCode.not_found))
def list_questions(viva_id: str = VIVA, ops=Depends(faculty_ops)):
    """Includes `key_points`, which students never see."""
    return ops.list_questions(viva_id)


@router.post("/vivas/{viva_id}/questions/approve", response_model=QuestionList, summary="Approve AI-drafted questions",
             responses=error_responses(*AUTH, ErrorCode.not_found, ErrorCode.validation_error, ErrorCode.invalid_state))
def approve_questions(body: ApproveQuestions, viva_id: str = VIVA, ops=Depends(faculty_ops), faculty=Depends(require_faculty)):
    """Turns `ai-draft` questions into `bank` questions and records who approved them (`approved_by`, the reviewer of the token).
    Send `question_ids` to approve some, or `{}` to approve every draft. Idempotent: approving a question that is already
    `bank` changes nothing, and the original `approved_by` stays. An unknown id is a 404 and nothing changes. Locked (409
    `invalid_state`, reason `students_joined`) once any student has joined, like the upload. Returns the whole bank."""
    return ops.approve_questions(viva_id, body, faculty)


@router.post("/vivas/{viva_id}/roster", response_model=RosterUploadResult, summary="Upload the roster, issue access codes",
             responses=error_responses(*AUTH, ErrorCode.not_found, ErrorCode.invalid_upload))
def upload_roster(viva_id: str = VIVA, file: UploadFile = File(description="A .csv file: header `student_id,name` (name optional)."),
                  ops=Depends(faculty_ops)):
    """Adds students; existing ones are left alone (`unchanged`, no new code). Each new student gets a one-time
    access code, returned **in plaintext only in this response** and stored hashed. Print or save it now; if lost,
    use `reset-code`. Atomic like the bank upload (422 `invalid_upload` with per-row errors)."""
    return ops.upload_roster(viva_id, file.filename, file.file.read(MAX_UPLOAD))


@router.get("/vivas/{viva_id}/roster", response_model=RosterList, summary="List the roster",
            responses=error_responses(*AUTH, ErrorCode.not_found))
def list_roster(viva_id: str = VIVA, ops=Depends(faculty_ops)):
    """Students with session status and whether an active code can start/rejoin a session. Never contains code values."""
    return ops.list_roster(viva_id)


@router.post("/vivas/{viva_id}/roster/{student_id}/reset-code", response_model=ResetCodeResult,
             summary="Issue a new access code for one student",
             responses=error_responses(*AUTH, ErrorCode.not_found, ErrorCode.invalid_state))
def reset_code(viva_id: str = VIVA, student_id: str = Path(examples=["S2024002"]), ops=Depends(faculty_ops)):
    """The old code stops working at once; the new one is returned in plaintext once. Not allowed (409 `invalid_state`)
    after the student's session has ended."""
    return ops.reset_code(viva_id, student_id)


@router.post("/vivas/{viva_id}/roster/{student_id}/revoke-code", response_model=RosterEntry,
             summary="Revoke a student's access code",
             responses=error_responses(*AUTH, ErrorCode.not_found))
def revoke_code(viva_id: str = VIVA, student_id: str = Path(examples=["S2024002"]), ops=Depends(faculty_ops)):
    """Revokes the active code so it cannot be used for future joins or rejoins. Idempotent. Does not end an existing
    session or invalidate its session token; it preserves the student's session, transcript and audit records."""
    return ops.revoke_code(viva_id, student_id)


@router.get("/vivas/{viva_id}/sessions", response_model=SessionList, summary="List sessions",
            responses=error_responses(*AUTH, ErrorCode.not_found, ErrorCode.validation_error))
def list_sessions(viva_id: str = VIVA,
                  status: Optional[SessionStatus] = Query(None, description="Only this status."),
                  low_confidence: Optional[bool] = Query(None, description="true: only flagged for review."),
                  search: Optional[str] = Query(None, description="Case-insensitive match on student ID or name."),
                  limit: int = Query(50, ge=1, le=200),
                  cursor: Optional[str] = Query(None, description="`next_cursor` from the previous page."),
                  ops=Depends(faculty_ops)):
    """Newest first, cursor pagination. The cursor is opaque; do not build or parse it."""
    return ops.list_sessions(viva_id, status, low_confidence, search, limit, cursor)


@router.get("/sessions/{sid}", response_model=SessionDetail, summary="Session detail for audit and replay",
            responses=error_responses(*AUTH, ErrorCode.not_found))
def get_session(sid: UUID = SID, ops=Depends(faculty_ops)):
    """Transcript, scores per run and the median, per-dimension reason and evidence, feedback, overrides, integrity
    events and the audio reference. Evidence numbers are `turns[].idx`; to replay a piece of evidence seek the audio
    to that turn's `t_start_ms`. `effective_total` is the latest override's `new_total`, else the AI median."""
    return ops.get_session(sid)


@router.post("/sessions/{sid}/override", response_model=OverrideResult, status_code=201, summary="Override a mark",
             responses=error_responses(*AUTH, ErrorCode.not_found, ErrorCode.validation_error, ErrorCode.invalid_state))
def override_session(body: OverrideRequest, sid: UUID = SID, faculty=Depends(require_faculty), ops=Depends(faculty_ops)):
    """Logs a new override entry: reviewer (taken from the token, never from the body), old effective total,
    new total, reason, timestamp. The latest entry wins; earlier ones stay in the history. Only for `scored` or
    `failed` sessions (409 `invalid_state` otherwise). `new_total` may equal the current total to confirm a
    low-confidence result after review."""
    return ops.override_session(sid, body, faculty)


@router.post("/sessions/{sid}/review", response_model=ReviewResult, status_code=201, summary="Mark a result as reviewed",
             responses=error_responses(*AUTH, ErrorCode.not_found, ErrorCode.validation_error, ErrorCode.invalid_state))
def review_session(body: ReviewRequest, sid: UUID = SID, faculty=Depends(require_faculty), ops=Depends(faculty_ops)):
    """Clears the mandatory-review flag (`needs_review`) without changing the mark. Logged with the reviewer (from the
    token), a note and a timestamp; shown in `reviews`. Only for `scored` or `failed` sessions (409 `invalid_state`)."""
    return ops.review_session(sid, body, faculty)


@router.post("/sessions/{sid}/rescore", response_model=RescoreResult, status_code=202, summary="Queue the session for scoring again",
             responses=error_responses(*AUTH, ErrorCode.not_found, ErrorCode.invalid_state))
def rescore_session(sid: UUID = SID, ops=Depends(faculty_ops)):
    """Only from `failed` or `scored` (409 `invalid_state` otherwise). The session goes back to `ended` and a scoring
    job is queued; the worker produces new runs. Earlier overrides and reviews stay in the history."""
    return ops.rescore_session(sid)


@router.get("/vivas/{viva_id}/export.csv", summary="Export marks as CSV (optional feature)",
            responses={200: {"description": "One row per session. Columns: student_id, name, status, ai_total, "
                             "effective_total, overridden, low_confidence, needs_review, one column per rubric "
                             "dimension (median score), last_reviewer.",
                             "content": {"text/csv": {"schema": {"type": "string"}, "example": CSV_EXAMPLE}}},
                       **error_responses(*AUTH, ErrorCode.not_found)})
def export_viva_csv(viva_id: str = VIVA, ops=Depends(faculty_ops)):
    """Optional: the dashboard may skip it. Spreadsheet-friendly, UTF-8."""
    return Response(ops.export_csv(viva_id), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{viva_id}.csv"'})


def audio_access(request: Request, exp: Optional[int] = Query(None, description="Unix seconds; part of a signed URL."),
                 sig: Optional[str] = Query(None, description="Signature from `audio.url`; replaces the Authorization header."),
                 creds=Depends(faculty_scheme)):
    """Either a signed URL (so an <audio> tag works without headers) or a faculty bearer token."""
    settings = request.app.state.settings
    if sig and exp:
        if settings.contract_stub:  # contract phase: any signature passes
            return None
        try:
            sid = UUID(request.path_params["sid"])
        except ValueError:
            return None  # the route's own path validation answers 422
        if audio_signature_ok(settings.audio_signing_secret, sid, exp, sig, request.app.state.now().timestamp()):
            return None
    return require_faculty(request, creds)


@audio_router.get("/sessions/{sid}/audio", summary="Session audio (supports Range)",
                  response_class=Response, dependencies=[Depends(audio_access)],
                  responses={200: {"description": "The whole recording.", "content": {"audio/wav": {"schema": {"type": "string", "format": "binary"}}}},
                             206: {"description": "Partial content for a `Range: bytes=a-b` request.", "content": {"audio/wav": {"schema": {"type": "string", "format": "binary"}}}},
                             **error_responses(*AUTH, ErrorCode.not_found, ErrorCode.audio_not_available, ErrorCode.range_not_satisfiable)})
def get_session_audio(request: Request, sid: UUID = SID, ops=Depends(faculty_ops)):
    """The recording. **Supports HTTP `Range`** (single `bytes=start-end` range -> 206 with `Content-Range`;
    `Accept-Ranges: bytes` always), which is what makes click-to-seek work in an `<audio>` element.
    Authenticate with the Authorization header, or use the signed `audio.url` from the session detail (no header)."""
    source = ops.audio(sid)
    span = byte_range(request.headers.get("range"), source.size)
    headers = {"Accept-Ranges": "bytes"}
    if span is None:
        return Response(source.read(0, source.size - 1), media_type=source.content_type, headers=headers)
    start, end = span
    headers["Content-Range"] = f"bytes {start}-{end}/{source.size}"
    return Response(source.read(start, end), status_code=206, media_type=source.content_type, headers=headers)
