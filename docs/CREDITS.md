# Credits

Every tool, library and model used. Add a line before adding a dependency.

| Name | Used for | License / terms | Source |
|---|---|---|---|
| Google Gemini API (`gemini-3.5-flash`) | LLM: answer classification, reply phrasing, scoring | Google Gemini API terms of service | https://ai.google.dev |
| httpx | HTTP client for the Gemini adapter | BSD-3-Clause | https://www.python-httpx.org |
| pytest | test runner | MIT | https://pytest.org |
| Python | language runtime | PSF License | https://www.python.org |
| Ollama (optional, local dev only; no model chosen yet) | local LLM server behind the Ollama adapter | MIT (server); each model has its own license | https://ollama.com |
| FastAPI | HTTP API framework and OpenAPI generation (pulls in Starlette, BSD-3-Clause) | MIT | https://fastapi.tiangolo.com |
| Uvicorn | ASGI server for the API | BSD-3-Clause | https://www.uvicorn.org |
| Pydantic v2 | API request/response schemas | MIT | https://docs.pydantic.dev |
| SQLAlchemy 2.x | database models (SQLite dev, PostgreSQL target) | MIT | https://www.sqlalchemy.org |
| python-multipart | multipart form parsing for CSV/JSON uploads | Apache-2.0 | https://github.com/Kludex/python-multipart |
