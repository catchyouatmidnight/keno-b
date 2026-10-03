#!/bin/sh
set -eu
# Laya 0.3.26 normalizes tokenizer_config.json for current Transformers. Keep
# the downloaded checkpoint immutable and patch a private runtime copy instead.
rm -rf /tmp/laya
mkdir -p /tmp/laya
cp -a /models-source/. /tmp/laya/
exec uvicorn server:app --host 0.0.0.0 --port 8000 --workers 1 --no-access-log
