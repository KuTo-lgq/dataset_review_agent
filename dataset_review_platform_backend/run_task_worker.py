from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dataset_review_platform_backend.app.main import execute_audit_task


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: run_task_worker.py <task_id>", file=sys.stderr)
        return 2
    execute_audit_task(int(sys.argv[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
