#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 - <<'PY'
import os
import secrets
import tempfile
from pathlib import Path
path = Path('.env')
if not path.exists():
    raise SystemExit('Run setup.sh first.')
lines = path.read_text().splitlines()
values = [line.split('=', 1)[1] for line in lines if line.startswith('KENO_SEARCH_SECRET=')]
secret = values[-1] if values and len(values[-1]) >= 32 else secrets.token_hex(32)
lines = [line for line in lines if not line.startswith('KENO_SEARCH_SECRET=')]
fd, name = tempfile.mkstemp(dir='.', prefix='.env-live-')
try:
    with os.fdopen(fd, 'w') as file:
        file.write('\n'.join(lines + ['KENO_SEARCH_SECRET=' + secret]) + '\n')
    os.chmod(name, 0o600)
    os.replace(name, path)
finally:
    Path(name).unlink(missing_ok=True)
PY
docker compose --profile live up -d --build lookup search
echo 'Lookup services started. Weather and search stay disabled until enabled in the console Tools section.'
