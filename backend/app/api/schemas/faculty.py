from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator

from ...session_state import SessionStatus
from .common import ApiRequest, ApiResponse, UtcDatetime

VIVA_ID = r"^[a-z0-9][a-z0-9-]{2,62}$"
SESSION_ID = "7c9e6679-7425-40de-944b-e07fc1f90ae7"


class Difficulty(str, Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class QuestionType(str, Enum):
    concept = "concept"
    applied = "applied"


class QuestionSource(str, Enum):
    bank = "bank"
    ai_draft = "ai-draft"


# ---------- vivas ----------

class VivaCreate(ApiRequest):
    """Create a viva. Phase timings and rubric weights are fixed by the platform (spec-bound), so they are not inputs."""
    viva_id: Optional[str] = Field(None, pattern=VIVA_ID, description="URL-safe slug. Omit to let the server generate one.")
    title: str = Field(min_length=1, max_length=120, description="Shown to faculty and on the student rules page.")
    subject: str = Field(min_length=1, max_length=120)
    topics: list[str] = Field(min_length=1, description="Topics the bank covers.")
    difficulty: Difficulty
    results_visible_to_students: bool = Field(False, description="Whether students may fetch their result "
                                                                 "(GET /student/sessions/{sid}/result). Change later with PATCH.")
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "viva_id": "dsa-midterm-2026", "title": "DSA mid-term viva", "subject": "Data Structures and Algorithms",
        "topics": ["hash-tables", "complexity", "databases"], "difficulty": "medium",
        "results_visible_to_students": False}]})


class VivaUpdate(ApiRequest):
    """Change a viva after creation. Only the fields you send change."""
    results_visible_to_students: Optional[bool] = Field(None, description="Release (true) or hide (false) student results.")
    model_config = ConfigDict(json_schema_extra={"examples": [{"results_visible_to_students": True}]})


class PhaseInfo(ApiResponse):
    """One phase of the viva clock, in milliseconds from the session start."""
    name: str = Field(description="warmup, fundamentals, depth, applied, wrapup or scoring.")
    start_ms: int
    end_ms: int
    max_followups: int
    model_config = ConfigDict(json_schema_extra={"examples": [
        {"name": "fundamentals", "start_ms": 60000, "end_ms": 300000, "max_followups": 1}]})


class RubricDimension(ApiResponse):
    """A scored dimension. Weights sum to 100; total = sum(weight * score / 5)."""
    key: str
    weight: int
    five_means: str = Field(description="What a 5/5 looks like.")
    model_config = ConfigDict(json_schema_extra={"examples": [
        {"key": "conceptual", "weight": 30, "five_means": "Explains core concepts correctly in own words"}]})


class VivaConfigView(ApiResponse):
    """Read-only view of the viva structure the engine runs."""
    duration_ms: int = Field(description="Hard limit, 900000 (15 min).")
    answer_cap_ms: int = Field(description="Longest single answer, 90000.")
    prompt_version: str
    rubric_version: str
    phases: list[PhaseInfo]
    rubric: list[RubricDimension]
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "duration_ms": 900000, "answer_cap_ms": 90000, "prompt_version": "interviewer-v1", "rubric_version": "rubric-v1",
        "phases": [{"name": "warmup", "start_ms": 0, "end_ms": 60000, "max_followups": 0},
                   {"name": "fundamentals", "start_ms": 60000, "end_ms": 300000, "max_followups": 1}],
        "rubric": [{"key": "conceptual", "weight": 30, "five_means": "Explains core concepts correctly in own words"},
                   {"key": "depth", "weight": 25, "five_means": "Handles follow-ups, explains trade-offs and why"}]}]})


class Viva(ApiResponse):
    """A viva as faculty see it."""
    id: str
    title: str
    subject: str
    topics: list[str]
    difficulty: Difficulty
    created_by: str = Field(description="Reviewer name of the faculty token that created it.")
    created_at: UtcDatetime
    rules_version: str = Field(description="Version of the rules text students must accept.")
    results_visible_to_students: bool
    config: VivaConfigView
    question_count: int
    roster_count: int
    session_counts: dict[str, int] = Field(description="Sessions per status (keys are session statuses).")
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "id": "dsa-midterm-2026", "title": "DSA mid-term viva", "subject": "Data Structures and Algorithms",
        "topics": ["hash-tables", "complexity", "databases"], "difficulty": "medium", "created_by": "dr-rao",
        "created_at": "2026-10-09T09:00:00Z", "rules_version": "rules-v1", "results_visible_to_students": False,
        "config": VivaConfigView.model_config["json_schema_extra"]["examples"][0],
        "question_count": 10, "roster_count": 3, "session_counts": {"scored": 1, "in_progress": 1, "created": 1}}]})


