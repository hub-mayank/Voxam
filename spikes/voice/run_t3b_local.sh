#!/bin/bash
# T3b local legs (real Ollama LLM, real clips). From the worktree root, venv active, clean git tree. About 20 minutes; leave the machine idle.
set -e
cd "$(dirname "$0")"
for s in A B E F; do python bench_e2e_real.py --stack $s; done
python bench_wer.py
python bench_long.py
