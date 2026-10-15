# Volunteer consent and register (TJ-1)

Status: preparation only. The register starts with a header and **zero volunteers**. TJ-1 is not complete until the
operational fields are filled and at least 15 genuine signed forms exist outside Git: 10 volunteers for marked
vivas and 5 for demos, as required by [the team plan](../TEAM_PLAN.md). Do not invent signatures, rows or opt-ins.

## Before recording

1. Mayank/MSOT reviews the [form](consent_form_template.md). Tejas confirms the contact email, exact private storage
   location/custodian, access list, selected local/cloud providers including fallbacks, and the planned activities.
   Complete those details and the recording/deletion dates on each private copy before it is signed.
2. Assign a unique study ID such as `V001`; use it for the test roster and evidence filenames. Keep the name-to-ID
   mapping with the signed forms outside Git. Avoid institutional student IDs in volunteer tests.
3. Explain the form, answer questions and obtain testing consent before capturing a clip or starting a viva.
   Give the volunteer a copy. Declining public use must not exclude them from private testing.
4. Add a register row only after checking the signed form. The application additionally records rules acceptance
   for a viva; it stores no signed form or public-demo opt-in, so keep those checks with the coordinator.

## Register format

[register.csv](register.csv) has exactly these columns:

| Column | Meaning |
|---|---|
| `volunteer_id` | Unique study ID, linked to the signed form only through the private mapping |
| `date` | Actual date the testing consent was signed, in `YYYY-MM-DD` format |
| `public_demo` | `yes` only when the optional public-demo box is explicitly checked on the signed form; otherwise `no` |

Record one row per genuinely consented volunteer. Do not add names, email addresses, institutional IDs, signatures,
recordings, file-sharing URLs, session tokens or access codes. Use lowercase `yes`/`no`; do not leave this value blank.
Study IDs are pseudonymous while a private mapping exists. Register rows can persist in Git history: tell volunteers
this and remove the private mapping on deletion. Keep withdrawal and retention tracking privately, outside Git;
remove a withdrawn volunteer's row from the current register and stop using that material.

## Collection and use

Track the 10 marked-viva and 5 demo participants, private form location, session/clip IDs, actual recording dates,
one-month deletion due dates and any withdrawal in a private coordinator record. Those details do not belong in
this register. For a later recording session, complete a new private form with its actual details and schedule that
session's deletion separately. Keep each signed proof with the material it covers; retain any shared private identity
mapping only until all associated retained material is removed.

Before sharing any public demo, recheck the signed optional checkbox and current permission. If five public-demo
participants are needed, recruit five willing opt-ins; do not change a `no` to meet the target. Faculty CSV exports
include names/student IDs: prepare only the agreed evidence, remove unnecessary identifying fields and check its
permission before sharing. Do not publish raw exports or signed forms.

The system has no automatic deletion workflow. The coordinator schedules removal of audio, transcripts, scores,
private clips, reference/hypothesis text, exports, signed forms/mappings and related copies; handle logs, caches,
backups and provider-held copies as applicable. `scripts/run_local.sh --fresh` is **not** participant-data deletion:
it removes the local database/code file but leaves audio and other copies.

Before every PR, run `backend/.venv/bin/python scripts/check_secrets.py` and inspect the diff for real participant
data. Ignore rules and the key scanner do not detect or protect every signed form, recording or personal detail.