class VivaList(ApiResponse):
    """All vivas, newest first. Small enough that it is not paginated."""
    items: list[Viva]
    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [Viva.model_config["json_schema_extra"]["examples"][0]]}]})


# ---------- question bank ----------

class QuestionIn(ApiRequest):
    """One bank question as uploaded (JSON item, or one CSV row). `id` must be unique within the viva."""
    id: str = Field(min_length=1, max_length=40)
    topic: str = Field(min_length=1)
    type: QuestionType = Field(description="concept (fundamentals/depth phases) or applied (applied phase).")
    difficulty: int = Field(ge=1, le=5)
    text: str = Field(min_length=1, description="What the AI asks. Students see this.")
    key_points: list[str] = Field(default_factory=list, description="Private marking hints. Students never see these.")
    source: QuestionSource = Field(QuestionSource.bank, description="bank: reviewed by faculty. ai-draft: written by an AI; faculty must review "
                                                                    "and approve it before real use (re-upload it as bank once approved).")
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "id": "q001", "topic": "hash-tables", "type": "concept", "difficulty": 1,
        "text": "Can you explain how a hash table works?",
        "key_points": ["hash function maps key to index", "collision handling", "average O(1) lookup", "resizing/load factor"],
        "source": "bank"}]})


class Question(ApiResponse):
    """A stored bank question."""
    id: str
    topic: str
    type: QuestionType
    difficulty: int
    text: str
    key_points: list[str]
    source: str = Field(description="bank (reviewed by faculty), ai-draft (written by an AI, awaiting faculty approval) or generated (AI variant; not produced yet).")
    approved_by: Optional[str] = Field(None, description="Reviewer who approved the question (an ai-draft approved through POST .../questions/approve, "
                                                         "or a generated question); null for plain uploads.")
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "id": "q001", "topic": "hash-tables", "type": "concept", "difficulty": 1,
        "text": "Can you explain how a hash table works?",
        "key_points": ["hash function maps key to index", "collision handling", "average O(1) lookup", "resizing/load factor"],
        "source": "bank", "approved_by": None}]})


class ApproveQuestions(ApiRequest):
    """Approve AI-drafted questions. Each one becomes `source: bank` with `approved_by` set to the reviewer of the token."""
    question_ids: Optional[list[str]] = Field(None, min_length=1, description="Which questions to approve. Omit to approve every ai-draft in the bank. "
                                                                              "A question that is already `bank` is left alone.")
    model_config = ConfigDict(json_schema_extra={"examples": [{"question_ids": ["c01", "c02"]}]})


class GenerateQuestionsRequest(ApiRequest):
    """Generate review-only question drafts from instructor-provided syllabus text."""
    syllabus: str = Field(min_length=1, max_length=12000, description="Course outline or syllabus text; do not include student data.")
    count: int = Field(10, ge=1, le=20, description="Maximum number of draft questions to generate.")
    @field_validator("syllabus")
    @classmethod
    def syllabus_must_contain_text(cls, value):
        if not value.strip():
            raise ValueError("syllabus must contain non-whitespace text")
        return value.strip()
    model_config = ConfigDict(json_schema_extra={"examples": [{"syllabus": "Arrays, hashing, collision handling, complexity analysis", "count": 10}]})


class QuestionList(ApiResponse):
    """The viva's whole bank. Returned by GET, and by POST (the new bank after a successful upload)."""
    items: list[Question]
    concept_count: int
    applied_count: int
    warnings: list[str] = Field(description="Non-fatal advice, e.g. the bank is smaller than 7 concept / 3 applied.")
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "items": [Question.model_config["json_schema_extra"]["examples"][0]], "concept_count": 1, "applied_count": 0,
        "warnings": ["bank is small (concept=1, applied=0); aim for at least 7 concept and 3 applied"]}]})


# ---------- roster ----------

class IssuedEntry(ApiResponse):
    """One roster row after an upload. `access_code` is plaintext and appears only here, only once."""
    student_id: str
    name: Optional[str] = None
    outcome: str = Field(description="created (new student, code issued) or unchanged (already on the roster, no new code).")
    access_code: Optional[str] = Field(None, description="Plaintext one-time code. Null when unchanged or when "
                                                         "the server runs with require_access_code=false.")
    model_config = ConfigDict(json_schema_extra={"examples": [
        {"student_id": "S2024001", "name": "Asha Verma", "outcome": "created", "access_code": "K7M2-9QXP"}]})


