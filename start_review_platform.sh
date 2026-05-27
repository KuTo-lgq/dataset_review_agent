#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"
python -m uvicorn dataset_review_platform_backend.app.main:app --host 127.0.0.1 --port 8017
