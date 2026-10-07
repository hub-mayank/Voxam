import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import routes_faculty, routes_student
from .errors import install_error_handlers, uniform_validation_errors
from .schemas.common import Health, example_of
from .settings import Settings

DESCRIPTION = """
Backend for AI Viva: a fair, auditable 15-minute viva. Faculty set up vivas and review results; students take the viva.

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


def create_app(settings: Settings = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(title="AI Viva API", version="1.0.0", description=DESCRIPTION, openapi_tags=TAGS,
                  generate_unique_id_function=lambda route: route.name)
    app.state.settings = settings
    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["*"],
                           allow_headers=["*"], expose_headers=["X-Contract-Stub", "Content-Range", "Accept-Ranges"])
    install_error_handlers(app)
    app.include_router(routes_faculty.router)
    app.include_router(routes_faculty.audio_router)
    app.include_router(routes_student.join_router)
    app.include_router(routes_student.router)

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


app = create_app()


def openapi_json(api: FastAPI) -> str:
    """The frozen contract file: stable key order, trailing newline."""
    return json.dumps(api.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
