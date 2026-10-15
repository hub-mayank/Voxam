# Privacy note (draft for review by MSOT)

Voxam records volunteer test vivas to evaluate speech recognition, interview quality and AI marks against human marks.
This describes the current prototype and the team's handling policy. **One month after the viva is the proposed retention
period; MSOT said on 2026-10-08 that retention is about one month and configurable by the admin** ([questions](MSOT_QUESTIONS.md)). It is not enforced automatically.

## Data and storage

| Data | Stored by the prototype |
|---|---|
| Voice recording, including captured background sound | One stereo WAV per voice session: participant left, AI right; `AUDIO_DIR`, with its path in `sessions.audio_uri` |
| Transcript and interview audit | `turns`: answer/question text, timings, phase, question ID, classification, model/prompt version and metadata such as STT confidence |
| AI marking | `scores`: three runs, dimension marks, reasons, evidence references, feedback and confidence/review flags |
| Human review | `overrides` / `reviews`: reviewer identity, mark changes, reasons, notes and timestamps |
| Participant and session details | `roster`: student ID and optional name; `sessions`: participant ID, status, consent timestamp/rules version and session times |
| Login and processing state | HMAC-hashed access codes, hashed session tokens, failed-code counters, scoring jobs and possible error text |
| Operational logs | Provider/model, timing, usage and status in telemetry; API/worker logs can include client IPs, request paths/query strings, session IDs and errors |
| Copies made by operators | Faculty CSV exports, human marking sheets, WER reference/hypothesis files, signed forms and any private evidence/backup copies |

The [local launcher](../scripts/run_local.sh) defaults to `.local/viva.db`, `.local/audio/`, `.local/api.log`,
`.local/worker.log` and a **plaintext** `.local/codes.txt` for its seeded test roster. Other deployments use `DATABASE_URL`
and `AUDIO_DIR`; direct voice startup defaults to `audio/` relative to its working directory. Telemetry defaults to
`~/.cache/ai-viva/telemetry.jsonl` (`TELEMETRY_FILE` overrides it). Local TTS also caches generated speech under
`AUDIO_DIR/tts_cache` unless `TTS_CACHE` changes it. CLI and benchmark tools can write additional transcripts/results.

The student browser keeps its session token and join/rules details in tab `sessionStorage` to resume after reload;
the faculty browser also keeps its token in tab `sessionStorage`. Signed forms, identity-to-volunteer-ID mappings
and recordings belong in team-controlled private storage outside Git. Any shared-drive location and its permitted
users must be named to the volunteer before recording; the code does not create or control that drive. Voices and
transcripts may identify people even when filenames use volunteer IDs.

## Access and sharing

- Valid `FACULTY_TOKENS` allow faculty to view every viva's roster, transcript, audio and marks, review/override and export.
  There is currently no restriction by viva owner.
- In the real backend, a student's session token authorizes only their session. The result endpoint returns total/dimension marks
  and feedback after faculty release; it does not provide the faculty transcript or audio replay endpoint.
- Faculty session detail issues a signed audio URL valid for 15 minutes. **Anyone holding that URL can play the audio
  until expiry without a faculty token.** URL expiry does not delete the recording. Treat URLs and logs containing them
  as sensitive; do not paste them into issues or public demos.
- Operators with disk/database access can read stored files. The project team and human marker may review consented
  test material; MSOT reviewers may receive agreed submission evidence. Public use of a volunteer's recording or
  identifiable transcript/marks requires separate public-demo opt-in on the signed form.

## Processing outside the machine

The local launcher selects local Ollama when available, otherwise a mock LLM. Its voice stack selects whisper.cpp
and Piper when installed, otherwise a stub. Local models process on the server; the browser still sends audio/text to
that server. A remote `OLLAMA_HOST` sends prompts to that host, so the name "Ollama" alone does not establish local use.

| Configured service | Content it may receive |
|---|---|
| Local whisper.cpp / Piper / Ollama | Participant audio for STT; generated reply text for TTS; answer/context and marking prompts for the LLM, on the configured host |
| Groq or Google Gemini LLM | Current answer/question and interview prompts or full transcript and scoring prompts, including rubric/private hints; product LLM adapters do not send raw audio |
| Cerebras, OpenRouter or another OpenAI-compatible endpoint | The same LLM prompt content when configured; routed services may involve their selected downstream model provider |
| Optional experimental cloud speech tools | Groq Whisper receives answer audio; Azure Speech receives text for synthesis when those tools are explicitly used |

`LLM_CHAIN` and `SCORER_LLM_CHAIN` can differ and can fall back between providers. Tell volunteers **every configured
recipient**, including fallback providers and remote model hosts, before consent. Cloud speech tools are separate from
the product's local/stub voice path. Provider account terms govern their handling; this project does not verify or
promise their retention, training use or deletion. Review the selected service/account terms before sending volunteer data.

