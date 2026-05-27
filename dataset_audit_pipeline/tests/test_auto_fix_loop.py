#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO9Wl1QAAAAASUVORK5CYII="
)


def make_label(
    *,
    status: str,
    skip_reason: str,
    primary: str,
    customer_count: int,
    contains_child: bool,
    child_age_bucket: str,
) -> dict:
    return {
        "status": status,
        "skip_reason": skip_reason,
        "l2_relationship": {"primary": primary},
        "l3_scene": {"scene_tag": "dining"},
        "l4_auxiliary_tags": {
            "customer_count": customer_count,
            "group_gender": "mixed",
            "contains_child": contains_child,
            "child_age_bucket": child_age_bucket,
            "contains_elder": False,
            "young_group": False,
        },
        "ops_tags": [],
        "service_actions": [],
        "reasoning": "test",
        "confidence": 0.9,
    }


class AutoFixHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        content = payload["messages"][0]["content"][0]["text"]
        if "order_id: order-status-fix" in content:
            response = make_label(
                status="SKIP",
                skip_reason="EMPTY_TABLE",
                primary="unknown",
                customer_count=0,
                contains_child=False,
                child_age_bucket="none",
            )
        else:
            response = make_label(
                status="VALID",
                skip_reason="OTHER",
                primary="family",
                customer_count=2,
                contains_child=False,
                child_age_bucket="none",
            )
        wrapped = {"choices": [{"message": {"content": json.dumps(response, ensure_ascii=False)}}]}
        raw = json.dumps(wrapped).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def write_dataset(root: Path) -> Path:
    dataset_dir = root / "dataset"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    image_paths = [dataset_dir / "tiny_1.png", dataset_dir / "tiny_2.png"]
    for image_path in image_paths:
        image_path.write_bytes(PNG_BYTES)
    samples = [
        (
            "order-status-fix",
            make_label(
                status="VALID",
                skip_reason="EMPTY_TABLE",
                primary="family",
                customer_count=2,
                contains_child=False,
                child_age_bucket="none",
            ),
        ),
        (
            "order-rule-fix",
            make_label(
                status="VALID",
                skip_reason="OTHER",
                primary="family",
                customer_count=2,
                contains_child=False,
                child_age_bucket="0_6",
            ),
        ),
    ]
    with (dataset_dir / "train.jsonl").open("w", encoding="utf-8") as fh:
        for idx, (order_id, label) in enumerate(samples):
            sample = {
                "image": str(image_paths[idx]),
                "conversations": [
                    {
                        "from": "human",
                        "value": (
                            f"store_id: s1\nscene_id: scene-{order_id}\n"
                            f"captured_at: 2026-05-18T10:00:00\norder_id: {order_id}\n"
                            "business_date: 2026-05-18\n请分析主桌。"
                        ),
                    },
                    {"from": "assistant", "value": json.dumps(label, ensure_ascii=False)},
                ],
            }
            fh.write(json.dumps(sample, ensure_ascii=False) + "\n")
    (dataset_dir / "val.jsonl").write_text("", encoding="utf-8")
    return dataset_dir


def write_config(root: Path, dataset_dir: Path, endpoint: str) -> Path:
    config = {
        "dataset_name": "auto_fix_test",
        "dataset_dir": str(dataset_dir),
        "splits": ["train.jsonl"],
        "output_root": str(root / "runs"),
        "run_name": "auto_fix_test_run",
        "manual_review": {"max_items": 10},
        "auto_fix": {
            "enabled": True,
            "use_rule_fixes": True,
            "use_model_fixes": True,
            "max_rounds": 1,
            "max_rows_per_round": 10,
            "target_static_issue_count": 0,
            "target_static_issue_ratio": 0.0,
            "endpoint": endpoint,
            "model_name": "mock-model",
            "timeout": 10,
            "max_image_side": 256,
            "request_gap_ms": 0,
            "temperature": 0,
            "max_tokens": 256,
        },
        "model_risk": {"enabled": False},
    }
    config_path = root / "config.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return config_path


def main() -> int:
    project_root = Path(__file__).resolve().parents[2]
    with TemporaryDirectory(prefix="dataset_auto_fix_test_") as tmp:
        root = Path(tmp)
        dataset_dir = write_dataset(root)
        server = ThreadingHTTPServer(("127.0.0.1", 0), AutoFixHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            config_path = write_config(root, dataset_dir, f"http://127.0.0.1:{server.server_port}/api/chat/completions")
            subprocess.run(
                [sys.executable, str(project_root / "dataset_audit_pipeline" / "run_audit.py"), "--config", str(config_path)],
                cwd=str(project_root),
                check=True,
            )
            run_dir = root / "runs" / "auto_fix_test_run"
            auto_fix_summary = json.loads((run_dir / "auto_fix_summary.json").read_text(encoding="utf-8"))
            run_summary = json.loads((run_dir / "run_summary.json").read_text(encoding="utf-8"))
            fixed_train = (run_dir / "auto_fixed_dataset" / "train.jsonl").read_text(encoding="utf-8").splitlines()
            fixed_rows = [json.loads(line) for line in fixed_train if line.strip()]
            labels = [json.loads(row["conversations"][1]["value"]) for row in fixed_rows]

            assert auto_fix_summary["enabled"] is True, auto_fix_summary
            assert auto_fix_summary["rule_fix_rows"] >= 1, auto_fix_summary
            assert auto_fix_summary["accepted_model_rows"] >= 1, auto_fix_summary
            assert auto_fix_summary["final_static_issue_count"] == 0, auto_fix_summary
            assert run_summary["static_issue_count"] == 0, run_summary
            assert any(label["status"] == "SKIP" and label["l2_relationship"]["primary"] == "unknown" for label in labels), labels
            assert any(label["l4_auxiliary_tags"]["child_age_bucket"] == "none" for label in labels), labels
            print("PASS auto fix loop test")
            return 0
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
