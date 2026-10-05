#!/usr/bin/env bash
# Show performance metadata only: no messages, filenames, memories or API keys.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose exec -T backend python - <<'PY'
import json
import os
import sqlite3
from pathlib import Path

path = Path(os.environ.get("KENO_DB", "data/keno.db")).resolve()
with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
    rows = connection.execute(
        "SELECT metadata FROM turns WHERE status='complete' ORDER BY rowid DESC LIMIT 3"
    ).fetchall()
if not rows:
    print("No completed responses yet.")
for index, (raw,) in enumerate(rows, 1):
    data = json.loads(raw)
    route = data.get("route", {})
    output = {"recent_response": index,
              "laya_seconds": route.get("seconds"),
              "laya_question_count": route.get("question_count"),
              "thinking": route.get("thinking"),
              "thinking_decision": route.get("decisions", {}).get("thinking"),
              "uncertain": route.get("uncertain")}
    for key in ("context_prepare_seconds", "model_first_delta_seconds",
                "model_first_reasoning_seconds", "hidden_reasoning_seconds", "model_first_token_seconds",
                "first_token_seconds", "total_seconds", "elapsed_seconds",
                "tool_seconds", "tool_model_seconds", "tool_execution_seconds", "tool_planning_rounds",
                "answer_source", "prompt_tokens", "history_turns", "history_summary", "retrieved_history", "thinking_budget", "finish_reason"):
        output[key] = data.get(key)
    print(json.dumps(output, indent=2))
PY
