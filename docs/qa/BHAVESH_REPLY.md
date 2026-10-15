# Reply to Bhavesh: your implementation plan, our repository, and what is left for you

**From:** the project (Mayank, with Claude's review) · **Date:** 15 Oct 2026 · **Freeze:** Friday 16 Oct, 18:00

Bhavesh, thank you for the plan. It is a good plan: it puts the exam before the demo, it keeps the server in charge of time and
state, and its error copy, test tables and demo script are better than what we had. The honest problem was timing: it was written
without the repository, and the repository had already moved. So we did three things. We read your plan line by line against the
code and decisions. We took everything that fits. And, because the student pages are on the critical path and the clock is short,
we built the student flow ourselves so you are not blocked and can spend your time where you add the most: wording, testing and the
demo. This note tells you exactly what changed, why, and what is yours now.

## 1. What we adopted from your plan (and where it is now)

| Your idea | Where it lives now | Status |
|---|---|---|
| Ship the reliable exam before the impressive demo; text mode first | `TextViva.tsx` is the whole viva by typing; voice is an option on top | built, tested |
| Server owns the clock; resync on every event; ended is terminal | `session/state.ts` (`remaining_ms` from every response), `Timer.tsx`; `ended` → `done` only | built, tested |
| One active question; ignore stale events | the reducer replaces the question from each server reply; a late `deadline_passed` or `bad_client_seq` re-reads the status | built, tested |
| Submit once; disable while pending; idempotent retry | `submitAnswer` reuses the same `client_seq` for the same text; Send is off while busy | built, tested |
| Human error copy for every state, no raw codes | `copy.ts` (a test fails if an API code has no sentence); full table in `docs/qa/student-flow.md` | built, **needs your review of the wording** |
| Wrong code: disable submit for the server's interval, keep fields | `Join.tsx`: "Wait 7 s" from `retry_after_ms` | built, tested |
| Voice is optional: failure exposes text mode | mic denied, no device, closed socket and a voice error all leave the typing box on | built, tested |
| Mic check: permission, level, record, playback, confirm | `MicCheck.tsx` + `micSample.ts`; voice modes stay locked until it passes | built, tested |
| Level meter with words, not colour only; announce, do not flood | meter says quiet / good / very loud; timer announced once at 1 minute, 10 s, 0 | built |
| Bounded reconnect with honest status, then manual rejoin | `useVoiceSession`: 1, 2, 4 s, three tries, then a "Reconnect" button; the banner says the timer may continue | built (SDK) |
| Never put tokens in a WebSocket URL | the session token is the first WebSocket message (`docs/VOICE_PROTOCOL.md`) | already true |
| One playback owner, stop stale audio | `voice/player.ts` clears on `interrupt` and on close | already true |
| Central dispose on unmount | the voice hook stops tracks, socket, player and timers on unmount; the mic sample URL is revoked | built |
| Focus moves to the new screen heading; keyboard reachable | `useFocusHeading`; hold-to-talk also works with Space/Enter | built |
| Never persist the access code or audio | only the session token and rules text are in `sessionStorage`; the code is never stored | built |
| Result and feedback on the end screen (your PR #39 had it) | `ResultView.tsx` on the Done screen: total, dimensions in words, feedback with turns, "not released" and "still marking" states | built, tested |
| Browser/device/network/timing test matrix | folded into `docs/qa/student-checklist.md` (see section 4) | yours to run |
| Five-minute demo with one success and one recovery | `docs/DEMO_SCRIPT.md` (draft by us, adapted to the real features) | **yours to rehearse and finish** |
| Risk register and fallbacks | adopted as-is: protocol mismatch → stop, TTS failure → show text, noisy mic → retest then text | in force |
| "Do not start with Pipecat or LiveKit" | same decision, already made (D19): a custom FastAPI WebSocket | agreed |

## 2. What we changed, and why (so you do not build the wrong thing)

| Your plan | Our repository | Why we keep ours |
|---|---|---|
| **Capture with MediaRecorder** (Opus/WebM slices) | **AudioWorklet to 16 kHz PCM16 frames** (`voice/capture.ts`, protocol v1) | The server decodes raw PCM16. A MediaRecorder client would send audio the server cannot read. MediaRecorder is used in exactly one place: the mic-check sample, where the browser only has to play it back to the student. |
| **React Query for server state** | the `useStudentSession` reducer and provider that already exist | It is a new dependency (credits, approval) and the reducer already does cache-free, restart-safe state. Our rule is no new dependencies this close to freeze. |
| **faster-whisper and Kokoro** as the recommended models | **whisper.cpp base and Piper** (D19) | Measured: Kokoro was too slow on CPU and faster-whisper is only the spike baseline. This is also server-side, never the browser's business, as you said. |
| **Locust, load and WER harness** | `scripts/load_test.py` (T7), `scripts/wer.py` (TJ-6), `scripts/cost_model.py` (T9) | Already built and run. You asked to contribute only after coordination: the answer is "not needed". |
| **Pause capture while the AI speaks** | push-to-talk only enables the button while the server says *listening*; hands-free has a 320 ms barge-in guard | Matches your intent (no feedback loops) and is already how the server works. |
| **Token in "resume credentials"** | a rejoin is `POST /student/join` again with the code, which returns a new token; the old token stops working | The code is never stored, so a reload resumes through the saved *session token*; a second tab replaces the first. |
| **Edge** in the browser matrix | added to the checklist | Fair point, we had only Chrome/Safari/Firefox. |

Everything else in the plan that was a recommendation for later (Pipecat or LiveKit after freeze, a cloud STT fallback) stays
**phase two**, as you wrote.

## 3. What is already built (do not duplicate it)

All under `frontend/src/student/`, branch `task/BH-student-flow` (PR to follow):

- `screens/Join.tsx`, `RulesConsent.tsx`, `Waiting.tsx` (the "ready" screen), `MicCheck.tsx`, `Viva.tsx`, `Done.tsx`
- `TextViva.tsx`, `VoiceViva.tsx`, `Timer.tsx`, `StudentError.tsx`, `copy.ts`, `phase.ts`, `micSample.ts`, `student.css`
- `screens/screens.test.tsx` (14 tests: wrong code and wait, consent gating, voice locked until mic check, a full typed viva,
  `deadline_passed`, reload restore, sign-out, mic denied / quiet / pass, hold-to-talk, lost connection, sign in again)
- verified by hand against the real backend (mock LLM, stub voice): wrong code, rules, consent, ready, a typed answer, a reload in
  the middle. **Not verified: a real microphone, Safari, Firefox, Edge, a phone-width window, a screen reader.** That is your part.

## 4. What is yours now (with the exact acceptance for each)

You may change only `frontend/src/student/screens/*`, `docs/qa/*` and `docs/DEMO_SCRIPT.md` (`docs/ownership.json`). Session and voice
code are shared foundation: if you find a defect there, file an issue with steps and a screenshot and we fix it the same day.

1. **BH-0 review: the words.** Read `docs/qa/student-flow.md` and `frontend/src/student/copy.ts` as a nervous first-year student.
   Rewrite any sentence that is unclear, blaming or too long; every sentence must still tell the student one next action.
   *Done when:* a PR changes only `copy.ts` wording and the table, `npm run check` passes (the test still requires one sentence per code).
2. **BH-4 browser pass.** Run `docs/qa/student-checklist.md` top to bottom on a real machine in Chrome, Edge, Safari and Firefox
   (voice items on at least two). Add the rows we left out: tab in the background when the clock reaches zero, five vivas in a
   row (no stuck microphone indicator), offline during an answer, phone width.
   *Done when:* the filled table is committed under `docs/qa/results/`, every ❌ is a GitHub issue with steps, expected, actual and
   a screenshot, and blocking ones are marked so.
3. **Accessibility pass (30 minutes, keyboard first).** Tab through all six screens with no mouse; run VoiceOver (Safari) or
   NVDA through Join → Viva once. *Done when:* a short note in `docs/qa/` lists what a screen reader said at the timer and error
   moments and anything it could not reach.
4. **BH-5 demo script.** Take `docs/DEMO_SCRIPT.md`, run it end to end three times, fix the timings and sentences, record one
   clean take and one backup. *Done when:* Mayank can follow it cold, and the recording is saved outside git.
5. **Small UI fixes you find.** Spacing, labels, focus order, mobile layout: fix them in `screens/*` and `student.css` (one concern
   per PR, about 400 lines or fewer). Run, and paste into the PR:
   ```bash
   cd frontend && npm run check
   python ../scripts/check_paths.py bhavesh
   python ../scripts/check_secrets.py
   ```

## 5. Ground rules (unchanged, and they protect you)
- One card per pull request; Claude does a first-pass review within two hours; Mayank merges.
- No new dependencies, no real student data, no recordings, no access codes in git.
- If something in this note conflicts with the merged repository, the repository wins: say so in the PR and we fix the note.

## 6. Questions for you (reply in the PR or the group)
1. Have you accepted the repository invitation and run `scripts/run_local.sh` on your machine? If not, that is the first thing to
   do: nothing above works without it.
2. Which browsers and operating systems do you actually have? We need a Safari run on a real Mac.
3. Which of items 1–4 do you want to take first? Our suggestion: 4.2 (the browser pass) tonight, 4.1 tomorrow morning, 4.4 tomorrow afternoon.

## 7. Timeline to the freeze
| When | You | Us |
|---|---|---|
| Thursday evening | accept invite, run locally, start the browser pass | PR with the student flow; fix what your pass finds |
| Friday morning | wording review, accessibility pass | defects fixed same day |
| Friday afternoon | demo script rehearsal and recording | final merge and clean-clone check |
| Friday 18:00 | **freeze**: only defect fixes after this | |
