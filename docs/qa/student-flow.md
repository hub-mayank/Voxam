# Student flow: screens, states and the words a student reads (BH-0)

What is built (`frontend/src/student/`), written so a person can review the wording without reading code. The code and this file
must say the same thing: the error sentences below are generated from `copy.ts` and a test checks that every API error code has
one. Change a sentence in `copy.ts`, then here.

## The path

`/student` join → `/student/rules` rules and consent → `/student/ready` choose how to answer → (`/student/mic-check`) →
`/student/viva` → `/student/done`. The server decides where a student is: after a join, a reload or the deadline the app moves
to the screen the server's status says, so the browser never has to guess.

| Screen | What the student can do | Rules |
|---|---|---|
| **Join** | Viva ID (pre-filled from `/student?viva=ID`), student ID, access code (hidden, "Show the code" tick) | Continue is off while a field is empty, while a request is running, and for the wait the server asks for after wrong codes (button reads "Wait 7 s"). Fields are kept after an error. |
| **Rules and consent** | Read the server's rules text, tick one box, "I agree, continue" or "Not now" | The button stays off until the box is ticked. The rules version the student saw is the one sent with the consent. |
| **Ready** | Choose: type, push to talk, hands-free. Start. | Typing is always available and needs no microphone. Voice modes stay locked until the microphone check passed. The clock starts only on "Start the viva". |
| **Mic check** | Listen for 2.5 s, record a 3 s sample, play it back, confirm "I can hear myself" | Passes only after the student confirms (or when the browser cannot play back, after a good level). Denied or no device: plain steps and "Type my answers instead". Nothing is saved. |
| **Viva, typing** | Question, answer box, "Send answer", conversation log | Send is off while empty, busy, or when time is up. A failed send keeps the text; the retry uses the same sequence number, so an answer is never stored twice. At zero the box locks and the server is asked what happens next. |
| **Viva, voice** | "Begin the viva", hold to talk (button or Space/Enter) or "I am done speaking", level meter in words, state words, typed answer as a fallback | Hold-to-talk works only while the interviewer is listening. Lost connection says so and the timer keeps running; three automatic retries (1, 2, 4 s), then a "Reconnect" button. A blocked microphone never blocks the viva: typing stays on. |
| **Done** | Read the closing words, see the result and feedback once faculty released it, "Sign out" | Until release (or while marking) it says so kindly and offers "Check again". The total, each rubric dimension in words and the feedback with its turn numbers are shown; if a person changed the total, it says so. "Sign out" clears the saved session. |

## Timer words (screen reader and sighted)
The digits are not read every second. "One minute left.", "Ten seconds left." and "Time is up." are announced once each; the
last minute turns amber and says "(less than a minute)" so colour is never the only signal.

## Error sentences
The exact error code is written to the browser console for support. It is never shown. Every sentence tells the student what to do next.

| Code | When | What the student reads | What the screen does |
|---|---|---|---|
| `unauthorized` | saved session or token no longer valid | “Your session is no longer valid. Please sign in again with your ID and access code.” | back to the join screen |
| `forbidden` | someone else's session or wrong role | “This page is not available for your account. Please sign in again.” | back to the join screen |
| `not_found` | viva or session does not exist | “We could not find this viva. Check the viva ID and try again.” | stay on join, keep the fields |
| `method_not_allowed` | should not happen | “Something went wrong on our side. Please reload the page.” | reload |
| `validation_error` | a field is missing or malformed | “Please check what you typed and try again.” | stay, keep the fields |
| `invalid_upload` | faculty-side only | “Something went wrong on our side. Please reload the page.” | reload |
| `invalid_credentials` | wrong student ID or access code | “That ID or access code did not work. Check both and try again.” | stay on join, keep the fields; no retry timer until the server sends one |
| `already_exists` | faculty-side only | “Something went wrong on our side. Please reload the page.” | reload |
| `invalid_state` | action not allowed in the current state (for example start before consent) | “That step is not available right now. We are checking where you are.” | read the status again and move to the screen it says |
| `session_ended` | the viva is over; the code and token are dead | “Your viva is complete. You can safely close this page.” | end screen |
| `deadline_passed` | answer was too late and was not recorded | “Time is up. Your last answer was not saved. Your viva is now complete.” | end screen with the server's closing words; the typed text is not sent |
| `bad_client_seq` | the answer count is out of step (double send, or another tab) | “We need to resync this question before continuing.” | read the status again; the screen shows the server's current question |
| `rules_version_mismatch` | faculty changed the rules after the student joined | “The rules were updated. Please sign in again to read and accept them.” | sign out and join again to read the new rules |
| `range_not_satisfiable` | faculty-side only (audio) | “Something went wrong on our side. Please reload the page.” | reload |
| `audio_not_available` | faculty-side only (audio) | “Something went wrong on our side. Please reload the page.” | reload |
| `results_not_released` | result asked for before faculty released it | “Your result is not available yet.” | the Done screen says the result is not released yet and offers "Check again" |
| `rate_limited` | too many wrong codes; `details.retry_after_ms` says how long | “Too many tries. Please wait a moment before trying again.” | disable Continue and show the countdown from the server's value |
| `provider_unavailable` | the AI model is down; retry the same request | “The interviewer is busy for a moment. Your answer is safe: please try again.” | keep the typed answer; the Send button works again at once; same request is retried with the same sequence number |
| `internal_error` | a bug on our side | “Something went wrong on our side. Please try again. If it keeps happening, tell your invigilator.” | keep the typed answer; try again |
| `network_error` | the browser could not reach the server | “Connection lost. Check your internet and try again. Your viva timer may keep running.” | keep the typed answer; try again; the timer keeps running |

## Not built (on purpose)
- A visible history after a reload: the server returns the current question, not the earlier answers, so the log restarts. The
  answers are saved; this is display only.
- Integrity signals (tab switch, multiple voices): no policy exists yet (`docs/PRIVACY.md`).

## BH-0 delta — additional wording

### Additional voice error sentences

Voice errors come from the voice session. Retryable: yes means the student may try again; the screen says so instead of showing a code.

| Code | Retryable | Exact student sentence |
|---|---|---|
| `replaced` | yes | “Another window or tab is now listening. This one has stopped. Go to the tab or window that is now listening.” |
| `stt_failed` | yes | “We could not understand that answer. Please say it again.” |
| `no_speech` | yes | “We did not hear anything. Please speak again, and keep close to the microphone.” |
| `bad_message` | yes | “That message could not be sent. Please try again, or type your answer instead.” |

### Additional sentence rules

- Never blame the student for a server or provider failure.
- Never reveal another student's data, a code, or how many tries remain.
- If the screen cannot tell the student what to do, it says to reload once and then ask faculty — and the PR notes that gap.
