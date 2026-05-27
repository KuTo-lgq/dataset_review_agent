#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
DEPLOY_ROOT="${DEPLOY_ROOT:-$HOME/dataset-review-agent}"
RUNTIME_DIR="$DEPLOY_ROOT/runtime"
PID_FILE="$RUNTIME_DIR/platform.pid"
RUNNER_PID_FILE="$RUNTIME_DIR/platform_runner.pid"
STOP_FLAG="$RUNTIME_DIR/stop.flag"

is_running() {
  if [ -f "$RUNNER_PID_FILE" ]; then
    PID="$(cat "$RUNNER_PID_FILE")"
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
      return 0
    fi
  fi
  return 1
}

case "${1:-status}" in
  start)
    mkdir -p "$RUNTIME_DIR"
    if is_running; then
      echo "already running"
      exit 0
    fi
    nohup "$DEPLOY_ROOT/deploy/server/run_platform_forever.sh" >/dev/null 2>&1 &
    sleep 2
    if is_running; then
      echo "started"
      exit 0
    fi
    echo "failed to start" >&2
    exit 1
    ;;
  stop)
    touch "$STOP_FLAG"
    if [ -f "$PID_FILE" ]; then
      PID="$(cat "$PID_FILE")"
      kill "$PID" 2>/dev/null || true
    fi
    if [ -f "$RUNNER_PID_FILE" ]; then
      PID="$(cat "$RUNNER_PID_FILE")"
      kill "$PID" 2>/dev/null || true
    fi
    echo "stopped"
    ;;
  restart)
    "$0" stop || true
    sleep 2
    "$0" start
    ;;
  status)
    if is_running; then
      echo "running"
      if [ -f "$PID_FILE" ]; then
        echo "uvicorn_pid=$(cat "$PID_FILE")"
      fi
      if [ -f "$RUNNER_PID_FILE" ]; then
        echo "runner_pid=$(cat "$RUNNER_PID_FILE")"
      fi
    else
      echo "stopped"
      exit 1
    fi
    ;;
  logs)
    tail -n 80 "$RUNTIME_DIR/logs/platform.out.log" "$RUNTIME_DIR/logs/platform.err.log"
    ;;
  *)
    echo "usage: $0 {start|stop|restart|status|logs}" >&2
    exit 1
    ;;
esac
