#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
DEPLOY_ROOT="${DEPLOY_ROOT:-$HOME/dataset-review-agent}"
RUNTIME_DIR="$DEPLOY_ROOT/runtime"
PID_FILE="$RUNTIME_DIR/platform.pid"
RUNNER_PID_FILE="$RUNTIME_DIR/platform_runner.pid"
LOG_DIR="$RUNTIME_DIR/logs"
OUT_LOG="$LOG_DIR/platform.out.log"
ERR_LOG="$LOG_DIR/platform.err.log"

mkdir -p "$LOG_DIR"
cd "$DEPLOY_ROOT"
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"
if [ -f "$DEPLOY_ROOT/.env" ]; then
  set -a
  . "$DEPLOY_ROOT/.env"
  set +a
fi

echo $$ > "$RUNNER_PID_FILE"
while true; do
  echo "[$(date '+%F %T')] starting uvicorn" >> "$OUT_LOG"
  "$DEPLOY_ROOT/.venv/bin/python" -m uvicorn dataset_review_platform_backend.app.main:app --host 0.0.0.0 --port 8017 >> "$OUT_LOG" 2>> "$ERR_LOG" &
  CHILD=$!
  echo "$CHILD" > "$PID_FILE"
  wait "$CHILD" || true
  rm -f "$PID_FILE"
  echo "[$(date '+%F %T')] uvicorn exited, restarting in 5 seconds" >> "$OUT_LOG"
  sleep 5
  if [ -f "$RUNTIME_DIR/stop.flag" ]; then
    rm -f "$RUNTIME_DIR/stop.flag"
    break
  fi
done
rm -f "$RUNNER_PID_FILE"
