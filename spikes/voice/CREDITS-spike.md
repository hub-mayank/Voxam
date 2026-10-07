# Credits for the voice spike (T3) — for the Planner to merge into `docs/CREDITS.md`

Not merged here on purpose (CORE edits `docs/CREDITS.md`). "Verified" = read from the package metadata or the vendor page on 2026-10-08 (see `SOURCES.md`).

| Name | Used for | License / terms | Source | Status |
|---|---|---|---|---|
| faster-whisper 1.2.1 | local STT (CTranslate2, int8, CPU) | MIT | https://github.com/SYSTRAN/faster-whisper | verified |
| CTranslate2 4.8.2 | inference engine under faster-whisper | MIT | https://github.com/OpenNMT/CTranslate2 | verified (PyPI metadata) |
| OpenAI Whisper weights (base, small, medium; Systran CTranslate2 conversions) | STT models | MIT (Whisper); conversions on Hugging Face `Systran/faster-whisper-*` | https://huggingface.co/Systran | whisper licence not re-read on its page |
| onnxruntime 1.30.0 | runs Silero, Piper, Kokoro | MIT | https://github.com/microsoft/onnxruntime | verified (PyPI metadata) |
| pysilero-vad 3.4.0 (Silero VAD model) | voice activity detection / endpointing | MIT | https://github.com/snakers4/silero-vad | verified |
| **piper-tts 1.8.0** | local TTS | **GPL-3.0-or-later** | https://github.com/OHF-Voice/piper1-gpl | verified. **Copyleft: decide before shipping it inside the product** |
| Piper voice `en_US-lessac-medium` | TTS voice | Blizzard Challenge 2013 "lessac" dataset licence: https://www.cstr.ed.ac.uk/projects/blizzard/2013/lessac_blizzard2013/license.html | https://huggingface.co/rhasspy/piper-voices | **terms NOT read: unverified for product use** |
| Piper voice `en_GB-alba-medium` | TTS voice | CC BY 4.0 (attribution required) | https://huggingface.co/rhasspy/piper-voices | verified (model card) |
| Piper voice `hi_IN-rohan-medium` | Hindi TTS voice (downloaded; not benchmarked) | not checked | https://huggingface.co/rhasspy/piper-voices | unverified |
| kokoro-onnx 0.4.7 + Kokoro-82M v1.0 weights | TTS candidate (too slow on CPU) | library MIT; model Apache-2.0 | https://github.com/thewh1teagle/kokoro-onnx | verified (README) |
| macOS `say` voices Rishi, Aman, Tara (en_IN) | synthetic test speech, TTS baseline | Apple system component; terms of using generated audio in a product not checked | `say -v '?'` | unverified |
| PyAV (`av`) 19.0.1 | audio decoding for faster-whisper | BSD-3-Clause (bundles FFmpeg libraries under LGPL) | https://github.com/PyAV-Org/PyAV | verified (metadata) |
| jiwer 4.0.0 | WER computation | Apache-2.0 | https://github.com/jitsi/jiwer | verified |
| indic-transliteration 2.3.82 | Devanagari -> Roman before WER | MIT | https://github.com/indic-transliteration/indic_transliteration_py | verified |
| soundfile 0.14.0, numpy 2.5.3, websockets 17.2 | audio I/O, arrays, WebSocket client/server | BSD-3-Clause (numpy: BSD-3 + others) | PyPI | verified |
| Pipecat 1.12.0 (proof only) | transport option (b) | BSD-2-Clause | https://github.com/pipecat-ai/pipecat | verified (README) |
| LiveKit Agents 1.8.5 / livekit 1.1.20 (proof only) | transport option (c) | Apache-2.0 | https://github.com/livekit/agents | verified (docs page) |

Dependencies the product would need if the WebSocket route is chosen (for `backend/requirements.txt`, CORE to decide): `websockets` (uvicorn needs it to serve WebSockets; BSD-3), `faster-whisper`, `onnxruntime`, `pysilero-vad`, and a TTS (Piper is GPL; see above).
