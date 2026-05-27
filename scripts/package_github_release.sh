#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SUITE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT_DIR="${1:-$SUITE_ROOT/dist/dataset-review-agent}"

rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

copy_dir() {
  cp -R "$SUITE_ROOT/$1" "$OUTPUT_DIR/$1"
}

copy_file() {
  if [ -f "$SUITE_ROOT/$1" ]; then
    mkdir -p "$(dirname "$OUTPUT_DIR/$1")"
    cp "$SUITE_ROOT/$1" "$OUTPUT_DIR/$1"
  fi
}

copy_dir "dataset_audit_pipeline"
copy_dir "dataset_review_platform_backend"
copy_dir "deploy"
copy_dir "scripts"

copy_file ".env.example"
copy_file ".gitignore"
copy_file "LICENSE"
copy_file "README.md"
copy_file "requirements.txt"
copy_file "requirements.platform.txt"
copy_file "start_review_platform.ps1"
copy_file "start_review_platform.sh"
copy_file "askpass.example.cmd"

rm -rf \
  "$OUTPUT_DIR/dataset_review_platform_backend/data" \
  "$OUTPUT_DIR/dataset_review_platform_backend/exports" \
  "$OUTPUT_DIR/dataset_review_platform_backend/generated_configs" \
  "$OUTPUT_DIR/dataset_review_platform_backend/imported_runs" \
  "$OUTPUT_DIR/dataset_review_platform_backend/task_logs" \
  "$OUTPUT_DIR/dataset_audit_pipeline/runs" \
  "$OUTPUT_DIR/dataset_audit_pipeline/configs" \
  "$OUTPUT_DIR/dataset_audit_pipeline/FULL_GUIDE.md" \
  "$OUTPUT_DIR/dataset_audit_pipeline/OPERATION_GUIDE.md" \
  "$OUTPUT_DIR/deploy/server/.env.runtime"

find "$OUTPUT_DIR" -type d \( -name "__pycache__" -o -name ".pytest_cache" \) -prune -exec rm -rf {} +
find "$OUTPUT_DIR" -type f \( -name "*.pyc" -o -name "*.pyo" -o -name "*.log" -o -name "*.tmp" \) -delete

cat > "$OUTPUT_DIR/PUBLISHING.md" <<'EOF'
GitHub 发布目录已生成。

建议下一步：
1. 进入当前目录初始化新的 Git 仓库
2. 检查 .env.example 和 deploy/server/platform.env.example
3. 按你的开源仓库名更新 README 顶部标题或徽章
EOF

printf 'Release folder ready: %s\n' "$OUTPUT_DIR"
