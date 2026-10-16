# Student flow checklist (BH-4)

Run top to bottom in **Chrome, Safari and Firefox**. Backend: `scripts/run_local.sh` (stub voice is fine for the screens; real voice for the audio items).
Partial local results from 2026-10-16 are recorded below. A result marked partial does not pass the full checklist row; blank cells are untested. Every reproducible failure becomes a GitHub issue with steps, expected, actual and a screenshot.

| # | Step | Expected | Chrome | Safari | Firefox |
|---|---|---|---|---|---|
| 1 | Open `/student`, enter viva `local-dsa`, student `LOCAL01`, the printed code | Rules screen with the rules text | Reached Rules | Reached Rules; flow stopped here | |
| 2 | Enter a wrong code | A kind, specific message; no crash; wait time shown after repeated tries | | | |
| 3 | Decline the rules | Nothing starts; can still accept later | | | |
| 4 | Accept, press Start | First question shown, countdown starts near 15:00 | First question and running countdown shown | | |
| 5 | Type an answer, send | The AI's reply appears; countdown keeps running | Answer submitted; next question shown and timer continued | | |
| 6 | Reload the page mid-viva | Same question and time left; no duplicate answer | Current question restored; saved-answer note shown; no duplicate observed | | |
| 7 | Turn the network off, send, turn it on, send again | One answer stored; no duplicate | | | |
| 8 | Wait until the clock reaches 0 | Closing message; no more input | | | |
| 9 | Mic check, deny permission | Plain steps to fix it; typing still works | | | |
| 10 | Mic check, allow | Level meter moves when you speak | | | |
| 11 | Voice answer (push-to-talk) | Live transcript, AI speaks, state label changes | | | |
| 12 | Speak while the AI is talking | The AI stops and listens | | | |
| 13 | Narrow the window to phone width | Nothing overlaps; buttons reachable | Partial: Viva screen checked at 390×844 and 1280×800 CSS px; no horizontal overflow. Other screens untested. | | |
| 14 | Choose a voice mode without doing the mic check | Start is disabled and a link to the check is shown; typing stays available | | | |
| 15 | Wrong code twice in a row | The button counts down the wait the server asked for and the fields are kept | | | |
| 16 | Leave the tab in the background until the clock reaches 0, then return | The correct closing state; no extra answer sent | | | |
| 17 | Finish five vivas one after another in one tab | No stuck microphone indicator; no duplicate sockets | | | |
| 18 | Tab through every screen with the keyboard only | Visible focus; every control reachable; no trap | Partial: Join through first text answer exercised by keyboard; full screen/control audit untested. | Partial: Join to Rules only; full screen/control audit untested. | |
| 19 | Same flow in Edge | As Chrome | | | |
