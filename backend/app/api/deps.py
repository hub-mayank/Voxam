from fastapi import Depends, Request

from ..services.faculty import FacultyService
from ..services.student import StudentService
from ..services.stubs import StubFaculty, StubStudent


def get_db(request: Request):
    """One database session per request (none in contract-stub mode)."""
    factory = getattr(request.app.state, "sessionmaker", None)
    if factory is None:
        yield None
        return
    db = factory()
    try:
        yield db
    finally:
        db.close()


def faculty_ops(request: Request, db=Depends(get_db)):
    state = request.app.state
    return StubFaculty() if state.settings.contract_stub else FacultyService(db, state.settings, state.now)


def student_ops(request: Request, db=Depends(get_db)):
    state = request.app.state
    if state.settings.contract_stub:
        return StubStudent(state.settings)
    return StudentService(db, state.settings, state.now, state.llm_factory)
