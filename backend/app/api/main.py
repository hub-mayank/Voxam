import json
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import sessionmaker

from ..db.engine import init_db, make_engine
from ..envfile import load_env
from ..llm.factory import make_llm
from ..services.throttle import SlidingWindow
from . import routes_faculty, routes_student, routes_voice
from .errors import install_error_handlers, uniform_validation_errors
from .schemas.common import Health, example_of
from .settings import Settings

DESCRIPTION = """
Backend for Voxam: a fair, auditable 15-minute viva. Faculty set up vivas and review results; students take the viva.

**Contract status:** during the contract phase every route marked as a stub returns its example payload with the header
`X-Contract-Stub: 1`, so `uvicorn` is a working mock backend. Send `X-Mock-Error: <code>` to any stub route to get that error.

**Conventions.** Errors always look like `{"error": {"code", "message", "details"}}` with a code from a fixed list.
Timestamps are ISO-8601 UTC ending in `Z`. Durations are integer milliseconds (`*_ms`). Faculty send
`Authorization: Bearer <faculty token>`; students send `Authorization: Bearer <session token>` (starts with `st_`).
Wrong role gives 403, missing or unknown token gives 401.

**Voice (TBD, task T4):** a WebSocket for live audio is reserved (planned `/student/sessions/{sid}/voice`) but is not
part of this contract and not implemented. The text endpoints below are the contract; voice will reuse the same
session, token, timer and turn numbering.
"""

TAGS = [
    {"name": "faculty", "description": "Faculty dashboard. Bearer faculty token."},
    {"name": "student", "description": "Student login and viva. Bearer session token (except join)."},
    {"name": "meta", "description": "Health."},
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_app(settings: Settings = None, llm_factory=None, now=None, engine=None) -> FastAPI:
    """llm_factory(spec) -> an LLM for one request; now() -> aware UTC time. Both are injectable for tests and the demo seed."""
    if settings is None:
        load_env()  # the repo .env fills in what the shell did not set
        settings = Settings.from_env()
    settings.check()
    app = FastAPI(title="Voxam API", version="1.0.0", description=DESCRIPTION, openapi_tags=TAGS,
                  generate_unique_id_function=lambda route: route.name)
    app.state.settings = settings
    app.state.now = now or utc_now
    app.state.llm_factory = llm_factory or make_llm
    if not settings.contract_stub:
        app.state.engine = engine or make_engine(settings.database_url or None)
        init_db(app.state.engine)
        app.state.sessionmaker = sessionmaker(app.state.engine)
        app.state.ip_throttle = SlidingWindow(settings.ip_failures_per_minute)
    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["*"],
                           allow_headers=["*"], expose_headers=["X-Contract-Stub", "Content-Range", "Accept-Ranges"])
    install_error_handlers(app)
    app.include_router(routes_faculty.router)
    app.include_router(routes_faculty.audio_router)
    app.include_router(routes_student.join_router)
    app.include_router(routes_student.router)
    app.include_router(routes_voice.router)

    default_openapi = app.openapi

    def openapi():
        if app.openapi_schema is None:
            uniform_validation_errors(default_openapi())
        return app.openapi_schema

    app.openapi = openapi

    @app.get("/health", response_model=Health, tags=["meta"], summary="Liveness check")
    def health():
        return example_of(Health)

    return app


_app = None


def __getattr__(name):
    """`uvicorn app.api.main:app` builds the app on first use, so importing this module needs no environment."""
    global _app
    if name == "app":
        _app = _app or create_app()
        return _app
    raise AttributeError(name)


def openapi_json(api: FastAPI) -> str:
    """The frozen contract file: stable key order, trailing newline."""
    return json.dumps(api.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
