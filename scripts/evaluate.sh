#!/usr/bin/env bash
# Real local models, temporary backend/database; optional user PDF stays local.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ $# -eq 0 ]]; then
  docker compose exec -T backend python /app/scripts/evaluate.py
elif [[ $# -eq 2 && "$1" == "--pdf" ]]; then
  test -f "$2"
  target="/tmp/keno-eval-$(python3 -c 'import uuid; print(uuid.uuid4().hex)').pdf"
  trap 'docker compose exec -T --user root backend rm -f "$target" >/dev/null 2>&1 || true' EXIT
  docker compose cp "$2" "backend:$target"
  docker compose exec -T --user root backend chown 10001:10001 "$target"
  docker compose exec -T --user root backend chmod 0600 "$target"
  docker compose exec -T -e "KENO_EVAL_PDF=$target" -e "KENO_EVAL_PDF_NAME=$(basename "$2")" backend python /app/scripts/evaluate.py
else
  echo 'Usage: bash scripts/evaluate.sh [--pdf path/to/document.pdf]' >&2
  exit 2
fi
