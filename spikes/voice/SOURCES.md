# Vendor claims verified for T3

Retrieved 2026-10-08 by fetching the URL and reading the page (summaries by the fetch tool; re-check before relying on a number for money or quota).

| Claim | Page | Result |
|---|---|---|
| Groq `whisper-large-v3-turbo` free plan limits | https://console.groq.com/docs/rate-limits | Free Plan Limits tab: 20 requests/min, 2K requests/day, 7.2K audio-seconds/hour, 28.8K audio-seconds/day. Same for `whisper-large-v3`. The page warns actual limits may differ per account. **Not called: no key was provided.** |
| Gemini TTS and audio-input models have a free tier | https://ai.google.dev/gemini-api/docs/pricing | `gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts`, `gemini-3.1-flash-tts-preview`, `gemini-2.5-flash-preview-tts`: "Free of charge". `gemini-2.5-pro-preview-tts`: free tier not available. Audio-input/Live/Transcribe models listed free of charge. Per-minute free limits are not given on that page. **Not called: no key was provided.** |
| Piper: license, package | https://github.com/OHF-Voice/piper1-gpl | GPL-3.0; `pip install piper-tts`. Matches the installed package metadata (GPL-3.0-or-later). |
| Piper voices | https://huggingface.co/rhasspy/piper-voices (file listing via the Hub API) | 177 voices; **no `en_IN`**; `hi_IN` has pratham, priyamvada, rohan (medium); English accents available: `en_GB`, `en_US`. |
| kokoro-onnx licenses | https://github.com/thewh1teagle/kokoro-onnx | Library MIT; Kokoro model Apache-2.0; model file about 300 MB (quantized about 80 MB). |
| whisper.cpp | https://github.com/ggml-org/whisper.cpp | MIT; Metal GPU inference and Core ML on Apple Silicon; `whisper-stream` example; models tiny...large-v3-turbo. Homebrew formula `whisper-cpp` 1.9.5 with an arm64 bottle (checked locally with `brew info`). |
| faster-whisper | https://github.com/SYSTRAN/faster-whisper | MIT; CUDA or CPU, int8 on CPU; **no Apple GPU backend mentioned**; word timestamps and a VAD filter exist. |
| Pipecat | https://github.com/pipecat-ai/pipecat | BSD-2-Clause; **Python >= 3.11 (3.12+ recommended)**; transports: Daily, FastAPI WebSocket, LiveKit, SmallWebRTC; local Whisper, Piper, Kokoro, Silero services. Barge-in not described on the page (checked in the installed package instead, see the report). |
| LiveKit Agents | https://docs.livekit.io/agents/ | Apache-2.0; needs a LiveKit server (self-hosted or LiveKit Cloud); turn detection and interruptions are core features. Python versions not stated on the page (PyPI wheels resolve on 3.14). |
| Ollama formula | `brew info ollama` (local metadata) | `ollama` 0.40.0, MIT, arm64 bottle. Model pulls come from the Ollama registry (not on the pre-approved network list). |
| macOS voices | `say -v '?'` (local) | `en_IN`: Aman, Rishi, Tara; `hi_IN`: Lekha. 184 voices in total. |
| Python 3.14 wheels | `spikes/voice/wheel_check.sh` (dry-run resolves, 2026-10-08) | All candidates have binary wheels except plain `webrtcvad` (the `webrtcvad-wheels` fork has one). Output in the report. |
