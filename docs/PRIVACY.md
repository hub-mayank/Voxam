# Privacy note (draft for review by MSOT)

Voxam is a test system. This note says what it stores, who can see it and what leaves the machine. **Retention is an assumption
until MSOT answers** (`docs/MSOT_QUESTIONS.md`).

## What is stored
| Data | Where | Notes |
|---|---|---|
| Voice recording (stereo WAV: student left, AI right) | `AUDIO_DIR` on the server's disk; path in `sessions.audio_uri` | one file per session |
| Transcript: each turn's text, timing, speech-recognition confidence | database `turns` | |
| Questions asked, phase, prompt version, serving model | database `turns` | |
| AI marks, reasons, evidence turn numbers, confidence flags | database `scores` | 3 runs per viva |
| Faculty overrides and reviews: reviewer name, reason, time | database | |
| Student ID, name (roster) | database `roster` | uploaded by faculty |
| Access code | database, **only a keyed hash** (HMAC-SHA-256 with a server secret) | the code is shown once to faculty |
| Session token | database, **only a hash** | |

Not stored: IP addresses (kept in memory for the wrong-code throttle only), passwords, payment data.

## Who can see it
- **Faculty** with a bearer token (`FACULTY_TOKENS`, one named token per reviewer). Every faculty token sees every viva: there is no
  per-viva permission yet.
- **The student**: their own result, only after faculty release it. Audio is played through a **signed URL that expires after 15
  minutes**.
- **The team** during testing, under the consent form (`docs/consent/`).

## What leaves the machine
By default, nothing but text. Speech recognition (whisper.cpp) and speech synthesis (Piper) run locally.

| Service | Receives | When |
|---|---|---|
| Groq (`gpt-oss-20b`) | the transcript so far and the scoring prompt (text only, no audio) | when selected in `LLM_CHAIN` / `SCORER_LLM_CHAIN` |
| Google Gemini | same, text only | when selected |
| Ollama | nothing leaves: runs locally | default offline fallback |
| Groq Whisper | audio of the answers | **optional, off by default** |

The providers' own data terms apply. Free-tier terms may allow the provider to use submitted content to improve its products (Google
states this for the free Gemini tier); for real students this is a reason to use local models or a paid tier.

## Consent, retention, deletion
- Recording and AI marking need the student's consent on screen before the viva starts (the rules text and version are stored with the
  session). Test vivas use volunteers with a signed form; no real student data without MSOT approval.
- **Retention assumption: 1 month after the viva, then delete** (to be confirmed by MSOT).
- **Deletion is manual today**: remove the session's rows (turns, scores, jobs, session) and the audio file. There is no automatic
  expiry and no self-service deletion button. A student who asks is handled by faculty with that procedure.
- Real audio and signed forms never go into git (`.gitignore`); `scripts/check_secrets.py` runs before every commit.

## Known gaps
No per-viva access control for faculty; no automatic retention job; recordings are not encrypted at rest beyond the disk's own
encryption; the browser connection is only as private as the deployment's TLS (not configured in the local profile).