class RosterUploadResult(ApiResponse):
    """Result of a roster upload. Store or print the codes now: they cannot be read again, only reset."""
    items: list[IssuedEntry]
    created: int
    unchanged: int
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "items": [IssuedEntry.model_config["json_schema_extra"]["examples"][0],
                  {"student_id": "S2024002", "name": "Ravi Iyer", "outcome": "unchanged", "access_code": None}],
        "created": 1, "unchanged": 1}]})


class RosterEntry(ApiResponse):
    """A roster row as listed later: never contains the code; access_code_active governs future joins only."""
    student_id: str
    name: Optional[str] = None
    session_id: Optional[UUID] = Field(None, description="Null until the student has joined.")
    session_status: Optional[SessionStatus] = None
    access_code_active: bool = Field(description="True if a code can currently start or rejoin a session. Revoking it does not end an existing session.")
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "student_id": "S2024001", "name": "Asha Verma", "session_id": SESSION_ID, "session_status": "scored",
        "access_code_active": True}]})


class RosterList(ApiResponse):
    """The viva's roster."""
    items: list[RosterEntry]
    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [
        RosterEntry.model_config["json_schema_extra"]["examples"][0],
        {"student_id": "S2024002", "name": "Ravi Iyer", "session_id": None, "session_status": None,
         "access_code_active": False}]}]})


class ResetCodeResult(ApiResponse):
    """A fresh access code. The previous code stops working immediately. Shown once."""
    student_id: str
    access_code: str
    issued_at: UtcDatetime
    model_config = ConfigDict(json_schema_extra={"examples": [
        {"student_id": "S2024002", "access_code": "H4TN-6WZB", "issued_at": "2026-10-12T04:55:00Z"}]})


# ---------- sessions ----------

class SessionSummary(ApiResponse):
    """One row of the session list."""
    session_id: UUID
    student_id: str
    student_name: Optional[str] = None
    status: SessionStatus
    started_at: Optional[UtcDatetime] = None
    ended_at: Optional[UtcDatetime] = None
    ai_total: Optional[float] = Field(None, description="Median of the scorer runs, 0-100. Null until scored.")
    effective_total: Optional[float] = Field(None, description="The latest override's new_total, else ai_total.")
    overridden: bool
    low_confidence: bool
    needs_review: bool = Field(description="low_confidence and neither a review (POST .../review) nor an override has been logged.")
    scoring_error: Optional[str] = Field(None, description="Only when status is failed: one plain sentence on why automatic marking did not finish. "
                                                         "Null otherwise. Technical detail stays in the worker log, not here.")
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "session_id": SESSION_ID, "student_id": "S2024001", "student_name": "Asha Verma", "status": "scored",
        "started_at": "2026-10-12T05:30:12Z", "ended_at": "2026-10-12T05:44:58Z", "ai_total": 71.0,
        "effective_total": 78.0, "overridden": True, "low_confidence": False, "needs_review": False, "scoring_error": None}]})


class SessionList(ApiResponse):
    """A page of sessions, newest first. Pass `next_cursor` back as `cursor` for the next page; null means the end."""
    items: list[SessionSummary]
    next_cursor: Optional[str] = None
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "items": [SessionSummary.model_config["json_schema_extra"]["examples"][0], {
            "session_id": "0b8f1d52-3c1e-4f55-9d4b-6a1f2c7e9a10", "student_id": "S2024003", "student_name": "Meera Nair",
            "status": "scored", "started_at": "2026-10-12T06:00:00Z", "ended_at": "2026-10-12T06:15:00Z",
            "ai_total": 34.0, "effective_total": 34.0, "overridden": False, "low_confidence": True, "needs_review": True, "scoring_error": None}],
        "next_cursor": None}]})


