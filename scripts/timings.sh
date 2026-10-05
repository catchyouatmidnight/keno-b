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
              "laya_call_count": route.get("call_count"),
              "tool_family": route.get("tool_family"),
              "tool_decision": route.get("decisions", {}).get("tool_family"),
              "tool_need": route.get("decisions", {}).get("tool_need"),
              "tool_policy": route.get("tool_policy"),
              "effort_policy": route.get("effort_policy"),
              "thinking": route.get("thinking"),
              "thinking_decision": route.get("decisions", {}).get("thinking"),
              "uncertain": route.get("uncertain")}
    for key in ("context_prepare_seconds", "model_first_delta_seconds",
                "model_first_reasoning_seconds", "hidden_reasoning_seconds", "model_first_token_seconds",
                "first_token_seconds", "total_seconds", "elapsed_seconds",
                "tool_seconds", "tool_model_seconds", "tool_execution_seconds", "tool_planning_rounds", "tool_planning_mode", "tool_save_required", "tool_thinking_budget",
                "answer_source", "prompt_tokens", "history_turns", "history_summary", "retrieved_history", "thinking_budget", "finish_reason"):
        output[key] = data.get(key)
    print(json.dumps(output, indent=2))
PY
