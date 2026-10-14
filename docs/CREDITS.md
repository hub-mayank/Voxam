# Credits

Every tool, library and model used. Add a line before adding a dependency.

| Name | Used for | License / terms | Source |
|---|---|---|---|
| Google Gemini API (`gemini-3.5-flash`) | LLM: answer classification, reply phrasing, scoring | Google Gemini API terms of service | https://ai.google.dev |
| httpx | HTTP client for the Gemini adapter | BSD-3-Clause | https://www.python-httpx.org |
| pytest | test runner | MIT | https://pytest.org |
| Python | language runtime | PSF License | https://www.python.org |
| Ollama (local LLM server behind the Ollama adapter; model `llama3.2:3b`, see below) | local LLM server | MIT (server); each model has its own license | https://ollama.com |
| FastAPI | HTTP API framework and OpenAPI generation (pulls in Starlette, BSD-3-Clause) | MIT | https://fastapi.tiangolo.com |
| Uvicorn | ASGI server for the API | BSD-3-Clause | https://www.uvicorn.org |
| Pydantic v2 | API request/response schemas | MIT | https://docs.pydantic.dev |
| SQLAlchemy 2.x | database models (SQLite dev, PostgreSQL target) | MIT | https://www.sqlalchemy.org |
| python-multipart | multipart form parsing for CSV/JSON uploads | Apache-2.0 | https://github.com/Kludex/python-multipart |
| psycopg 3 (+ psycopg-binary) | PostgreSQL driver for SQLAlchemy | LGPL-3.0-only; used unmodified as a library, not copied or modified (D17) | https://www.psycopg.org |
| PostgreSQL 16 (Homebrew) | development and test database (D17) | PostgreSQL License | https://www.postgresql.org |
| whisper.cpp (`whisper-cli`, Homebrew `whisper-cpp` 1.9.5) with `ggml-base-q5_1` and `ggml-small-q5_1` models (ggerganov/whisper.cpp on Hugging Face) | default local STT on Apple Metal (D19) | MIT | https://github.com/ggml-org/whisper.cpp |
| faster-whisper 1.2.1 | local STT on CPU (CTranslate2, int8): fallback and spike baseline | MIT | https://github.com/SYSTRAN/faster-whisper |
| CTranslate2 4.8.2 | inference engine under faster-whisper | MIT | https://github.com/OpenNMT/CTranslate2 |
| OpenAI Whisper weights (base, small, medium; Systran CTranslate2 conversions) | STT models | MIT (Whisper); conversions on Hugging Face `Systran/faster-whisper-*` | https://huggingface.co/Systran |
| Groq API: `openai/gpt-oss-20b`, `whisper-large-v3-turbo` | live interview LLM (D19) and optional online STT, free tier only | Groq terms of service; gpt-oss weights are Apache-2.0; terms not re-read | https://console.groq.com |
| Ollama with `llama3.2:3b` | offline fallback LLM (D19) | Ollama MIT; Llama 3.2 Community License (terms not re-read) | https://ollama.com/library/llama3.2 |
| Azure AI Speech, voice `en-IN-NeerjaNeural` | optional Indian-English TTS voice (D19), free tier F0 only | Microsoft Azure terms; terms not re-read | https://learn.microsoft.com/azure/ai-services/speech-service/ |
| onnxruntime 1.30.0 | runs Silero and Piper | MIT | https://github.com/microsoft/onnxruntime |
| pysilero-vad 3.4.0 (Silero VAD model) | voice activity detection / end-of-turn | MIT | https://github.com/snakers4/silero-vad |
| piper-tts 1.8.0 | local TTS, run as a separate subprocess (GPL isolation, D19) | **GPL-3.0-or-later**: never imported into our process; we ship no modified copy | https://github.com/OHF-Voice/piper1-gpl |
| Piper voice `en_GB-alba-medium` | TTS voice (D19) | CC BY 4.0: attribution required (credited here) | https://huggingface.co/rhasspy/piper-voices |
| Piper voices `en_US-lessac-medium`, `hi_IN-rohan-medium` | spike only, not used in the product | lessac: Blizzard 2013 licence, terms not read; rohan: not checked | https://huggingface.co/rhasspy/piper-voices |
| kokoro-onnx 0.4.7, Kokoro-82M v1.0 weights | TTS candidate, rejected (too slow on CPU); spike only | library MIT; model Apache-2.0 | https://github.com/thewh1teagle/kokoro-onnx |
| macOS `say` voices Rishi, Aman, Tara (en_IN) | synthetic test speech for latency runs; not a product component | Apple system component; terms of using generated audio not checked | `say -v '?'` |
| PyAV (`av`) 19.0.1 | audio decoding for faster-whisper | BSD-3-Clause (bundles FFmpeg libraries under LGPL) | https://github.com/PyAV-Org/PyAV |
| jiwer 4.0.0 | WER computation (scripts and spike) | Apache-2.0 | https://github.com/jitsi/jiwer |
| indic-transliteration 2.3.82 | Devanagari to Roman before WER (spike) | MIT | https://github.com/indic-transliteration/indic_transliteration_py |
| soundfile 0.14.0, numpy 2.5.3 | audio I/O and arrays | BSD-3-Clause | https://pypi.org/project/soundfile/ |
| websockets 17.2 | WebSocket support under uvicorn (T4 adds it to requirements) | BSD-3-Clause | https://github.com/python-websockets/websockets |
| Pipecat 1.12.0, LiveKit Agents 1.8.5 / livekit 1.1.20 | voice frameworks evaluated and proved, not used (D19) | BSD-2-Clause / Apache-2.0 | https://github.com/pipecat-ai/pipecat, https://github.com/livekit/agents |
| React, React DOM | frontend UI library | MIT | https://react.dev |
| React Router | frontend routing | MIT | https://reactrouter.com |
| Vite, @vitejs/plugin-react | frontend dev server and build | MIT | https://vite.dev |
| TypeScript | frontend language and type checker | Apache-2.0 | https://www.typescriptlang.org |
| Vitest, jsdom, @testing-library/react | frontend tests | MIT | https://vitest.dev |
| ESLint, typescript-eslint | frontend lint | MIT / MIT-compatible (BSD-2-Clause for typescript-eslint packages: MIT) | https://eslint.org |
| openapi-typescript | generates the typed API client from `docs/openapi.json` (dev only) | MIT | https://openapi-ts.dev |
| OpenAI Codex | AI-assisted question-bank drafting (TJ-2; faculty review required), evidence-report tooling (TJ-7), and tests | OpenAI service terms | https://openai.com/codex/ |
