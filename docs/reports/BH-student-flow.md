# BH-1/BH-2/BH-3 Student flow + plan reconciliation: ⚠️ partial   (2026-10-15, Claude took over the student pages)
Bhavesh had no code in the repository the day before freeze, so the student flow was built here and his plan was reconciled with
the repository (`docs/qa/BHAVESH_REPLY.md`). **Not verified with a real microphone, Safari, Firefox, Edge, a phone-width window or a
screen reader**: those are Bhavesh's BH-4 pass.

- Changed: six screens in `frontend/src/student/screens/` (join, rules and consent, ready, mic check, viva, done) with `TextViva`,
  `VoiceViva`, `Timer`, `StudentError`, `copy.ts`, `phase.ts`, `micSample.ts`; the session hook gains `restoring` (a reload no
  longer bounces the student to the login), `invalid_state` re-reads the status, and a first-paint timer fix.
- Evidence: `cd frontend && npm run check` -> schema current, `tsc`, `eslint`, **78 passed, 3 skipped** (14 new screen tests, 2
  copy tests). By hand against the real local backend (`scripts/run_local.sh`, mock LLM, stub voice): wrong code (kind sentence,
  fields kept), right code, rules, consent, ready, typed answer (next question shown, timer 14:59 then 14:49), a reload in the
  middle (same question and time left, no duplicate).
- Not verified / not run: real microphone and hands-free in a browser (Mayank's M2), reconnect on a real network drop, Safari /
  Firefox / Edge, screen reader, five vivas in a row, phone width. The conversation log restarts after a reload (the status gives the
  current question only).
- Risks found: a student on a shared machine keeps the session token in tab `sessionStorage` until "Sign out" (documented in
  `docs/PRIVACY.md`); the mic sample uses MediaRecorder in the browser's default format (playback only, never sent).
- Suggestions: have Bhavesh run `docs/qa/student-checklist.md` (rows 14-19 added) on a real Mac tonight; put a "Sign out" on the
  viva screen only after a decision (an accidental click would end a student's access).
- Questions for Mayank: none blocking. Decide who sends `docs/qa/BHAVESH_REPLY.md` to Bhavesh.
- Next task proposed: BH-4 by Bhavesh; T8 live runs by Claude after the Groq token window rolls over.

## Plan ideas inherited, checked against our plan
See section 1 of `docs/qa/BHAVESH_REPLY.md`. Adopted: text-first exam, server-owned clock, stale-event rules, idempotent submit,
human error copy per code, retry countdown, voice-optional fallback, mic check with playback, announcements without flooding,
bounded reconnect, central dispose, keyboard/focus, risk register, five-minute demo shape. Kept ours: PCM16 AudioWorklet (not
MediaRecorder), the existing reducer (not React Query), whisper.cpp + Piper (not Kokoro/faster-whisper), our load/WER/cost scripts.

## What is left, and whose it is (state at 2026-10-15 night)
**Claude, can do alone:** T8 live runs (3 follow-up personas on a live model; injection, off-topic and Hinglish probes; scorer v3
5x5) once the Groq token window rolls; clean-clone check after the fixes merge; first-pass review of every PR; final report build
and submission summary; optional deletion script for the privacy note.
**Mayank only:** push `task/BH-student-flow` and `task/fix-quickstart-33-34`; mark #31/#32/#35/#36 ready for review and merge;
merge Claude's PRs (self-approval is blocked); send the reply to Bhavesh; sign off the consent form and name the storage location;
approve both question banks in the faculty screen; run the microphone test (M2) on his Mac; find the human marker (B7); host the
volunteer vivas (TJ-5); decide latency strategy and hosting for the finals (B8/T11); record the demo; submit.
**Others:** Tejas TJ-1 forms, TJ-3 clips, TJ-5 volunteers; Parth faculty-flow QA pass; Bhavesh BH-0 review, BH-4, BH-5.
