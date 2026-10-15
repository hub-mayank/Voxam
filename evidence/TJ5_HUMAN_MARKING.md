# TJ-5: ten volunteer vivas and independent human marking

**Status: preparation only. No volunteer sessions, human marks or accuracy results are supplied by this guide.**
TJ-5 still needs ten genuine volunteers to complete vivas on Mayank's Mac and an independently assigned human
marker. Tejas must arrange a faculty or peer marker with Mayank; no marker has been assumed here.

## Before the first viva

1. Complete the [consent form](../docs/consent/consent_form_template.md) using the
   [workflow proposed in PR #31](https://github.com/hub-mayank/ai-viva/pull/31). Confirm signed testing consent, the private
   storage/custodian, who can access the material, the actual providers and each recording's one-month manual
   deletion date. Public-demo permission is separate and is unnecessary for private human marking.
2. Use volunteer IDs in the test roster. Keep the name-to-ID, session-ID and consent mapping outside Git. Choose
   ten distinct volunteers; launcher seed accounts and scripted personas are not volunteer evidence.
3. Mayank prepares the cohort and an approved question bank, and starts `scripts/run_local.sh` on his Mac.
   Verify the displayed voice, interviewer and scorer providers before use. A mock/stub run demonstrates plumbing;
   identify it explicitly and do not present its marks as accuracy evidence for a real model. Disclose cloud routes
   and fallbacks before collecting recordings. Do not run `--fresh` against a cohort containing retained sessions.
4. Agree the same rubric and marking procedure with the human marker before viewing any AI scores. Record the
   chosen cohort, rubric version, question bank, scorer prompt/model and any fallback privately. Keep versions
   fixed for the comparison; record changed protocols or retakes separately.

## Run and prepare a private marking packet

- Each volunteer accepts the app's rules and completes their viva. Record the real session UUID, volunteer ID,
  date, completion status and any interruption in the private coordinator log. Preserve the audio and transcript.
- Confirm the recording can be replayed and the transcript contains the actual questions and answers. Record
  missing material or failed sessions honestly; arrange a consented retake when necessary. Do not discard weak
  answers or select only successful-looking scores. Count distinct complete volunteer vivas, not retry attempts.
- The coordinator prepares a private packet containing the questions, approved bank key points, rubric, student
  answers, transcript turn numbers and recording/timestamps. Hide AI scores, grading reasons, feedback, confidence flags, faculty overrides and
  other human ratings from the marker. The ordinary faculty detail screen is not a blind marking view; this
  separation is a manual coordinator step.
- Keep the AI output separately. Freeze the human's first ratings before revealing AI grading or discussing
  disagreements. Corrections or later reconciled marks belong in separate private records, not an overwritten
  first-rating sheet.

## Human marking sheet

Copy the existing [header-only marking sheet](../docs/marking_sheet.csv) into the agreed private location. Keep
the repository copy empty. Use one primary rating row per session; the `marker` column may use a stable private
marker ID whose identity/appointment date is recorded by the coordinator. Do not invent example volunteers,
marker identities, session UUIDs or scores.

Use the existing rubric's five dimensions on the 0–5 scale. Agree any additional rating anchors before marking;
the descriptions below are the configuration's existing 5/5 anchors, not a new scoring rubric.

| Sheet column | Weight | Existing 5/5 anchor |
|---|---:|---|
| `conceptual_0_5` | 30% | Explains core concepts correctly in own words |
| `depth_0_5` | 25% | Handles follow-ups, explains trade-offs and why |
| `problem_0_5` | 20% | Breaks applied problem into steps, sound approach |
| `practical_0_5` | 15% | Speaks concretely about what they built and how |
| `communication_0_5` | 10% | Clear, structured, concise answers |

Use integer ratings from 0 to 5, matching the scorer prompt. Technical marks must reflect technical content:
accent, grammar or language mixing must not reduce the first four dimensions. The current scorer prompt permits
mixed language to affect Communication only; agree its clarity/structure anchors before marking and apply the same
rubric to the human and AI comparison. The human should listen when transcription is uncertain.
In `notes`, give brief reasons with student turn numbers/timestamps; avoid unrelated personal information.

Compute the human `total_100` from the five ratings, not a separate impression of performance:

```text
total_100 = 6*conceptual + 5*depth + 4*problem + 3*practical + 2*communication
```

The weights sum to 100%; all five ratings of 5 yield 100. Preserve rating date, rubric version, packet location
and any missing evidence in the private coordinator log; these are not new columns in the existing sheet.

## Comparison handoff after ratings are frozen

`scripts/compare.py` expects a different CSV: `session_id,ai_total,human_total`. Do not pass the marking sheet
directly to it. The coordinator must prepare a separate private comparison file after the blind ratings are locked:

1. Obtain the AI snapshot for the same session UUIDs. The faculty CSV has `student_id` and `ai_total`, but lacks
   `session_id`; use the private cohort/session mapping to match it. Check for duplicate IDs and ambiguous matches.
2. Set `human_total` from the frozen sheet's `total_100`. Set `ai_total` from the original AI aggregate, not the
   faculty-overridden `effective_total`. Include each of the ten session UUIDs exactly once, with finite totals
   from 0 to 100 and human totals verified against the weighted formula. Resolve missing matches before analysis.
3. Run `backend/.venv/bin/python scripts/compare.py /absolute/private/path/comparison.csv`. Report the actual
   sample size, mean absolute gap, signed bias and Pearson correlation printed by the script. Do not run it on an
   empty template. If either series has no variance, correlation is undefined (`nan`); do not replace it with zero.
4. Keep raw recordings, names, signed forms, mapping, human notes and raw faculty exports outside Git. Any
   submission or public material must match consent and be reviewed for identifiers. Aggregate results need
   explicit provenance and sample size before the report can describe this as completed accuracy evidence.

## Completion evidence still needed

Ten distinct consented volunteer vivas on Mayank's Mac; replayable audio and transcripts; an appointed independent
human marker; ten first-rating rows; and a checked comparison for those same sessions. Empty templates and this
guide do not meet that requirement. Schedule manual deletion of the private packets and related copies under
the agreed consent workflow; `scripts/run_local.sh --fresh` leaves audio and is not a deletion procedure.

Sources: [TJ-5](../docs/TEAM_PLAN.md), [required accuracy evidence](../docs/SPEC.md),
[rubric weights](../config/viva.config.json), [scorer rules](../backend/app/prompts/scorer-v3.txt),
[weighted total calculation](../backend/app/scorer.py), [comparison script](../scripts/compare.py),
[faculty export fields](../backend/app/services/faculty.py), [privacy note](../docs/PRIVACY.md).
