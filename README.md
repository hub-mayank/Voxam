# AI Viva (Step 1: text-mode core)
    docker compose up -d                 # postgres + redis
    cd backend && pip install -r requirements.txt
    python -m pytest tests               # state machine, policy, audit fields
    python -m app.cli --llm mock         # text viva, writes session.jsonl
    # Gemini: export GEMINI_API_KEY=... GEMINI_MODEL=...; python -m app.cli --llm gemini
Keys never go in the repo.
