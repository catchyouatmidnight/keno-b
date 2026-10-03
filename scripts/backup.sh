#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
umask 077
destination="backups/keno-$(date -u +%Y%m%dT%H%M%SZ).sqlite3"
docker compose exec -T backend python scripts/database.py backup /tmp/keno-backup.sqlite3
docker compose cp backend:/tmp/keno-backup.sqlite3 "$destination"
docker compose exec -T backend rm /tmp/keno-backup.sqlite3
echo "Saved $destination (private profile, memories and conversations; no API key or model weights)."
