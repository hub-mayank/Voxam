# Voxam demo script — 5 minutes, followable cold

One student takes a short viva in the browser; faculty review the
transcript, recording and score. Everything here uses seeded DEMO
data — no real students, no real data, no paid services.

Corrections vs the old BH-5 doc (local branch `feat/bhavesh-bh-5`):
mode is chosen by the `?mode=` URL parameter (not by an in-screen
"Use voice instead" button); mic check is required before voice
and skipped for text; Done shows closing words + Sign out, no score;
the faculty token is taken from `run_local.sh` output, never
hard-coded; no button labels are quoted unless they are verified
on main (check labels on the live UI before presenting).

## Setup (do this before the audience arrives, ~2 minutes)

Terminal 1 — backend + worker + seeded LOCAL viva:

```bash
scripts/run_local.sh
```

It prints the LOCAL students (`LOCAL01`–`LOCAL10`) with their
one-time access codes and the faculty token. Keep it open. Do NOT
hard-code the faculty token in this script — read it from the
terminal output each time.

Terminal 2 — frontend:

```bash
cd frontend && npm install && npm run dev
```

Open `http://localhost:5173`. For voice, use Chrome on localhost
(the microphone needs https or localhost). Have a second tab ready
on `http://localhost:5173/faculty` for the faculty half.

If anything fails: check both terminals for errors, reload the
page, and fall back to the typed answers in step 1:30–3:30 — the
demo still works.

## The demo

### 0:00–0:30 — "This is Voxam: a 15-minute spoken technical viva, scored and auditable."

Say: "A student joins with an ID and a one-time code, takes the viva
by voice or typing, and faculty review the transcript, the
recording and the score."

### 0:30–1:00 — Join and rules

1. Open `/student?viva=local-dsa`.
2. Join with viva `local-dsa`, student `LOCAL01`, and the code
   printed by `run_local.sh`. Join takes Viva ID + student ID +
   access code.
3. Say: "The rules are shown before anything is recorded.
   Declining does not start the viva."
4. Tick the agreement checkbox, then Accept.

### 1:00–1:30 — Ready and mic-check gating

1. The Ready screen (`/student/ready`) shows Start.
   Say: "The clock starts on the server, not in the browser —
   reloading cannot buy extra time."
2. For the voice half: go to Mic check (`/student/mic-check`),
   run the check, confirm, and return to Ready with voice mode.
   Mic check is required before voice.
3. For the text half: skip mic check. Mic check is skipped
   for text.

Mode selection (verify the exact control on the live UI): the
viva router reads `?mode=` — `text`, `push_to_talk`, or
`hands_free` — else the saved `vivaAnswerMode`, else `text`.

### 1:30–3:30 — The viva (type once, talk once, interrupt once)

1. Open `/student/viva?mode=text`. Answer the first question by
   typing and send.
   Say: "Every answer is idempotent — a retry after a network
   drop never records an answer twice."
2. Open `/student/viva?mode=push_to_talk` for the voice half.
3. Use the push-to-talk control, answer the next question, release.
   Say: "Live transcript, the AI speaking back, the countdown
   still running."
4. While the AI is speaking, use the push-to-talk control again.
   Say: "Barge-in: the AI stops and listens. If the mic fails,
   the student can always type instead."

### 3:30–4:00 — Finish

1. Answer until the closing turn, or let the clock run out.
   Say: "When time is up the server ends the viva; a late answer
   is not recorded."
2. Done (`/student/done`) shows the closing words and Sign out.
   Say: "Done shows the closing words. The score lives on the
   faculty side."
   Do NOT promise a transcript or result on Done — main's Done
   shows closing words + Sign out, no score.

### 4:00–5:00 — Faculty review

1. In the second tab, open `/faculty` and sign in with the
   faculty token printed by `run_local.sh`.
2. Open the `LOCAL01` session.
3. Show the transcript, the score with per-dimension reasons and
   evidence turn numbers, and play the recording.
   Say: "Every mark cites transcript turns, and the recording
   replays from the same offsets. Scoring runs in the background
   after the viva, so if the score is not there yet, wait a few
   seconds and reload."
4. Do NOT claim that reloading the student Done screen shows the
   result — on main, Done has no result display. The result is
   faculty-side until Done gains a result display.

## What the demo proves

- Student: join → rules → Ready → mic check (voice only) →
  typed + voice answers → barge-in → clean finish → closing
  words on Done.
- Faculty: transcript + recording + auditable score in one place.
- Fairness: same structure for every student, server-owned clock,
  no duplicate answers on retry.

## If something goes wrong live

| Problem | Say / do |
|---|---|
| Microphone denied | "The browser blocked the mic — the student types instead." Switch to `?mode=text` and show the typed answer. |
| Voice does not connect | "Voice is down — the typed flow is the same viva." Keep typing. |
| Wrong code | Show the kind error message; join again with the printed code. |
| Score not shown yet | "Scoring runs after the viva." Reload the faculty session in a few seconds. |
| Done shows no score | By design on main — Done shows closing words + Sign out only. Show the score on the faculty side. |

## Rehearsal (per docs/qa/BHAVESH_REPLY.md)

- Run this script 3 times before presenting.
- Produce 1 clean recording + 1 backup. Keep recordings OUTSIDE
  git (never commit audio).
- Freeze: Fri 16 Oct 18:00 — defect fixes only after.

## Left out (intentionally) + why

- The old doc's hard-coded faculty token. Tokens are per-run
  output from `run_local.sh`; hard-coding one is wrong and a
  secret-handling risk. Read it from the terminal each time.
- Old button labels: "I am taking a viva", "I accept", "check
  your microphone", "Check microphone", "Use voice instead",
  "Start voice", "Hold to talk", "Hold to interrupt", and the
  "Viva finished" label. They do not match main's routes /
  labels / `?mode=` param. Mode is chosen by `?mode=`, not by
  an in-screen voice button.
- The old doc's "Done shows the closing message and transcript"
  and "reload Done to show the result". Main's Done shows
  closing words + Sign out, no score. Promising a result on
  Done would mislead the audience.
- The old doc's "release the results, then reload Done" faculty
  step. It depends on a Done result display that main does not
  have. Dropped until Done gains result display.
- Implementation detail (hooks, API calls, protocol messages).
  A demo script narrates what the audience sees, not how it
  is built.
