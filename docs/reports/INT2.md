# INT2 Integrity signals from the student page: ⚠️ partial   (2026-10-19, CORE)
The page now reports tab, focus, paste and copy signals to the endpoint added in INT1. Not yet checked in a real browser, and the faculty display (Parth) is not built.

- Changed: `frontend/src/student/integrity/` (`tracker.ts`, `useIntegritySignals.ts`), `studentApi.integrity()`, the two types, one hook call and one muted notice line in `student/screens/Viva.tsx`. Bhavesh had not started this item and a day is left, so it was done here; his brief is marked done.
- Behaviour: an absence under 3 s sends nothing; a tab switch sends one `tab_hidden` (not also `window_blur`, whichever event the browser fires first); a window that loses focus while the tab stays visible sends `window_blur`; paste and copy send only a length; one retry after 5 s on a lost connection or a 5xx, otherwise dropped; no error is ever shown. Listening stops when the viva screen unmounts.
- Evidence: `cd frontend && npm run check` -> `114 passed | 3 skipped` (adds 10: 5 tracker, 5 hook); `npm run build` passed.
- Not verified / not run: any real browser (Chrome, Safari: `docs/qa/integrity-browser-check.md` is Tejas's); voice mode with a real microphone; the 3 s threshold is a judgement, not measured; the notice line text is mine and Bhavesh may restyle it.
- Risks found: the notice line sits on the viva page for every student; if #80 restyles `Viva.tsx` there may be a small merge conflict (one added line).
- Suggestions: Parth's signals section next (faculty cannot see the signals until it exists, except in the raw API).
- Questions for Mayank: none.
- Next task proposed: Parth's integrity display, then Tejas's browser sheet.
