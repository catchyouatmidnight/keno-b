#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
umask 077
destination="backups/keno-$(date -u +%Y%m%dT%H%M%SZ).sqlite3"
# /tmp in the backend is a tmpfs, which `docker compose cp` cannot read; stream the snapshot out instead.
docker compose exec -T backend rm -f /tmp/keno-backup.sqlite3
docker compose exec -T backend python scripts/database.py backup /tmp/keno-backup.sqlite3 >/dev/null
trap 'rm -f "$destination.part"' EXIT
docker compose exec -T backend cat /tmp/keno-backup.sqlite3 > "$destination.part"
docker compose exec -T backend rm /tmp/keno-backup.sqlite3
python3 -c 'import sqlite3,sys; sys.exit(sqlite3.connect(sys.argv[1]).execute("PRAGMA integrity_check").fetchone()[0]!="ok")' "$destination.part" || { echo 'Backup failed its integrity check; nothing saved.' >&2; exit 1; }
mv "$destination.part" "$destination"
echo "Saved $destination (private profile, memories and conversations; no API key or model weights)."
