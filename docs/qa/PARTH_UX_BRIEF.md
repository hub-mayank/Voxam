# Parth: faculty UI/UX pass

**Date:** 16 Oct 2026 · **Your paths:** `frontend/src/faculty/` only · **Size:** 4 small PRs, in the order below

Judges and markers will spend most of their time on your screens, so these decide how the product feels. Why this pass: we ran a real
voice viva on Mayank's Mac and looked at the faculty pages with real data. They work, but they read like a database dump. Nothing
below changes the API or the rules, only how the existing data is shown.

## Ground rules
- Frontend only. If a change needs a new API field, write it under "Questions" in your PR and do not fake it.
- No new libraries. Use the classes already in `shared/styles.css` (`card`, `badge`, `table`, `field`, `muted`). New faculty-only
  styles go in a new `faculty/faculty.css` imported from `routes.tsx`. **Do not edit `shared/`, `App.tsx` or anything under `student/`**
  (Bhavesh is changing the shared header there; you will get it by rebasing).
- Every PR: `npm run check` green, tests for new behaviour, screenshots (light and dark) in the PR. No access codes or tokens in screenshots.
- Small PRs. Do not merge your own.

## PR 1: session detail page (`SessionDetail.tsx`)
Problem: one long column. The transcript is below the fold, and when a session is not scored the empty score block and four
disabled action boxes take up half the page.
1. Two columns on wide screens, one on narrow: left = transcript and audio player; right = a summary card.
2. Summary card, top to bottom: student, status badge, total (or "Not scored"), flag badges (`needs_review`, `overridden`, low confidence with its reasons).
3. Scores as five rows, one per dimension: name, bar (width = score / weight), `score / weight`. Show reason and evidence links under each on click, not always open.
4. Make the audio player sticky at the top of the left column so it stays visible while reading.
5. Hide the override and review forms until the session is `scored` or `failed`; for other statuses show one muted line saying why ("Available once the viva is scored").

## PR 2: failed and not-scored states (`SessionDetail.tsx`, `SessionList.tsx`)
Problem: a failed session shows "Not scored" with no explanation. Today this happens to any viva where the scorer model returns an
invalid answer, and a faculty member cannot tell what to do.
1. Failed status: a bad badge and one fixed sentence on the summary card: "Automatic marking did not finish. The answers and audio are saved. Request a rescore or enter a mark yourself."
   Do **not** invent a reason, the API has no failure-reason field (see Questions).
2. Put **Request rescore** on the card for `failed` and `scored`, with the existing confirm step. After it, show "Queued" and poll the session every 5 s until the status changes; stop on unmount.
3. In the sessions table, a `failed` row gets a bad badge and a "Rescore" link that opens the detail page focused on the rescore button.
4. Status badges everywhere use one mapping (scored = good, failed = bad, scoring = info, in_progress = info, ended/abandoned = warn). Put it in one function.

## PR 3: viva list (`VivaList.tsx`)
Problem: titles are long raw strings ("[LOCAL] DSA viva (local run; AI-draft bank approved for local use only)") and every row shows
eight badges, most of them zero.
1. Row layout: title (truncate at one line, full title on hover), subject, then one line of facts: `30 questions · 10 students · 1 scored · 1 failed`.
2. Show only session counts that are above zero. If all are zero, show "No sessions yet".
3. Add a small progress line: scored / roster size.
4. Add a "Results hidden / released" badge (data is already in `results_visible_to_students`).
5. Empty list: a card with one sentence and the "Create a viva" button, not a bare table.

## PR 4: polish and checks
1. Loading states: skeleton rows or a muted "Loading…" in the same place as the content; no layout jump.
2. Table rows are clickable across the whole row, not only the link text; keyboard focus still works.
3. Copy-code button text changes to "Copied" for two seconds.
4. Pass with the browser at 1280 px and 390 px width; fix overflow. Check dark mode.
5. Update `faculty/README.md` for anything that changed.

## Done when
- A person who has never seen the product can open a viva, find a failed session, understand it, and request a rescore without help.
- `npm run check` is green; every new behaviour has a test.
- Screenshots of the four screens at both widths are in the PRs.

## Questions to put in your first PR
- The API gives no reason for a failed session. Is a `scoring_error` field worth adding? (Mayank decides; Claude does the backend.)

## Data you can use for review
`scripts/run_local.sh` creates the LOCAL viva with students LOCAL01–10 and the WebD viva WEB01–05. For a populated dashboard use
`scripts/seed_demo.py` (DEMO). A failed session exists on Mayank's machine only; to see the failed state in tests, build it with the
mocked API.
