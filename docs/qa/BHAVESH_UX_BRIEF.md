# Bhavesh: student UI/UX pass and the shared header

**Date:** 16 Oct 2026 · **Your paths:** `frontend/src/student/`, `frontend/src/App.tsx`, `frontend/src/shared/` · **Size:** 4 small PRs, in the order below

This is the first screen a judge or a student sees. The flow works end to end (join, rules, ready, mic check, viva, done) and a real
voice viva ran on Mayank's Mac. This pass makes it look and feel like a product. It changes presentation only: the screens, the
server-owned clock and the error sentences in `copy.ts` stay as they are.

## Ground rules
- Frontend only, no new libraries. Keep the tokens in `shared/styles.css` (light and dark both).
- **You own the shared header and shared styles** so Parth does not collide with you. Parth only edits `faculty/`; he rebases onto your PR 1.
- Do not touch `copy.ts` wording except where this brief says so. Do not touch voice or session logic (`voice/`, `session/`).
- Every PR: `npm run check` green, tests for new behaviour, screenshots (light, dark; 390 px and 1280 px). No codes or tokens in screenshots.
- Do not merge your own PRs.

## PR 1: brand header and home page (`App.tsx`, `shared/Page.tsx`, `shared/styles.css`)
1. A header on every page: "Voxam" at the left (links to `/`), and on faculty pages "Faculty", on student pages "Viva". Same height, border below, works at 390 px.
2. Home page (`/`), replacing the bare link line: one-sentence product line ("A fair, voice-first viva that your faculty can audit."), then two large cards: **I am taking a viva** (to `/student`) and **Faculty dashboard** (to `/faculty`). Under them, three short facts: it asks follow-up questions, marks against a fixed rubric, and every mark has a transcript and audio to check.
3. Use only facts that are true today. Do not claim anything about hosting or scale.
4. Make `Page` accept an optional `wide` flag so faculty pages keep 1100 px and the student pages keep 760 px.

## PR 2: student step indicator and Join screen
1. A four-step indicator across student screens: Join, Rules, Ready, Viva. The current step is marked with text and a shape, not colour alone; add `aria-current="step"`. The Done screen shows all four as complete.
2. Join: group the fields in one card, label them plainly, show the 'Wait 7 s' state in the button text, keep the fields filled on a wrong code (already true: do not break it).
3. Larger touch targets: buttons at least 44 px high on narrow screens; inputs 16 px font so iOS does not zoom.

## PR 3: viva screen
1. Timer: keep the number and add a thin progress bar under it (remaining / total). It turns to the `warn` colour at 1 minute and a text note appears ("1 minute left"); the bar is not the only signal. The screen-reader announcements stay once at 1 minute, 10 s and 0.
2. Conversation log: interviewer and student lines in two clear styles (labelled "Interviewer" and "You"), newest at the bottom, scrolls itself to the newest line without stealing focus from the answer box.
3. Voice: hold-to-talk button big and centred with a short label for each state (ready, listening, thinking, speaking). Typing box stays visible beneath it, as it is now.
4. On reload mid-viva, the log currently shows only the opening question. Check whether `GET` session state returns earlier turns; if it does, show them; if it does not, show one muted line "Earlier answers are saved" and write the gap under Questions in the PR. Do not invent history.

## PR 4: Done screen and the final pass
1. Done: a clear heading, the state (marking, failed marking, released result) in one sentence each from the existing `ResultView` states (the failed-marking sentence was merged in #71; keep it), and the "Check again" button.
2. Released result: scores as five rows with bars (same look as Parth's summary card; reuse the CSS you wrote in PR 1 so they match).
3. Browser pass from `docs/qa/bh-4-browser-pass.md`: Chrome and Safari, 390 px and 1280 px, dark mode, keyboard only for the whole flow. Record what failed and what you fixed.
4. Update `docs/qa/student-flow.md` for anything that changed.

## Done when
- A student who has never seen it can get from the code to the first question in under a minute without help.
- `npm run check` is green, new behaviour has tests, and the browser pass table is filled in.
- Screenshots of Join, Ready, Viva and Done at both widths are in the PRs.

## Questions to put in your PRs
- Does the session state return earlier turns on reload (PR 3.4)?
