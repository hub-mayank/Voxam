from fastapi import Depends, Request

from ..services.faculty import FacultyService
from ..services.student import StudentService
from ..services.stubs import StubFaculty, StubStudent


class ReleaseAfterCall:
    """Rolls the session back when a service call returns, so its connection goes back to the pool before the response is built.
    Without it a request keeps its connection until the dependency is torn down, which happens after FastAPI has validated the
    response in a worker thread. With 150 simultaneous joins every one of the 40 workers was waiting for a connection and the
    connections were held by requests waiting for a worker: nothing moved until pool_timeout (found by the T7 load test).
    Service methods return plain values, so nothing reads the session afterwards."""

    def __init__(self, ops, db):
        self.ops = ops
        self.db = db

    def __getattr__(self, name):
        method = getattr(self.ops, name)
        if not callable(method):
            return method

        def call(*args, **kwargs):
            try:
                return method(*args, **kwargs)
            finally:
                self.db.rollback()
        return call


async def get_db(request: Request):
    """One database session per request (none in contract-stub mode). `async` so the session is closed on the event loop and
    never has to wait for a worker thread."""
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
    if state.settings.contract_stub:
        return StubFaculty()
    return ReleaseAfterCall(FacultyService(db, state.settings, state.now), db)


def student_ops(request: Request, db=Depends(get_db)):
    state = request.app.state
    if state.settings.contract_stub:
        return StubStudent(state.settings)
    service = StudentService(db, state.settings, state.now, state.llm_factory, ip_throttle=state.ip_throttle)
    return ReleaseAfterCall(service, db)
