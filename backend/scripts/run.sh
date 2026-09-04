#!/usr/bin/env bash
set -euo pipefail

PROFILES_DIR="$(cd "$(dirname "$0")/../profiles" && pwd)"

usage() {
  echo "Usage: $0 --profile <name> [--port <port>] [--planner single|multi]"
  echo ""
  echo "  --planner  Which architecture handles planning-intent messages."
  echo "             multi (default) = LangGraph multi-agent graph"
  echo "             single          = single-agent tool-call loop"
  echo "             Overrides VOYAGER_PLANNER from the profile/env."
  echo ""
  echo "Available profiles:"
  for f in "$PROFILES_DIR"/.env.*; do
    echo "  ${f##*.env.}"
  done
  exit 1
}

PROFILE=""
PORT=8060
PLANNER=""
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
    --planner)
      PLANNER="$2"
      if [[ "$PLANNER" != "single" && "$PLANNER" != "multi" ]]; then
        echo "Error: --planner must be 'single' or 'multi' (got '$PLANNER')"
        exit 1
      fi
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

# Applied after sourcing the profile, so an explicit --planner wins over a
# VOYAGER_PLANNER baked into the profile file.
if [[ -n "$PLANNER" ]]; then
  export VOYAGER_PLANNER="$PLANNER"
fi

EXISTING_PIDS=$(lsof -ti tcp:"$PORT" 2>/dev/null || true)
if [[ -n "$EXISTING_PIDS" ]]; then
  echo "Killing existing process(es) on port $PORT (PIDs $EXISTING_PIDS)"
  echo "$EXISTING_PIDS" | xargs kill
fi

echo "Starting Voyager backend with profile: $PROFILE on port $PORT (planner: ${VOYAGER_PLANNER:-multi})"
cd "$(dirname "$0")/.."
exec uvicorn app.main:app --reload --port "$PORT"
