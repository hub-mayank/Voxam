# Integrity: what Voxam does about cheating tools, and what it cannot do

Short version: **Voxam cannot stop a tool such as Cluely, and does not claim to.** It makes such use harder to rely on, leaves
evidence for a human, and says so openly to the student. Nothing here changes a mark by itself.

## Why prevention is impossible from a web page
A tool like Cluely is a separate desktop app. It listens to the interviewer's audio, reads the screen and shows hints in an overlay
that is hidden from screen sharing. A page running in a browser cannot see other apps, cannot detect an overlay and cannot stop
screen capture or a second device. The only real prevention is a controlled setting: a managed lab machine, or an invigilator in the
room. For the pilot, the lab iMacs with a person present are that setting; for remote use nothing on our side can replace it.

## What is built (D27)
| Layer | What it does | What it can and cannot catch |
|---|---|---|
| Page signals | While the viva runs the page reports: tab hidden, window lost focus (tab still visible), paste, copy. Stored as time (viva clock, set by the server) and length, never the text. Short absences are ignored by the page. | Catches switching away to look something up on the same machine. Does **not** catch an overlay, a second device or a second person. A student can also trigger these innocently (a notification, the address bar). |
| Rules text `rules-v2` | Tells the student what is noted and that nobody is penalised without a human review. | Deters; no technical effect. Vivas created before this change keep `rules-v1`. |
| Oral cross-check | Once, at the start of the depth phase, the interviewer takes a detail from the student's own opener and asks for it again from another angle. If the model fails a fixed line is used. | Whoever did the work answers easily; someone reading out an answer prepared for a different project tends to contradict their opener, and faculty can see it in the transcript. A tool that listens to the whole conversation **can** answer it, so this is evidence for a reviewer, not a block. |

Already in place and unchanged: the interviewer builds follow-ups from the student's own last answer, and the scorer is protected
against instructions hidden in answers (`neutralise()`, `INJECTION`).

## How faculty should read the signals
- A signal is a fact ("the tab was hidden for 9 s at 05:12"), not a finding. Listen to the audio at that time before drawing a conclusion.
- Several long absences clustered around questions, with answers that begin late and sound read, is worth a conversation. One short blur is not.
- The mark is whatever the rubric gives, plus any human override with a reason. The signals are never an input to the scorer.

## Not built, on purpose
- Blocking copy/paste, forcing fullscreen, or locking the browser: hostile to honest students and trivially bypassed.
- Webcam or screen recording: much heavier consent and privacy cost than this pilot can justify.
- Voice-based "second speaker" or "reading aloud" detectors: no measured accuracy, so no claim. Possible later work needs a labelled set of vivas where such a tool was really used.

## Evidence status
Tests prove the signals are stored, deduplicated, bounded and shown to faculty, and that the cross-check happens once and is rebuilt
from stored turns. **No test shows that any signal detects cheating**; there is no labelled data for that. Browser-level behaviour
(which events fire in Chrome and Safari) is checked by hand in `docs/qa/integrity-browser-check.md`.
