#!/bin/sh
set -eu
# Select an installed model without editing .env. The backend writes only a safe basename.
model="${MODEL_FILE:-Qwen3.5-2B-Q4_K_M.gguf}"
if [ -r /runtime/model-selection.txt ]; then
  candidate="$(tr -d '\r\n' </runtime/model-selection.txt)"
  case "$candidate" in
    *[!A-Za-z0-9._-]*|''|*/*) echo 'Ignoring invalid staged model selection' >&2 ;;
    *.gguf)
      if [ -f "/managed-models/$candidate" ] || [ -f "/models/$candidate" ]; then model="$candidate"; fi
      ;;
  esac
fi
if [ -f "/managed-models/$model" ]; then model_path="/managed-models/$model"; else model_path="/models/$model"; fi
set -- --model "$model_path" --alias "$model" "$@"
# Preserve argument boundaries. Never evaluate settings as shell commands.
case "${VISION_ENABLED:-true}" in
  true)
    set -- "$@" --mmproj "/models/${MMPROJ_FILE:?Vision needs MMPROJ_FILE}" --no-mmproj-offload --image-max-tokens 1024
    ;;
  false) ;;
  *) echo 'VISION_ENABLED must be true or false' >&2; exit 1 ;;
esac
exec /app/llama-server "$@"
