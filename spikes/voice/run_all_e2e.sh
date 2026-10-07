#!/bin/bash
# Re-run every E2E variant the report quotes (about 8 minutes). From the worktree root with the venv active: bash spikes/voice/run_all_e2e.sh
cd "$(dirname "$0")" || exit 1
for s in A B C D; do python bench_e2e.py --stack $s; done
python bench_e2e.py --stack B --stt-mode segmented
python bench_e2e.py --stack B --hangover 900
python bench_e2e.py --stack B --hangover 400
python bench_e2e.py --stack B --tag _repeat2
