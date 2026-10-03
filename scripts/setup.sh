#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v docker >/dev/null || { echo 'Install Docker Engine and the Compose plugin first.' >&2; exit 1; }
docker compose version >/dev/null
mkdir -p models data backups
if [[ ! -e .env ]]; then
  umask 077
  cp .env.example .env
  token=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')
  sed -i "s/replace-with-at-least-32-random-characters/$token/" .env
  echo 'Created .env with a random server access key.'
else
  echo 'Keeping existing .env and personal data.'
fi
chmod 600 .env
# Container runs as UID 10001. Never reset or replace existing data.
if [[ $(stat -c '%u' data) != 10001 ]]; then
  if [[ $(id -u) == 0 ]]; then chown -R 10001:10001 data;
  else sudo chown -R 10001:10001 data; fi
fi
chmod 700 data
if [[ ${1:-} == --download-model ]]; then
  python3 scripts/download-model.py
else
  echo 'Import your GGUF into models/, or run: python3 scripts/download-model.py'
fi
echo 'Setup ready. Start with: docker compose up -d --build'
echo 'Open http://localhost:8080 and paste KENO_API_KEY from .env.'
