# API changelog

One line per change to `docs/openapi.json` after G0. Additive changes are allowed with a line here and a message to the frontend team (Parth, Bhavesh); removals, renames and type changes need Mayank's approval. Newest first.

- 2026-10-08 (T5, cosmetic) The product name is Voxam: `info.title` is now "Voxam API" and the description says Voxam. No route or schema changed.
- 2026-10-08 (T5, additive) `POST /faculty/vivas/{viva_id}/questions/approve {question_ids?}`: turns `ai-draft` questions into `bank` and sets `approved_by` from the token; omit `question_ids` to approve every draft; idempotent; unknown id is 404 (nothing changes); 409 `invalid_state` (reason `students_joined`) once any student has joined; returns the whole bank (`QuestionList`). `Question.approved_by` description now also covers approved drafts. New schema `ApproveQuestions`.
- 2026-10-08 (T1c, additive) `QuestionIn.source` (optional, `bank` or `ai-draft`, default `bank`; optional `source` CSV column): lets a bank written by an AI be marked as a draft that faculty must approve; `Question.source` returns it.
- 2026-10-08 (T2b, additive) `POST /faculty/sessions/{sid}/review {note}`: logs a review (reviewer from the token) and clears `needs_review`; `SessionDetail.reviews` lists them; `needs_review` is now cleared by a review or an override.
- 2026-10-08 (T2b, additive) `POST /faculty/sessions/{sid}/rescore` (202): only from `failed` or `scored`; session returns to `ended` and a scoring job is queued.
- 2026-10-08 (T2b, additive) `Turn.model` and `Turn.prompt_version`: which model served an AI turn (null for canned turns) and the interviewer prompt version.
- 2026-10-08 (T2b, additive) `Viva.results_visible_to_students` (default false; also optional in `VivaCreate`) and `PATCH /faculty/vivas/{viva_id}` to change it.
- 2026-10-08 (T2b, additive) `GET /student/sessions/{sid}/result`: total, dimension scores and feedback; 403 `results_not_released` until faculty release results.
- 2026-10-08 (T2b, additive) Error codes `audio_not_available` (404, no recording, e.g. text mode) and `results_not_released` (403).
- 2026-10-07 (T2a) Initial frozen contract (G0).
