# CL-6 voice lab join form: 👍 done   (2026-10-13, CORE/VOICE)
`/student/voice-lab` now takes a student through the whole voice viva on its own: join with ID and access code, read and accept the rules, choose push-to-talk or hands-free, start the clock, talk. Branch `task/CL6-voice-lab-join` (from `main` at 8f597bf).

- Changed: `frontend/src/student/voice/VoiceLab.tsx` (join flow built only on `useSession()` and `useVoiceSession()`; the `?sid=&token=` link still works), `VoiceLab.test.tsx`, README notes.
- Evidence: `cd frontend && npm run check` -> schema current, tsc and eslint clean, **41 passed, 3 skipped** (the skipped are the opt-in real-backend tests); no dependency added. In a real browser (the in-app browser pane) against `scripts/run_local.sh` and the Vite dev server: the form rendered with no console errors, joining as `LOCAL01` showed the rules, accepting and choosing hands-free then Start reached the lab with the "I'm done" control, and the server showed the session `in_progress` with a start time.
- Not verified / not run: **Connect with a microphone** (it would open a real microphone permission prompt; that is your M2 test); the end of a viva through the form (the `ended` message refreshes the session to the "finished" card; covered by logic, not run in a browser); other browsers.
- Risks found: none new. It is deliberately a developer page: its copy is plain, it shows diagnostics, and it has no design; the real student screens (BH-1/BH-2) use the same hooks.
- Suggestions: (1) Use this page for the volunteers' vivas (TJ-5) if Bhavesh's screens are not in by Thursday, with headphones. (2) When BH-1/BH-2 land, keep this page behind a `?debug` flag for latency and level diagnostics.
- Questions for Mayank: push `task/CL6-voice-lab-join`. None blocking.
- Next task proposed: wait for Parth's and Bhavesh's first PRs (review within 2 h), or the Groq tail-latency options if you want to spend live calls.