class Turn(ApiResponse):
    """One spoken turn. `idx` counts spoken turns from 0 and is the number scoring evidence refers to."""
    idx: int
    role: str = Field(description="ai or student.")
    text: str
    t_start_ms: Optional[int] = Field(None, description="Offset into the audio recording. Null in text mode.")
    t_end_ms: Optional[int] = None
    phase: str
    question_id: Optional[str] = None
    action: Optional[str] = Field(None, description="Why the AI said this (ask, followup, hint, move_on, redirect, close...). AI turns only.")
    quality: Optional[str] = Field(None, description="Interviewer's live classification of a student answer: strong, partial, none, offtopic.")
    model: Optional[str] = Field(None, description="AI turns: the model that served the call(s) behind this turn (visible fallbacks). "
                                                   "Null for canned turns (opener, closing, bank questions) and student turns.")
    prompt_version: Optional[str] = Field(None, description="AI turns: interviewer prompt version in force. Null for student turns.")
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "idx": 3, "role": "student", "text": "A hash function maps the key to an index, and collisions use chaining.",
        "t_start_ms": 41200, "t_end_ms": 52800, "phase": "fundamentals", "question_id": "q001",
        "action": None, "quality": "partial", "model": None, "prompt_version": None}]})


class RunScore(ApiResponse):
    """One scorer run (there are 3 per session)."""
    run: int
    total: float
    dimension_scores: dict[str, int] = Field(description="Dimension key to 0-5.")
    model_config = ConfigDict(json_schema_extra={"examples": [
        {"run": 1, "total": 71.0, "dimension_scores": {"conceptual": 4, "depth": 3, "problem": 3, "practical": 4, "communication": 4}}]})


class DimensionResult(ApiResponse):
    """Final result for one rubric dimension: the median over runs, the reason and the transcript evidence."""
    key: str
    weight: int
    score: float = Field(description="Median 0-5 over the runs.")
    score_min: int
    score_max: int
    reason: str
    evidence: list[int] = Field(description="Turn idx values (student turns) that justify the score; seek the audio to their t_start_ms.")
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "key": "conceptual", "weight": 30, "score": 4, "score_min": 4, "score_max": 4,
        "reason": "Explains hashing and collision handling correctly in own words.", "evidence": [1, 3]}]})


class FeedbackLine(ApiResponse):
    """One feedback line for the student, tied to transcript evidence."""
    text: str
    evidence: list[int]
    model_config = ConfigDict(json_schema_extra={"examples": [
        {"text": "Good grasp of collision handling; add load-factor and resizing next time.", "evidence": [3]}]})


class Scoring(ApiResponse):
    """The AI score: per-run results plus the median that becomes `ai_total`."""
    rubric_version: str
    prompt_version: str
    model: str
    runs: list[RunScore]
    median_total: float = Field(description="Total of the median dimension scores: sum(weight * score / 5), 0-100.")
    total_spread: float = Field(description="Max run total minus min run total.")
    dimensions: list[DimensionResult]
    feedback: list[FeedbackLine] = Field(description="3-5 lines.")
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "rubric_version": "rubric-v1", "prompt_version": "scorer-v1", "model": "gemini-3.5-flash",
        "runs": [{"run": 1, "total": 71.0, "dimension_scores": {"conceptual": 4, "depth": 3, "problem": 3, "practical": 4, "communication": 4}},
                 {"run": 2, "total": 68.0, "dimension_scores": {"conceptual": 4, "depth": 3, "problem": 3, "practical": 3, "communication": 4}},
                 {"run": 3, "total": 71.0, "dimension_scores": {"conceptual": 4, "depth": 3, "problem": 3, "practical": 4, "communication": 4}}],
        "median_total": 71.0, "total_spread": 3.0,
        "dimensions": [
            {"key": "conceptual", "weight": 30, "score": 4, "score_min": 4, "score_max": 4,
             "reason": "Explains hashing and collision handling correctly in own words.", "evidence": [1, 3]},
            {"key": "depth", "weight": 25, "score": 3, "score_min": 3, "score_max": 3,
             "reason": "Handles one follow-up, but trade-offs stay shallow.", "evidence": [5]},
            {"key": "problem", "weight": 20, "score": 3, "score_min": 3, "score_max": 3,
             "reason": "Breaks the slow-API problem into steps but skips isolating the database.", "evidence": [7]},
            {"key": "practical", "weight": 15, "score": 4, "score_min": 3, "score_max": 4,
             "reason": "Describes the chat project concretely.", "evidence": [1]},
            {"key": "communication", "weight": 10, "score": 4, "score_min": 4, "score_max": 4,
             "reason": "Clear and structured answers.", "evidence": [3, 5]}],
        "feedback": [
            {"text": "Good grasp of collision handling; add load-factor and resizing next time.", "evidence": [3]},
            {"text": "Say why you chose a design, not just what it is.", "evidence": [5]},
            {"text": "Isolate the database before blaming the network when debugging slow APIs.", "evidence": [7]}]}]})


