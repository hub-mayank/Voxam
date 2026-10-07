"""Contract-stub services (CONTRACT_STUB=1): same methods as the real ones, but every answer is the schema's example.
This is the mock backend for the frontend."""
from dataclasses import dataclass
from typing import Callable

from ..api.errors import ApiError, ErrorCode
from ..api.schemas.common import example_of
from ..api.schemas.faculty import (OverrideResult, QuestionList, RescoreResult, ResetCodeResult, ReviewResult, RosterList,
                                   RosterUploadResult, SessionDetail, SessionList, Viva, VivaList)
from ..api.schemas.student import (AnswerResponse, ConsentResponse, JoinResponse, StartResponse, StatusResponse, StudentResult)
from ..api.stub import silent_wav

CSV_EXAMPLE = ("student_id,name,status,ai_total,effective_total,overridden,low_confidence,needs_review,"
               "conceptual,depth,problem,practical,communication,last_reviewer\n"
               "S2024001,Asha Verma,scored,71.0,78.0,true,false,false,4,3,3,4,4,dr-rao\n")


@dataclass
class AudioSource:
    size: int
    content_type: str
    read: Callable[[int, int], bytes]  # inclusive byte range


def file_source(path, content_type) -> AudioSource:
    def read(start, end):
        with open(path, "rb") as f:
            f.seek(start)
            return f.read(end - start + 1)
    return AudioSource(path.stat().st_size, content_type, read)


class StubFaculty:
    def create_viva(self, body, faculty): return example_of(Viva)
    def list_vivas(self): return example_of(VivaList)
    def get_viva(self, viva_id): return example_of(Viva)
    def update_viva(self, viva_id, body): return example_of(Viva)
    def upload_questions(self, viva_id, filename, data): return example_of(QuestionList)
    def list_questions(self, viva_id): return example_of(QuestionList)
    def upload_roster(self, viva_id, filename, data): return example_of(RosterUploadResult)
    def list_roster(self, viva_id): return example_of(RosterList)
    def reset_code(self, viva_id, student_id): return example_of(ResetCodeResult)
    def list_sessions(self, viva_id, status, low_confidence, search, limit, cursor): return example_of(SessionList)
    def get_session(self, sid): return example_of(SessionDetail)
    def rescore_session(self, sid): return example_of(RescoreResult)
    def export_csv(self, viva_id): return CSV_EXAMPLE

    def override_session(self, sid, body, faculty):
        result = example_of(OverrideResult)
        result.override.reviewer = faculty.reviewer  # identity comes from the token
        return result

    def review_session(self, sid, body, faculty):
        result = example_of(ReviewResult)
        result.review.reviewer = faculty.reviewer
        return result

    def audio(self, sid):
        data = silent_wav()
        return AudioSource(len(data), "audio/wav", lambda a, b: data[a:b + 1])


class StubStudent:
    def __init__(self, settings):
        self.settings = settings

    def join(self, body):
        if self.settings.require_access_code and not body.access_code:
            raise ApiError(ErrorCode.validation_error, "access_code is required.",
                           {"fields": [{"loc": ["body", "access_code"], "message": "Field required"}]})
        return example_of(JoinResponse)

    def consent(self, sid, body): return example_of(ConsentResponse)
    def start(self, sid): return example_of(StartResponse)
    def answer(self, sid, body): return example_of(AnswerResponse)
    def status(self, sid): return example_of(StatusResponse)
    def result(self, sid): return example_of(StudentResult)
