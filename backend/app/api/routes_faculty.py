from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Path, Query, Request, Response, UploadFile

from ..session_state import SessionStatus
from .auth import faculty_scheme, require_faculty
from .errors import ApiError, ErrorCode, error_responses
from .schemas.common import example_of
from .schemas.faculty import (OverrideRequest, OverrideResult, QuestionList, ResetCodeResult, RosterList,
                              RosterUploadResult, SessionDetail, SessionList, Viva, VivaCreate, VivaList)
from .stub import byte_range, silent_wav, stub_marker

AUTH = (ErrorCode.unauthorized, ErrorCode.forbidden)
VIVA = Path(description="Viva ID (slug).", examples=["dsa-midterm-2026"])
SID = Path(description="Session ID (UUID).", examples=["7c9e6679-7425-40de-944b-e07fc1f90ae7"])
CSV_EXAMPLE = ("student_id,name,status,ai_total,effective_total,overridden,low_confidence,needs_review,"
               "conceptual,depth,problem,practical,communication,last_reviewer\n"
               "S2024001,Asha Verma,scored,71.0,78.0,true,false,false,4,3,3,4,4,dr-rao\n")

router = APIRouter(prefix="/faculty", tags=["faculty"], dependencies=[Depends(require_faculty), Depends(stub_marker)])
audio_router = APIRouter(prefix="/faculty", tags=["faculty"], dependencies=[Depends(stub_marker)])


@router.post("/vivas", response_model=Viva, status_code=201, summary="Create a viva",
             responses=error_responses(*AUTH, ErrorCode.validation_error, ErrorCode.already_exists))
def create_viva(body: VivaCreate):
    """Creates a viva with the platform's fixed 15-minute structure and rubric. Then upload the question bank and the roster."""
    return example_of(Viva)


@router.get("/vivas", response_model=VivaList, summary="List vivas", responses=error_responses(*AUTH))
def list_vivas():
    """Newest first. A cheap way for the dashboard to check that a pasted token works."""
    return example_of(VivaList)


@router.get("/vivas/{viva_id}", response_model=Viva, summary="Get one viva",
            responses=error_responses(*AUTH, ErrorCode.not_found))
def get_viva(viva_id: str = VIVA):
    return example_of(Viva)


@router.post("/vivas/{viva_id}/questions", response_model=QuestionList, summary="Upload the question bank",
             responses=error_responses(*AUTH, ErrorCode.not_found, ErrorCode.invalid_upload, ErrorCode.invalid_state))
def upload_questions(viva_id: str = VIVA, file: UploadFile = File(description="A .csv or .json file (picked by file extension).")):
    """Replaces the whole bank, atomically: if any row is invalid nothing changes and the response is a 422
    `invalid_upload` with `details.rows` = [{row, field, message}] (row is 1-based, the CSV header is row 0).

    - **JSON**: an array of `QuestionIn` objects.
    - **CSV**: header `id,topic,type,difficulty,text,key_points`; `key_points` are separated by `|`.

    Locked (409 `invalid_state`) once any student has joined. A small bank is allowed but returns `warnings`."""
    return example_of(QuestionList)


@router.get("/vivas/{viva_id}/questions", response_model=QuestionList, summary="Get the question bank",
            responses=error_responses(*AUTH, ErrorCode.not_found))
def list_questions(viva_id: str = VIVA):
    """Includes `key_points`, which students never see."""
    return example_of(QuestionList)


@router.post("/vivas/{viva_id}/roster", response_model=RosterUploadResult, summary="Upload the roster, issue access codes",
             responses=error_responses(*AUTH, ErrorCode.not_found, ErrorCode.invalid_upload))
def upload_roster(viva_id: str = VIVA, file: UploadFile = File(description="A .csv file: header `student_id,name` (name optional).")):
    """Adds students; existing ones are left alone (`unchanged`, no new code). Each new student gets a one-time
    access code, returned **in plaintext only in this response** and stored hashed. Print or save it now; if lost,
    use `reset-code`. Atomic like the bank upload (422 `invalid_upload` with per-row errors)."""
    return example_of(RosterUploadResult)


@router.get("/vivas/{viva_id}/roster", response_model=RosterList, summary="List the roster",
            responses=error_responses(*AUTH, ErrorCode.not_found))
def list_roster(viva_id: str = VIVA):
    """Students with the status of their session, if any. Never contains access codes."""
    return example_of(RosterList)


@router.post("/vivas/{viva_id}/roster/{student_id}/reset-code", response_model=ResetCodeResult,
             summary="Issue a new access code for one student",
             responses=error_responses(*AUTH, ErrorCode.not_found, ErrorCode.invalid_state))
