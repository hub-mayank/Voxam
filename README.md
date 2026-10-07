# AI Viva (Step 1: text-mode core)
    docker compose up -d                 # postgres + redis
    cd backend && pip install -r requirements.txt
    python -m pytest tests               # state machine, policy, audit fields
    python -m app.cli --llm mock         # text viva, writes session.jsonl
    # Gemini: export GEMINI_API_KEY=... GEMINI_MODEL=...; python -m app.cli --llm gemini
Keys never go in the repo.

## Step 2: scorer
    python -m app.score tests/personas/strong.jsonl --llm mock
    export GEMINI_API_KEY=...            # never commit; see .env.example
    python -m app.list_models            # pick GEMINI_MODEL from this list
    export GEMINI_MODEL=<name>; python -m app.score session.jsonl --llm gemini
    python scripts/compare.py marks.csv  # AI vs human: gap + correlation

## Model benchmark
    python scripts/bench_models.py gemini-2.5-flash gemini-3.5-flash --runs 3   # raw CSV -> results/
