#!/bin/sh
set -eu

default_model="${MODEL_FILE:-Qwen3.5-2B-Q4_K_M.gguf}"

select_model() {
  model="$default_model"
  if [ -r /runtime/model-selection.txt ]; then
    candidate="$(tr -d '\r\n' </runtime/model-selection.txt)"
    case "$candidate" in
      *[!A-Za-z0-9._-]*|''|*/*) ;;
      *.gguf)
        if [ -f "/managed-models/$candidate" ] || [ -f "/models/$candidate" ]; then model="$candidate"; fi
        ;;
    esac
  fi
  printf '%s\n' "$model"
}

append_vision() {
  case "${VISION_ENABLED:-true}" in
    true)
      set -- "$@" --mmproj "/models/${MMPROJ_FILE:?Vision needs MMPROJ_FILE}" --no-mmproj-offload --image-max-tokens 1024
      ;;
    false) ;;
    *) echo 'VISION_ENABLED must be true or false' >&2; exit 1 ;;
  esac
  printf '%s\0' "$@"
}

# An explicit --model supplied by an operator keeps the old one-shot behavior.
explicit_model=false
for arg in "$@"; do
  if [ "$arg" = "--model" ] || [ "$arg" = "-m" ]; then explicit_model=true; break; fi
done
if [ "$explicit_model" = true ]; then
  case "${VISION_ENABLED:-true}" in
    true) set -- "$@" --mmproj "/models/${MMPROJ_FILE:?Vision needs MMPROJ_FILE}" --no-mmproj-offload --image-max-tokens 1024 ;;
    false) ;;
    *) echo 'VISION_ENABLED must be true or false' >&2; exit 1 ;;
  esac
  exec /app/llama-server "$@"
fi

case "${VISION_ENABLED:-true}" in
  true) set -- "$@" --mmproj "/models/${MMPROJ_FILE:?Vision needs MMPROJ_FILE}" --no-mmproj-offload --image-max-tokens 1024 ;;
  false) ;;
  *) echo 'VISION_ENABLED must be true or false' >&2; exit 1 ;;
esac

child=""
active=""

stop_child() {
  if [ -n "$child" ] && kill -0 "$child" 2>/dev/null; then
    kill -TERM "$child" 2>/dev/null || true
    wait "$child" 2>/dev/null || true
  fi
}
shutdown() {
  stop_child
  exit 0
}
trap shutdown TERM INT

start_server() {
  model="$(select_model)"
  if [ -f "/managed-models/$model" ]; then model_path="/managed-models/$model"; else model_path="/models/$model"; fi
  /app/llama-server --model "$model_path" --alias "$model" "$@" &
  child=$!
  active="$model"
  tmp="/runtime/active-model.txt.tmp"
  printf '%s\n' "$model" >"$tmp"
  mv "$tmp" /runtime/active-model.txt
  echo "Keno runtime loading $model" >&2
}

start_server "$@"
while :; do
  sleep 1
  if ! kill -0 "$child" 2>/dev/null; then
    status=0
    wait "$child" || status=$?
    exit "$status"
  fi
  desired="$(select_model)"
  if [ "$desired" != "$active" ]; then
    echo "Keno runtime switching $active -> $desired" >&2
    stop_child
    start_server "$@"
  fi
done
