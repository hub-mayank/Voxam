#!/usr/bin/env bash
# T8 live evidence runs on Groq gpt-oss-20b, in the order of value. Run from the repo root on a clean, committed tree, after the
# free-tier token window has room (python -c below prints the headroom). Roughly 70k tokens in total.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-backend/.venv/bin/python}
MODEL=${MODEL:-groq:openai/gpt-oss-20b}
export FREE_TIER_MAX_WAIT_S=${FREE_TIER_MAX_WAIT_S:-120}
$PY - <<'PYEOF'
import sys; sys.path.insert(0, "backend")
from app.envfile import load_env; load_env()
from app.llm import budget
used = budget.token_usage().get("groq|openai/gpt-oss-20b", {}).get("tpd", 0)
print(f"groq gpt-oss-20b tokens used in the last 24 h: {used} of {int(0.9 * 200000)} allowed; this run needs about 70000")
PYEOF
echo "== 1/3 follow-up quality on the live interviewer model"
$PY scripts/followup_personas.py --llm "$MODEL" --tag groq_gpt-oss-20b
echo "== 2/3 fairness and safety probes (10 injections, 3 off-topic, 2 language-mixing)"
$PY scripts/fairness_probes.py --llm "$MODEL" --live --tag groq_gpt-oss-20b
echo "== 3/3 scorer consistency, 5 transcripts x 3 runs (prompt $($PY -c 'import sys; sys.path.insert(0,"backend"); from app.scorer import SCORER_PROMPT_VERSION as v; print(v)'))"
$PY scripts/consistency.py --llm "$MODEL" --live --runs 3 --tag groq_gpt-oss-20b_v3