def reset_code(viva_id: str = VIVA, student_id: str = Path(examples=["S2024002"])):
    """The old code stops working at once; the new one is returned in plaintext once. Not allowed (409 `invalid_state`)
    after the student's session has ended."""
    return example_of(ResetCodeResult)


@router.get("/vivas/{viva_id}/sessions", response_model=SessionList, summary="List sessions",
            responses=error_responses(*AUTH, ErrorCode.not_found, ErrorCode.validation_error))
def list_sessions(viva_id: str = VIVA,
                  status: Optional[SessionStatus] = Query(None, description="Only this status."),
                  low_confidence: Optional[bool] = Query(None, description="true: only flagged for review."),
                  search: Optional[str] = Query(None, description="Case-insensitive match on student ID or name."),
                  limit: int = Query(50, ge=1, le=200),
                  cursor: Optional[str] = Query(None, description="`next_cursor` from the previous page.")):
    """Newest first, cursor pagination. The cursor is opaque; do not build or parse it."""
    return example_of(SessionList)


@router.get("/sessions/{sid}", response_model=SessionDetail, summary="Session detail for audit and replay",
            responses=error_responses(*AUTH, ErrorCode.not_found))
def get_session(sid: UUID = SID):
    """Transcript, scores per run and the median, per-dimension reason and evidence, feedback, overrides, integrity
    events and the audio reference. Evidence numbers are `turns[].idx`; to replay a piece of evidence seek the audio
    to that turn's `t_start_ms`. `effective_total` is the latest override's `new_total`, else the AI median."""
    return example_of(SessionDetail)


@router.post("/sessions/{sid}/override", response_model=OverrideResult, status_code=201, summary="Override a mark",
             responses=error_responses(*AUTH, ErrorCode.not_found, ErrorCode.validation_error, ErrorCode.invalid_state))
def override_session(body: OverrideRequest, sid: UUID = SID, faculty=Depends(require_faculty)):
    """Logs a new override entry: reviewer (taken from the token, never from the body), old effective total,
    new total, reason, timestamp. The latest entry wins; earlier ones stay in the history. Only for `scored` or
    `failed` sessions (409 `invalid_state` otherwise). `new_total` may equal the current total to confirm a
    low-confidence result after review."""
    result = example_of(OverrideResult)
    result.override.reviewer = faculty.reviewer  # identity comes from the token
    return result


@router.get("/vivas/{viva_id}/export.csv", summary="Export marks as CSV (optional feature)",
            responses={200: {"description": "One row per session. Columns: student_id, name, status, ai_total, "
                             "effective_total, overridden, low_confidence, needs_review, one column per rubric "
                             "dimension (median score), last_reviewer.",
                             "content": {"text/csv": {"schema": {"type": "string"}, "example": CSV_EXAMPLE}}},
                       **error_responses(*AUTH, ErrorCode.not_found)})
def export_viva_csv(viva_id: str = VIVA):
    """Optional: the dashboard may skip it. Spreadsheet-friendly, UTF-8."""
    return Response(CSV_EXAMPLE, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{viva_id}.csv"'})


def audio_access(request: Request, exp: Optional[int] = Query(None, description="Unix seconds; part of a signed URL."),
                 sig: Optional[str] = Query(None, description="Signature from `audio.url`; replaces the Authorization header."),
                 creds=Depends(faculty_scheme)):
    """Either a signed URL (so an <audio> tag works without headers) or a faculty bearer token."""
    if sig and exp:  # contract phase: any signature passes; T2b verifies the HMAC and expiry
        return None
    return require_faculty(request, creds)


@audio_router.get("/sessions/{sid}/audio", summary="Session audio (supports Range)",
                  response_class=Response, dependencies=[Depends(audio_access)],
                  responses={200: {"description": "The whole recording.", "content": {"audio/wav": {"schema": {"type": "string", "format": "binary"}}}},
                             206: {"description": "Partial content for a `Range: bytes=a-b` request.", "content": {"audio/wav": {"schema": {"type": "string", "format": "binary"}}}},
                             **error_responses(*AUTH, ErrorCode.not_found, ErrorCode.range_not_satisfiable)})
def get_session_audio(request: Request, sid: UUID = SID):
    """The recording. **Supports HTTP `Range`** (single `bytes=start-end` range -> 206 with `Content-Range`;
    `Accept-Ranges: bytes` always), which is what makes click-to-seek work in an `<audio>` element.
    Authenticate with the Authorization header, or use the signed `audio.url` from the session detail (no header)."""
    data = silent_wav()
    span = byte_range(request.headers.get("range"), len(data))
    headers = {"Accept-Ranges": "bytes"}
    if span is None:
        return Response(data, media_type="audio/wav", headers=headers)
    start, end = span
    headers["Content-Range"] = f"bytes {start}-{end}/{len(data)}"
    return Response(data[start:end + 1], status_code=206, media_type="audio/wav", headers=headers)
