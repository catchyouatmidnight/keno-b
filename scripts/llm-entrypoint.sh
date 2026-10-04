#!/bin/sh
set -eu
# Preserve argument boundaries. Never evaluate settings as shell commands.
case "${VISION_ENABLED:-true}" in
  true)
    set -- "$@" --mmproj "/models/${MMPROJ_FILE:?Vision needs MMPROJ_FILE}" --no-mmproj-offload --image-max-tokens 1024
    ;;
  false) ;;
  *) echo 'VISION_ENABLED must be true or false' >&2; exit 1 ;;
esac
exec /app/llama-server "$@"
