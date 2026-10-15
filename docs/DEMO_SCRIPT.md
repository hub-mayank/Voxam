# Five-minute demo script (BH-5, draft: rehearse it, then fix the timings)

**One rule: never improvise the outage and never wait for the real 15 minutes.** The student part runs live for about three
minutes; the faculty part uses a viva that finished earlier.

## Before you press record (checklist)
- [ ] `scripts/run_local.sh --fresh` running with the voice mode you will show (real: whisper.cpp + Piper, or `VOICE_PROVIDER=stub`).
- [ ] `cd frontend && npm install && npm run dev`, browser open at `http://localhost:5173/student?viva=local-dsa`.
- [ ] One finished, scored viva exists (run one earlier; `python scripts/seed_demo.py` also makes demo data: check that it contains a scored session before you rely on it), and its audio plays on the faculty screen.
- [ ] Microphone permission reset, headphones on, notifications off, no real names or codes on screen (the local codes are test data).
- [ ] Network trigger rehearsed once: browser DevTools → Network → "Offline" for about 5 s, then "No throttling".
- [ ] A backup recording of a clean run is saved.

## Script
| Time | Do | The audience sees | Say |
|---|---|---|---|
| 0:00 | Open the join page, point at the demo label (local test data) | Viva ID filled in, hidden code | "Same structure and rules for every student, and the code is personal." |
| 0:20 | Enter student and code, continue | Rules in plain words, one consent tick | "Consent is explicit and the version of the rules is stored." |
| 0:45 | Tick, agree, choose **Push to talk**, run the mic check | Level meter in words, playback of your own voice | "No viva starts on a microphone nobody can hear; typing is always available." |
| 1:30 | Start, answer one question by voice | Question, state words (listening, thinking, speaking), live transcript | "The server keeps the clock; the AI only listens, classifies and phrases." |
| 2:30 | Go offline for 5 s, then online | "Connection lost… timer may continue", then the same question returns | "The browser never decides the state; it rejoins the server's session." |
| 3:15 | Type the next answer instead | Answer accepted, reply shown | "Voice failure does not block the exam." |
| 3:45 | Switch to the faculty dashboard, open the finished viva | Transcript, audio replay, scores with evidence turns, flags | "Every mark cites the turns behind it, and faculty can override with a reason." |
| 4:30 | Show the CSV export or the evidence row | The sidecar-labelled results | "Mock, stub and live results are labelled; nothing is hand-typed." |
| 4:50 | Close | – | "The browser never decides the exam state or the score." |

## If something breaks live
Switch to typing; if the backend is down, play the backup recording. Do not explain the failure while recording; say "that is
exactly the recovery path" only if the reconnect banner really appeared.