class AudioRef(ApiResponse):
    """Where to get the recording. Use `url` as the <audio> source: it is signed, expires, and needs no header."""
    available: bool
    url: Optional[str] = Field(None, description="Path with ?exp=<unix seconds>&sig=<hex>. Valid for expires_at - now. "
                                                 "Request GET /faculty/sessions/{sid} again for a fresh one.")
    content_type: Optional[str] = None
    duration_ms: Optional[int] = None
    size_bytes: Optional[int] = None
    expires_at: Optional[UtcDatetime] = None
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "available": True, "url": f"/faculty/sessions/{SESSION_ID}/audio?exp=1791784800&sig=9f2c1ab77e0d4c35",
        "content_type": "audio/wav", "duration_ms": 886000, "size_bytes": 28352044, "expires_at": "2026-10-12T06:00:00Z"}]})


class OverrideEntry(ApiResponse):
    """One logged override. The reviewer comes from the token, never from the request."""
    id: int
    reviewer: str
    old_total: Optional[float] = Field(None, description="The effective total just before this override; null if there was none.")
    new_total: float
    reason: str
    at: UtcDatetime
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "id": 1, "reviewer": "dr-rao", "old_total": 71.0, "new_total": 78.0,
        "reason": "Student's project explanation was stronger than the transcript shows.", "at": "2026-10-13T08:20:00Z"}]})


class IntegrityEvent(ApiResponse):
    """A recorded integrity signal: something to look at, never a verdict, and never part of the mark."""
    id: int
    kind: str = Field(description="tab_hidden, window_blur, paste or copy (sent by the student page); other kinds may be added later.")
    t_ms: int
    detail: dict = Field(default_factory=dict)
    model_config = ConfigDict(json_schema_extra={"examples": [
        {"id": 1, "kind": "tab_hidden", "t_ms": 312000, "detail": {"duration_ms": 9200, "client_id": "b1f4c0de"}}]})


class ReviewRequest(ApiRequest):
    """Mark a low-confidence (or any) result as reviewed, without changing the mark."""
    note: str = Field(min_length=3, max_length=2000, description="What was checked.")
    model_config = ConfigDict(json_schema_extra={"examples": [{"note": "Listened to the audio; the AI mark is fair."}]})


class ReviewEntry(ApiResponse):
    """One logged review. The reviewer comes from the token."""
    id: int
    reviewer: str
    note: str
    at: UtcDatetime
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "id": 1, "reviewer": "dr-iyer", "note": "Listened to the audio; the AI mark is fair.", "at": "2026-10-13T08:10:00Z"}]})


class ReviewResult(ApiResponse):
    """The logged review and the session's resulting review flag."""
    review: ReviewEntry
    needs_review: bool
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "review": ReviewEntry.model_config["json_schema_extra"]["examples"][0], "needs_review": False}]})


class RescoreResult(ApiResponse):
    """A scoring job was queued for the session (the worker picks it up)."""
    session_id: UUID
    status: SessionStatus
    job_status: str = Field(description="queued.")
    model_config = ConfigDict(json_schema_extra={"examples": [{"session_id": SESSION_ID, "status": "ended", "job_status": "queued"}]})


