# Guide for the human markers (scoring accuracy, T8)

Thank you for marking. Your marks are compared with the AI's, so the one rule is: **mark independently and do not look at the AI's marks.**

## What you receive
A private folder `for_markers/` with one sub-folder per viva (`P01`, `P02`, ...): `packet.md` (the questions with their key points, the rubric, the
conversation with turn numbers and times) and `audio.wav`, plus one `marking_sheet.csv` to fill in. Names and any AI output are not included.

## What to do for each viva (about 10 to 15 minutes)
1. Read `packet.md`, listen to `audio.wav` wherever the transcript looks wrong or unclear (the times in the packet are offsets into the recording).
2. Rate the **student only** on five dimensions, **whole numbers from 0 to 5**: conceptual understanding (30%), depth and reasoning (25%), problem
   solving (20%), practical/project knowledge (15%), communication (10%). Anchors for 5/5 are in the packet.
3. Accent, grammar and mixing Hindi with English must **not** lower the first four dimensions; they may affect communication only for clarity and structure.
4. "I don't know" earns 0 for that topic only; do not punish other dimensions twice.
5. In `notes`, write one or two reasons with the turn numbers you relied on.
6. `total_100` = 6 x conceptual + 5 x depth + 4 x problem + 3 x practical + 2 x communication (all fives = 100). You can leave it blank; it is checked.

## Rules that keep it fair
- Work alone; do not compare with the other marker until both sheets are sent back.
- Do not change a rating after sending the sheet; if you want to correct something, send a second file and say why.
- Do not share the recordings or names outside the group; they are private test material, kept for one month.

## When you are done
Send back `marking_sheet.csv` (rename it to your own name, for example `vikas.csv`). The coordinator then runs
`python scripts/compare_markers.py --mapping <_private/mapping.csv> --sheet vikas.csv --sheet devesh.csv`, which reports each marker's gap to the AI, their
agreement with each other, and the correlation. Two markers also tell us how much humans disagree, which is the realistic ceiling for the AI.
