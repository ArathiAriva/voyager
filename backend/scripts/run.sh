#!/usr/bin/env bash
set -euo pipefail

PROFILES_DIR="$(cd "$(dirname "$0")/../profiles" && pwd)"

usage() {
  echo "Usage: $0 --profile <name>"
  echo ""
  echo "Available profiles:"
  for f in "$PROFILES_DIR"/.env.*; do
    echo "  ${f##*.env.}"
  done
  exit 1
}

PROFILE=""
PORT=8000
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile|-p)
      PROFILE="$2"
      shift 2
      ;;
    --port)
      PORT="$2"
      shift 2
      ;;
    *)
      usage
      ;;
  esac
done

[[ -z "$PROFILE" ]] && usage

ENV_FILE="$PROFILES_DIR/.env.$PROFILE"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Error: profile '$PROFILE' not found (no $ENV_FILE)"
  echo ""
  usage
fi

set -a
# shellcheck source=/dev/null
source "$ENV_FILE"
set +a

EXISTING_PIDS=$(lsof -ti tcp:"$PORT" 2>/dev/null || true)
if [[ -n "$EXISTING_PIDS" ]]; then
  echo "Killing existing process(es) on port $PORT (PIDs $EXISTING_PIDS)"
  echo "$EXISTING_PIDS" | xargs kill
fi

echo "Starting Voyager backend with profile: $PROFILE on port $PORT"
cd "$(dirname "$0")/.."
exec uvicorn app.main:app --reload --port "$PORT"
