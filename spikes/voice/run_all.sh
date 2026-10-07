#!/bin/bash
# Regenerate EVERY result in results/voice_spike/ from the current commit (about 30 minutes; leave the machine idle: it measures latency).
# From the worktree root, venv active, git tree clean (so each sidecar carries a clean git_sha):   bash spikes/voice/run_all.sh
set -e
cd "$(dirname "$0")"
python fetch_models.py
python make_synth.py
python bench_vad.py
python bench_stt.py --models base,small,medium
python bench_tts.py
bash run_all_e2e.sh
python bench_stt_concurrency.py
python transport/proof_ws.py --turns 12
[ -d data/clips ] && ls data/clips/c0*.m4a >/dev/null 2>&1 && python bench_wer.py || echo "no real clips yet: skipping bench_wer.py (see RECORDING.md)"