## Consent, retention and deletion requests

Volunteer testing requires a signed form in [docs/consent](consent/) and the application's recording/rules consent
before starting. The database stores a consent timestamp and rules version, not the full signed form or a public-demo
permission. Keep that permission with the private signed form. Do not use real MSOT student data without MSOT approval.

The proposed policy is to delete participant recordings, transcripts, marks, identifying consent records and related
private copies **one calendar month after the viva**, or earlier on a deletion request. Operators must record the due
date and perform deletion themselves. For testing questions or deletion requests, contact **Tejas** at
`dadhichtejas653@gmail.com`, using your volunteer/session ID privately. The operator must name the exact private
storage location and permitted recipients on the consent form before testing.

## Expired-session cleanup

The retention helper previews by default. Stop the API and scoring worker before applying it; this prevents an in-flight session or
worker from recreating data while cleanup runs. Set `DATABASE_URL`, `AUDIO_DIR`, and `TTS_CACHE` to the same locations used by the
server. For the local launcher, those are usually `.local/viva.db`, `.local/audio`, and `.local/audio/tts_cache`:

```sh
DATABASE_URL="sqlite:////$PWD/.local/viva.db" AUDIO_DIR="$PWD/.local/audio" TTS_CACHE="$PWD/.local/audio/tts_cache" \
  python scripts/purge_expired_sessions.py --before 2026-09-15T00:00:00Z

# After checking the counts and cutoff:
DATABASE_URL="sqlite:////$PWD/.local/viva.db" AUDIO_DIR="$PWD/.local/audio" TTS_CACHE="$PWD/.local/audio/tts_cache" \
  python scripts/purge_expired_sessions.py --before 2026-09-15T00:00:00Z --apply
```

Use the cutoff that matches the approved retention schedule (the example is illustrative). Apply mode removes only terminal sessions
whose `ended_at` is at or before that timezone-qualified cutoff. It deletes the session, transcript turns, scores, reviews, overrides,
integrity events, scoring jobs, access codes and roster row, plus local per-session recordings and generated TTS cache files. Clearing
the shared TTS cache may make the next voice run slower; it is disposable and will be rebuilt. A path check refuses per-session audio
outside `AUDIO_DIR`. If an external recording URI is configured, cleanup stops before changing anything so its storage provider can be
handled separately. If file removal fails after the database commit, the command reports that local cleanup remains incomplete.

This helper does not remove the viva's shared question bank, provider-held data, application or system logs, backups, signed consent
forms, exports, or copies on shared drives. Continue the manual steps below for those copies and record what was handled.

### Manual operator procedure for copies outside the application database

1. Confirm the requester and affected session/volunteer IDs privately; stop further recording, scoring and sharing of
   that material. Revoke affected session/access credentials and prevent queued or in-flight work from recreating data.
2. Remove the recording and any participant-specific generated-speech cache or temporary files. Remove dependent
   turns, scores, jobs, overrides, reviews and any integrity-event rows before deleting the session. Remove associated
   access-code entries before corresponding roster entries when they are no longer needed for another authorized session.
3. Remove matching private clips, references/hypotheses, exports, marking sheets, signed forms and identity mappings;
   inspect logs and backups for related identifiers/content. Coordinate deletion of shared copies with their holders.
   For provider-held copies, use the applicable provider process and report any limit rather than promise deletion.
4. Verify that the session/audio can no longer be retrieved and private copies have been handled. Confirm completion
   and any unresolved copies to the volunteer; keep only a minimal non-content administrative record of the request.

## Deployment limitations

There is no automatic retention job, deletion UI or per-viva faculty access control. Application-level encryption at
rest is not implemented; disk encryption and private filesystem/backup permissions are the operator's responsibility.
The local profile uses development credentials and HTTP, so it must not be exposed for a real student deployment
unchanged. `CONTRACT_STUB=1` relaxes authentication for synthetic demos; never use it with participant data.
Remote deployments need HTTPS/WSS and private credentials. Ignore rules cover some local outputs, but do
not protect arbitrary filenames: never commit real audio, signed forms, identifying mappings or raw participant data.

Technical sources: [database models](../backend/app/db/models.py), [student service](../backend/app/services/student.py),
[audio access](../backend/app/api/routes_faculty.py), [audio links](../backend/app/services/views.py),
[voice configuration](../backend/app/voice/config.py), [LLM factory](../backend/app/llm/factory.py),
[telemetry](../backend/app/telemetry.py), [student browser storage](../frontend/src/student/session/useStudentSession.ts),
[faculty browser storage](../frontend/src/api/useFacultyApi.tsx).
