# Integrity signals: browser check (fill in by hand)

Owner: Tejas. Run against the local app (`scripts/run_local.sh`, a LOCAL student, text mode first, then voice mode). Faculty page:
open the session after the viva and look at the integrity list. Write what you **saw**, not what you expected. "Not seen" is a valid result.

| # | Action during the viva | Chrome (mac) | Safari (mac) | Expected |
|---|---|---|---|---|
| 1 | Switch to another tab for about 10 s, come back | | | one `tab_hidden`, about 10 s, no `window_blur` |
| 2 | Click another app (not a browser tab) for about 10 s, come back | | | one `window_blur`, about 10 s |
| 3 | Switch tab for 1 s only | | | nothing stored (below the page's threshold) |
| 4 | Click the address bar and come back | | | nothing, or one short `window_blur` below the threshold |
| 5 | Paste 50 characters into the answer box | | | one `paste`, `chars` about 50, the text itself is not shown anywhere |
| 6 | Select and copy the question text | | | one `copy` with a length |
| 7 | Open the page, start, then turn Wi-Fi off, switch tab, turn Wi-Fi on | | | the viva continues; the signal arrives late or is dropped; no error shown to the student |
| 8 | Voice mode: hold to talk, switch tab while the AI speaks | | | `tab_hidden`; the AI keeps speaking and the viva continues |
| 9 | Reload the page mid-viva | | | no signal for the reload itself; the viva resumes |
| 10 | Faculty detail: are the signals shown with a time that matches the audio? | | | time within a few seconds of what you did |

Also record: browser versions, anything that fired that should not have, anything that did not fire. Do not paste codes or tokens here.
