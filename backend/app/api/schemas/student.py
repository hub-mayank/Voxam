from typing import Optional
from uuid import UUID

from pydantic import ConfigDict, Field

from ...session_state import SessionStatus
from .common import ApiRequest, ApiResponse, UtcDatetime
from .faculty import FeedbackLine

SESSION_ID = "7c9e6679-7425-40de-944b-e07fc1f90ae7"
TOKEN = "st_Zk3vQ0m1pWw8s2dYb7nX4cL9tRfJ6aHeUoGiVyMq5NA"


class JoinRequest(ApiRequest):
    """Student login. The access code is required (D10); the server can be run with require_access_code=false for local dev."""
    viva_id: str
    student_id: str = Field(min_length=1, max_length=40)
    access_code: Optional[str] = Field(None, description="One-time code from faculty, e.g. K7M2-9QXP. "
                                                         "Required unless the server runs with require_access_code=false.")
    model_config = ConfigDict(json_schema_extra={"examples": [
        {"viva_id": "dsa-midterm-2026", "student_id": "S2024001", "access_code": "K7M2-9QXP"}]})


class JoinResponse(ApiResponse):
    """Login result. Keep `session_token` and send it as `Authorization: Bearer` on every student call."""
    session_id: UUID
    session_token: str = Field(description="Opaque, starts with st_. Rejoining issues a new one and kills this one.")
    status: SessionStatus
    resumed: bool = Field(description="True when this is a rejoin of a session that already existed.")
    viva_title: str
    duration_ms: int = Field(description="Hard limit of the viva, 900000.")
    rules_text: str = Field(description="Show this before asking for consent.")
    rules_version: str = Field(description="Send this back with the consent.")
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "session_id": SESSION_ID, "session_token": TOKEN, "status": "created", "resumed": False,
        "viva_title": "DSA mid-term viva", "duration_ms": 900000,
        "rules_text": "This is a 15-minute recorded viva. Everyone gets the same structure. The audio and transcript are "
                      "kept for faculty review. Do not use notes or other people.",
        "rules_version": "rules-v1"}]})


class ConsentRequest(ApiRequest):
    """Accept (or not) the rules and recording."""
    accepted: bool
    rules_version: str = Field(description="The rules_version the student actually saw.")
    model_config = ConfigDict(json_schema_extra={"examples": [{"accepted": True, "rules_version": "rules-v1"}]})


class ConsentResponse(ApiResponse):
    """accepted=true moves created -> consented. accepted=false changes nothing (status stays created, no recording)."""
    status: SessionStatus
    consent_at: Optional[UtcDatetime] = Field(None, description="Null if the student declined.")
    model_config = ConfigDict(json_schema_extra={"examples": [{"status": "consented", "consent_at": "2026-10-12T05:29:40Z"}]})


class AiTurn(ApiResponse):
    """What the AI says next. `idx` is the spoken-turn index, the same numbering the faculty transcript uses."""
    idx: int
    text: str
    phase: str = Field(description="warmup, fundamentals, depth, applied, wrapup or scoring.")
    ended: bool = Field(description="True on the closing turn: the viva is over, stop sending answers.")
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "idx": 2, "text": "Can you explain how a hash table works?", "phase": "fundamentals", "ended": False}]})


class StartResponse(ApiResponse):
    """The clock has started on the server. Show a countdown from remaining_ms and re-sync from server_now."""
    status: SessionStatus
    started_at: UtcDatetime
    deadline_at: UtcDatetime
    server_now: UtcDatetime
    remaining_ms: int
    turn: AiTurn
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "status": "in_progress", "started_at": "2026-10-12T05:30:12Z", "deadline_at": "2026-10-12T05:45:12Z",
        "server_now": "2026-10-12T05:30:12Z", "remaining_ms": 900000,
        "turn": {"idx": 0, "text": "Hi, welcome. This is a 15-minute recorded viva. To start: tell me about a project you built.",
                 "phase": "warmup", "ended": False}}]})


class AnswerRequest(ApiRequest):
    """One student answer. In voice mode the server fills this from STT instead."""
    text: str = Field(min_length=1, max_length=4000)
    client_seq: int = Field(ge=1, description="1 for the first answer, then +1 each. Resend the same value to retry safely.")
    t_start_ms: Optional[int] = Field(None, ge=0, description="Offset into the recording when the answer started.")
    t_end_ms: Optional[int] = Field(None, ge=0)
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "text": "A hash function maps the key to an index, and collisions use chaining.",
        "client_seq": 2, "t_start_ms": 41200, "t_end_ms": 52800}]})


class AnswerResponse(ApiResponse):
    """The AI's next turn. Replaying a client_seq returns the identical response with replayed=true."""
    client_seq: int
    replayed: bool
    status: SessionStatus
    turn: AiTurn
    server_now: UtcDatetime
    remaining_ms: int
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "client_seq": 2, "replayed": False, "status": "in_progress",
        "turn": {"idx": 4, "text": "What happens as the table fills up?", "phase": "fundamentals", "ended": False},
        "server_now": "2026-10-12T05:31:05Z", "remaining_ms": 847000}]})


class StatusResponse(ApiResponse):
    """Poll this for the timer, and call it after a reload or rejoin to resume where the student was."""
    status: SessionStatus
    phase: Optional[str] = None
    server_now: UtcDatetime
    started_at: Optional[UtcDatetime] = None
    deadline_at: Optional[UtcDatetime] = None
    remaining_ms: Optional[int] = Field(None, description="Null before start. 0 once the deadline has passed.")
    last_client_seq: int = Field(description="Highest client_seq the server has accepted; 0 if none.")
    current_turn: Optional[AiTurn] = Field(None, description="The latest AI turn, so a reload can show the open question.")
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "status": "in_progress", "phase": "fundamentals", "server_now": "2026-10-12T05:31:05Z",
        "started_at": "2026-10-12T05:30:12Z", "deadline_at": "2026-10-12T05:45:12Z", "remaining_ms": 847000,
        "last_client_seq": 2,
        "current_turn": {"idx": 4, "text": "What happens as the table fills up?", "phase": "fundamentals", "ended": False}}]})


class StudentDimension(ApiResponse):
    """One rubric dimension in the student's result."""
    key: str
    weight: int
    score: float = Field(description="0-5.")
    model_config = ConfigDict(json_schema_extra={"examples": [{"key": "conceptual", "weight": 30, "score": 4}]})


class StudentResult(ApiResponse):
    """The student's own result. Only available when faculty released results for the viva."""
    total: float = Field(description="Final mark out of 100: the faculty override if there is one, else the AI mark.")
    overridden: bool = Field(description="True when faculty changed the mark; dimension scores are then the AI's.")
    dimensions: list[StudentDimension]
    feedback: list[FeedbackLine] = Field(description="3-5 lines.")
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "total": 78.0, "overridden": True,
        "dimensions": [{"key": "conceptual", "weight": 30, "score": 4}, {"key": "depth", "weight": 25, "score": 3},
                       {"key": "problem", "weight": 20, "score": 3}, {"key": "practical", "weight": 15, "score": 4},
                       {"key": "communication", "weight": 10, "score": 4}],
        "feedback": [{"text": "Good grasp of collision handling; add load-factor and resizing next time.", "evidence": [3]},
                     {"text": "Say why you chose a design, not just what it is.", "evidence": [5]},
                     {"text": "Isolate the database before blaming the network when debugging slow APIs.", "evidence": [7]}]}]})
