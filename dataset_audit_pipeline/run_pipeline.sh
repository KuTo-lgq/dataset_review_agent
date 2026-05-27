#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_PATH="${1:-$SCRIPT_DIR/config.example.json}"

python3 "$SCRIPT_DIR/run_audit.py" --config "$CONFIG_PATH"

mapfile -t PIPELINE_META < <(
python3 - "$CONFIG_PATH" <<'PY'
import json
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
cfg = json.loads(config_path.read_text(encoding="utf-8"))
output_root = Path(cfg.get("output_root", "."))
run_name = cfg.get("run_name")
if run_name:
    run_dir = output_root / run_name
else:
    candidates = [p for p in output_root.iterdir() if p.is_dir()]
    run_dir = max(candidates, key=lambda p: p.stat().st_mtime) if candidates else output_root

model_cfg = cfg.get("model_risk", {})
print(run_dir)
print("true" if model_cfg.get("enabled") else "false")
print(model_cfg.get("endpoint", ""))
print(model_cfg.get("model_name", ""))
print(model_cfg.get("api_key_env", "DATASET_AUDIT_API_KEY"))
PY
)

RUN_DIR="${PIPELINE_META[0]}"
MODEL_RISK_ENABLED="${PIPELINE_META[1]}"
MODEL_ENDPOINT="${PIPELINE_META[2]}"
MODEL_NAME="${PIPELINE_META[3]}"
API_KEY_ENV="${PIPELINE_META[4]}"

if [[ "$MODEL_RISK_ENABLED" == "true" && -n "$MODEL_ENDPOINT" && -n "$MODEL_NAME" ]]; then
  if [[ -n "${!API_KEY_ENV:-}" ]]; then
    python3 "$SCRIPT_DIR/generate_llm_analysis_report.py" \
      --run-dir "$RUN_DIR" \
      --endpoint "$MODEL_ENDPOINT" \
      --model-name "$MODEL_NAME" \
      --api-key-env "$API_KEY_ENV"
  else
    echo "[pipeline] Skip llm_analysis_report.md because env '$API_KEY_ENV' is not set."
  fi
else
  echo "[pipeline] Skip llm_analysis_report.md because model_risk is disabled or config is incomplete."
fi
