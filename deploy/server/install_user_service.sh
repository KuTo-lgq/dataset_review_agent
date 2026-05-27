#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
DEPLOY_ROOT="${DEPLOY_ROOT:-$HOME/dataset-review-agent}"
RUNTIME_DIR="$DEPLOY_ROOT/runtime"
CRON_MARKER="# dataset-review-platform"

mkdir -p "$DEPLOY_ROOT"
mkdir -p "$RUNTIME_DIR/platform_generated_configs" "$RUNTIME_DIR/platform_runs" "$RUNTIME_DIR/logs"

if [ ! -d "$DEPLOY_ROOT/.venv" ]; then
  python3 -m venv "$DEPLOY_ROOT/.venv"
fi

"$DEPLOY_ROOT/.venv/bin/python" -m pip install --upgrade pip >/dev/null
"$DEPLOY_ROOT/.venv/bin/pip" install -r "$DEPLOY_ROOT/requirements.platform.txt"

if [ ! -f "$DEPLOY_ROOT/.env" ]; then
  cp "$DEPLOY_ROOT/deploy/server/platform.env.example" "$DEPLOY_ROOT/.env"
fi

chmod +x "$DEPLOY_ROOT/deploy/server/platform_ctl.sh" "$DEPLOY_ROOT/deploy/server/run_platform_forever.sh"

TMP_CRON="$(mktemp)"
crontab -l 2>/dev/null | grep -v "$CRON_MARKER" > "$TMP_CRON" || true
echo "@reboot $DEPLOY_ROOT/deploy/server/platform_ctl.sh start $CRON_MARKER" >> "$TMP_CRON"
crontab "$TMP_CRON"
rm -f "$TMP_CRON"

"$DEPLOY_ROOT/deploy/server/platform_ctl.sh" start
"$DEPLOY_ROOT/deploy/server/platform_ctl.sh" status
