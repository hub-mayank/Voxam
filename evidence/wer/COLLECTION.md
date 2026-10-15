# TJ-3: collect consented speech clips and exact references

**Preparation only.** [refs.csv](refs.csv) contains a header and no collected clips. TJ-3 remains incomplete until
there are at least **20 distinct recordings: 10 Indian-accented technical English and 10 Hinglish**, with consent,
private audio and checked references. Repeating a clip with another model/language setting does not add a clip.

## Before recording

1. Use the [consent form](../../docs/consent/consent_form_template.md) and
   [collection workflow proposed in PR #31](https://github.com/hub-mayank/ai-viva/pull/31). Complete the private storage/custodian, access list,
   selected processors, recording and deletion dates on the form before signing. Obtain consent for short speech
   clips; public-demo permission is separate. Cloud speech needs its own disclosed permission.
2. Assign a pseudonymous volunteer ID and link it to the signed form only in private storage. Use that ID in
   `speaker_id`; use separate unique clip IDs for recordings. Never include names, institutional IDs or contact details.
3. Choose a private shared-drive folder and locally accessible copy **outside the repository**. Restrict access to
   the consented recipients. Keep original audio, converted copies, forms, identity mappings and withdrawals there.
   Schedule manual deletion under the [privacy policy](../../docs/PRIVACY.md); ignore rules are not a privacy control.

## Record and prepare references

- Follow [RECORDING.md](../../spikes/voice/RECORDING.md): quiet room, mic about 20 cm away, normal speaking speed and
  natural pauses; about 15–30 seconds per clip. Its seven prompts are useful starting points, not a completed TJ-3 dataset.
- Collect varied technical explanations across volunteers and both language groups. Record naturally; do not keep
  retaking a clip just to improve the recognizer's result. Record whether clips are read aloud or spontaneous privately.
- Listen to each original clip and write the **words actually spoken**, including repetitions/stumbles. Do this
  independently of the STT output. Do not correct grammar, remove difficult words or substitute the expected script.
- Use Roman-script Hinglish references consistently; keep original references private when they contain identifiers.
  Choose nonidentifying technical material for any agreed repository/submission evidence. Never publish identifying
  reference/hypothesis text or access-controlled drive links. Editing words after measurement changes the dataset.
- Save/export a private mono PCM16 16-kHz WAV for the local evaluator. On macOS, replace these sample paths:

  ```bash
  afconvert -f WAVE -d LEI16@16000 -c 1 "/absolute/private/clips/clip.m4a" "/absolute/private/clips/clip.wav"
  ```

  Keep both copies outside Git. The evaluator checks WAV format and declared payload length; it does not convert files.

## Manifest

Fill [refs.csv](refs.csv) with one row per genuinely collected clip. Work on a private copy first when references
or local paths need privacy review. Quote CSV fields containing commas, quotes or line breaks; double embedded quotes.

| Column | Meaning |
|---|---|
| `clip` | Unique ID: 1–64 characters; starts with a letter/digit, then letters/digits/underscore/dot/hyphen |
| `kind` | Exactly `english` or `hinglish`; the English set must be Indian-accented technical speech |
| `reference` | Nonempty exact reference transcript; punctuation-only references are rejected |
| `audio_path` | Local private WAV path; required for `--local`, optional for saved-hypothesis comparison |
| `language_setting` | `en`, `hi` or `auto`; a row overrides `--language`, blank uses the command's default (`en`) |
| `speaker_id` | Pseudonymous volunteer ID; supported as collection metadata, not a recognizer setting |

Relative audio paths resolve against the manifest's directory, not the shell directory. A shared-drive web URL
cannot be decoded: obtain an authorized local file. A private manifest with absolute paths can stay outside Git;
the tool accepts it with `--refs`. Never commit private usernames, local folder details or identity mappings.

## Evaluate after collection

From the repository root, use `backend/.venv/bin/python`. The evaluator needs the existing `jiwer` and
`indic-transliteration` spike libraries; local recognition also needs configured whisper.cpp CLI/model files.
Use `WHISPER_CLI`, `VOICE_MODELS_DIR`, `WHISPER_SIZE` and `WHISPER_THREADS` if your local installation differs.
These commands are instructions for the operator, not evidence that recognition has already run.

```bash
backend/.venv/bin/python scripts/wer.py --refs evidence/wer/refs.csv --local --language en --out results/wer_local.csv
```

Use a private `--refs` path and a private output directory when transcripts are not approved for repository evidence.
Local recognition uses real installed whisper.cpp and labels the sidecar `provider=live`; that label does not verify
consent, audio authenticity, accent, speaker diversity or the minimum clip counts. No cloud speech API is called.

For saved hypotheses, make a separate CSV with `clip,text`; IDs must exactly match the manifest, with no duplicates
or unknown/missing clips. Empty `text` is valid and counts as recognition failure. Replace the paths/model label:

```bash
backend/.venv/bin/python scripts/wer.py --refs evidence/wer/refs.csv --hypotheses "/absolute/private/hypotheses.csv" --model "actual-recognizer-label" --out results/wer_offline.csv
```

This only compares saved text. Its default `provider=stub` must remain labelled offline; it does not prove a new
recognition run. `--provider mock` is for explicitly mocked hypotheses. Never copy references into hypotheses to
manufacture accuracy. The untouched header-only manifest intentionally fails evaluation rather than producing results.

## Completion and sharing checks

- Check signed consent against every speaker, 20 unique clips, and at least 10 clips in each required group.
  Confirm the references against the audio and record the limitations of read-aloud or single-speaker material.
- Preserve each actual result CSV and its adjacent `.meta.json`; they record source hashes, normalization version,
  model, execution mode and sample units. Keep private source copies available only to agreed reviewers.
- Read strict WER first. Corpus WER uses summed errors divided by summed reference words within each model/language
  group; do not average clip percentages or merge different language settings. Skeleton WER is optimistic and can
  hide real errors. Live does not mean the minimum submission evidence is satisfied.
- Before a PR, inspect the diff for audio, signatures, identifiers and unapproved transcript text, then run
  `backend/.venv/bin/python scripts/check_secrets.py`. Only agreed nonidentifying evidence belongs in Git.
  A draft PR may contain this guide and empty manifest; keep it marked preparation until real evidence exists.