class SessionDetail(ApiResponse):
    """Everything needed to audit one viva: transcript, audio, scores with evidence, overrides, integrity."""
    session_id: UUID
    viva_id: str
    student_id: str
    student_name: Optional[str] = None
    status: SessionStatus
    rules_version: Optional[str] = None
    consent_at: Optional[UtcDatetime] = None
    started_at: Optional[UtcDatetime] = None
    ended_at: Optional[UtcDatetime] = None
    deadline_at: Optional[UtcDatetime] = None
    turns: list[Turn]
    scoring: Optional[Scoring] = Field(None, description="Null until scored.")
    scoring_error: Optional[str] = Field(None, description="Only when status is failed: one plain sentence on why automatic marking did not finish. "
                                                         "Null otherwise. Technical detail stays in the worker log, not here.")
    low_confidence: bool
    low_confidence_reasons: list[str]
    needs_review: bool = Field(description="low_confidence and neither a review nor an override has been logged.")
    effective_total: Optional[float] = Field(None, description="Latest override's new_total, else scoring.median_total, else null.")
    effective_source: Optional[str] = Field(None, description="override, ai or null.")
    audio: AudioRef
    overrides: list[OverrideEntry] = Field(description="Oldest first. The last one wins.")
    reviews: list[ReviewEntry] = Field(description="Oldest first.")
    integrity_events: list[IntegrityEvent]
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "session_id": SESSION_ID, "viva_id": "dsa-midterm-2026", "student_id": "S2024001", "student_name": "Asha Verma",
        "status": "scored", "rules_version": "rules-v1", "consent_at": "2026-10-12T05:29:40Z",
        "started_at": "2026-10-12T05:30:12Z", "ended_at": "2026-10-12T05:44:58Z", "deadline_at": "2026-10-12T05:45:12Z",
        "turns": [
            {"idx": 0, "role": "ai", "text": "Hi, welcome. To start: tell me about a project you built.",
             "t_start_ms": 500, "t_end_ms": 6200, "phase": "warmup", "question_id": "opener", "action": "open", "quality": None, "model": None, "prompt_version": "interviewer-v1"},
            {"idx": 1, "role": "student", "text": "I built a chat app with websockets and a Postgres backend.",
             "t_start_ms": 7400, "t_end_ms": 15100, "phase": "warmup", "question_id": "opener", "action": None, "quality": "strong", "model": None, "prompt_version": None},
            {"idx": 2, "role": "ai", "text": "Can you explain how a hash table works?",
             "t_start_ms": 16000, "t_end_ms": 19800, "phase": "fundamentals", "question_id": "q001", "action": "new_question", "quality": None, "model": None, "prompt_version": "interviewer-v1"},
            {"idx": 3, "role": "student", "text": "A hash function maps the key to an index, and collisions use chaining.",
             "t_start_ms": 41200, "t_end_ms": 52800, "phase": "fundamentals", "question_id": "q001", "action": None, "quality": "partial", "model": None, "prompt_version": None},
            {"idx": 4, "role": "ai", "text": "What happens as the table fills up?",
             "t_start_ms": 53600, "t_end_ms": 56000, "phase": "fundamentals", "question_id": "q001", "action": "hint", "quality": None, "model": "gemini-3.5-flash", "prompt_version": "interviewer-v1"},
            {"idx": 5, "role": "student", "text": "It resizes, so lookups stay constant on average. I would pick chaining for simplicity.",
             "t_start_ms": 60100, "t_end_ms": 71000, "phase": "fundamentals", "question_id": "q001", "action": None, "quality": "strong", "model": None, "prompt_version": None},
            {"idx": 6, "role": "ai", "text": "Your API was fast yesterday and slow today. How do you find the cause?",
             "t_start_ms": 640000, "t_end_ms": 646000, "phase": "applied", "question_id": "q101", "action": "new_question", "quality": None, "model": None, "prompt_version": "interviewer-v1"},
            {"idx": 7, "role": "student", "text": "I would check recent deploys, then logs and metrics, then reproduce the slow request.",
             "t_start_ms": 650000, "t_end_ms": 690000, "phase": "applied", "question_id": "q101", "action": None, "quality": "partial", "model": None, "prompt_version": None}],
        "scoring": Scoring.model_config["json_schema_extra"]["examples"][0],
        "scoring_error": None,
        "low_confidence": False, "low_confidence_reasons": [], "needs_review": False,
        "effective_total": 78.0, "effective_source": "override",
        "audio": AudioRef.model_config["json_schema_extra"]["examples"][0],
        "overrides": [OverrideEntry.model_config["json_schema_extra"]["examples"][0]],
        "reviews": [ReviewEntry.model_config["json_schema_extra"]["examples"][0]],
        "integrity_events": []}]})


class OverrideRequest(ApiRequest):
    """Override the mark. Always allowed on a scored (or failed) session; always logged; the latest one wins."""
    new_total: float = Field(ge=0, le=100, description="New mark out of 100.")
    reason: str = Field(min_length=3, max_length=2000, description="Why. Required, shown in the history.")
    model_config = ConfigDict(json_schema_extra={"examples": [
        {"new_total": 78.0, "reason": "Student's project explanation was stronger than the transcript shows."}]})


class OverrideResult(ApiResponse):
    """The logged override and the resulting effective total."""
    override: OverrideEntry
    effective_total: float
    model_config = ConfigDict(json_schema_extra={"examples": [
        {"override": OverrideEntry.model_config["json_schema_extra"]["examples"][0], "effective_total": 78.0}]})
