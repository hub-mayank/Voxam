# Voxam demo script: 5 minutes, followable cold

Drafted by Bhavesh (BH-5) and corrected to what is on `main` (student result view, language choice, Ready-screen modes).
One student takes a short viva; faculty review the transcript, recording and score; the student then sees the released result.
Everything uses local test data: no real students, no paid services.

## Setup (before the audience arrives, about 3 minutes)
Terminal 1, backend + worker + two seeded vivas (`local-dsa`, `local-webdev`):
```bash
FACULTY_TOKENS="mayank:choose-a-long-secret" scripts/run_local.sh --fresh
```
Read the token (the part after the colon) and the student codes from its output or `.local/codes.txt`; never hard-code them in a script.
Terminal 2:
```bash
cd frontend && npm install && npm run dev
```
- Use Chrome on `http://localhost:5173` (the microphone needs localhost or https).
- Second tab: `http://localhost:5173/faculty`, signed in with the faculty token.
- Have one **finished and scored** viva ready (take one beforehand) so the faculty half never waits for scoring.
- If something fails: reload, check both terminals, and fall back to typed answers; the demo still works.

## The demo
| Time | Do | Say |
|---|---|---|
| 0:00 | Open `/student?viva=local-dsa`. | "A student joins with an ID and a personal one-time code. Same structure and rules for everyone." |
| 0:30 | Student `LOCAL01` + the printed code. Rules appear; tick the box, **I agree, continue**. | "Rules and recording consent come first; declining starts nothing." |
| 1:00 | Ready screen: pick **Push to talk**, language **English** (mention **Hindi or Hinglish** exists), **Check my microphone**, say a sentence, play it back, **Yes, I can hear myself**. | "No viva starts on a microphone nobody can hear. Typing is always available." |
| 1:45 | **Start the viva**, **Begin the viva**. Answer the first question by holding the button. | "The clock is the server's. The AI only listens, classifies and phrases." |
| 2:45 | While the interviewer speaks, hold the button (barge-in). | "The AI stops and listens, like a person would." |
| 3:15 | Switch off Wi-Fi for 5 s, back on (or DevTools → Network → Offline). Then type the next answer instead. | "The browser never decides the state; it rejoins the server's session. Voice failure never blocks the exam." |
| 3:45 | Faculty tab: open the finished viva. Show transcript, audio replay, the score with reasons and evidence turn numbers, any confidence flag. | "Every mark cites the turns behind it; the recording replays from those moments; faculty can override with a reason." |
| 4:30 | **Export and release results**: tick release, reload the student's end screen. | "Faculty release results; the student sees the total and the feedback, never before." |
| 4:50 | Close. | "The browser never decides the exam state or the score." |

## Before recording
- [ ] Microphone permission is reset and known; headphones on; notifications off.
- [ ] No real names, codes or tokens on screen; the local test codes are fine.
- [ ] The offline step was rehearsed once; a backup recording of a clean run exists.
- [ ] Do not wait for the real 15 minutes: stop the live student part at the faculty switch.

## What the demo proves
Student: join → rules → mode and language → mic check → voice and typed answers → barge-in → reconnect → result after release.
Faculty: transcript, recording, evidence-cited score, override, export and release.
