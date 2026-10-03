#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ $# == 2 && $2 == --replace ]] || { echo 'Usage: bash scripts/restore.sh /absolute/path/to/backup.sqlite3 --replace' >&2; exit 1; }
backup=$(realpath "$1")
[[ -f $backup ]] || { echo 'Backup file not found.' >&2; exit 1; }
docker compose stop backend
# Keep a local rollback copy before replacing existing data.
if [[ -f data/keno.db ]]; then
  docker compose run --rm --no-deps backend python scripts/database.py backup "/data/before-restore-$(date -u +%Y%m%dT%H%M%SZ).sqlite3" || {
    echo 'Could not create rollback backup. Restore aborted; backend remains stopped.' >&2; exit 1;
  }
fi
docker compose run --rm --no-deps -v "$backup:/restore.sqlite3:ro" backend python scripts/database.py restore /restore.sqlite3 --replace
docker compose up -d backend
echo 'Restored assistant. Access key remains the one in this installation’s .env.'
