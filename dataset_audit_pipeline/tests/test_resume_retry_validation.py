#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import shutil
import subprocess
import sys
import threading
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO9Wl1QAAAAASUVORK5CYII="
)


def make_label(status: str, skip_reason: str, primary: str, count: int) -> dict:
    return {
        "status": status,
        "skip_reason": skip_reason,
        "l2_relationship": {"primary": primary},
        "l3_scene": {"scene_tag": "dining"},
        "l4_auxiliary_tags": {
            "customer_count": count,
            "group_gender": "mixed",
            "contains_child": False,
            "child_age_bucket": "none",
            "contains_elder": False,
            "young_group": False,
        },
        "ops_tags": [],
        "service_actions": [],
        "reasoning": "test",
        "confidence": 0.9,
    }


class MockHandler(BaseHTTPRequestHandler):
    counters: dict[str, int] = defaultdict(int)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        payload = json.loads(body.decode("utf-8"))
        content = payload["messages"][0]["content"][0]["text"]
        order_id = ""
        for line in content.splitlines():
            if line.startswith("order_id:"):
                order_id = line.split(":", 1)[1].strip()
                break
        MockHandler.counters[order_id] += 1
        attempt = MockHandler.counters[order_id]

        if order_id == "order-retry-http" and attempt == 1:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"temporary"}')
            return

        if order_id == "order-retry-json" and attempt == 1:
            response = {"status": "VALID", "l2_primary": "family"}
        elif order_id == "order-always-invalid":
            response = {"status": "VALID", "l2_primary": "family"}
        elif order_id == "order-retry-http":
            response = make_label("VALID", "OTHER", "family", 2)
        else:
            response = make_label("VALID", "OTHER", "family", 2)

        wrapped = {"choices": [{"message": {"content": json.dumps(response, ensure_ascii=False)}}]}
        raw = json.dumps(wrapped).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def write_dataset(root: Path) -> None:
    dataset_dir = root / "dataset"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    image_path = dataset_dir / "tiny.png"
    image_path.write_bytes(PNG_BYTES)

    rows = [
        ("order-retry-json", make_label("VALID", "OTHER", "family", 2)),
        ("order-retry-http", make_label("VALID", "OTHER", "family", 2)),
        ("order-always-invalid", make_label("VALID", "OTHER", "family", 2)),
    ]
    train_path = dataset_dir / "train.jsonl"
    val_path = dataset_dir / "val.jsonl"
    with train_path.open("w", encoding="utf-8") as fh:
        for order_id, label in rows:
            sample = {
                "image": str(image_path),
                "conversations": [
                    {
                        "from": "human",
                        "value": f"store_id: s1\nscene_id: scene-{order_id}\ncaptured_at: 2026-05-18T10:00:00\norder_id: {order_id}\nbusiness_date: 2026-05-18\n请分析主桌。",
                    },
                    {"from": "assistant", "value": json.dumps(label, ensure_ascii=False)},
                ],
            }
            fh.write(json.dumps(sample, ensure_ascii=False) + "\n")
    val_path.write_text("", encoding="utf-8")


def write_config(root: Path, endpoint: str) -> Path:
    config = {
        "dataset_name": "resume_retry_validation_test",
        "dataset_dir": str(root / "dataset"),
        "splits": ["train.jsonl"],
        "output_root": str(root / "runs"),
        "run_name": "resume_retry_validation",
        "manual_review": {"max_items": 3},
        "model_risk": {
            "enabled": True,
            "endpoint": endpoint,
            "model_name": "mock-model",
            "selection": "all",
            "max_rows": 3,
            "timeout": 10,
            "request_gap_ms": 0,
            "temperature": 0,
            "max_tokens": 256,
            "resume": True,
            "max_attempts": 2,
            "retry_backoff_seconds": 0,
            "retry_request_errors": True,
            "retry_validation_failures": True,
        },
    }
    config_path = root / "config.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return config_path


def run_pipeline(config_path: Path, project_root: Path) -> None:
    subprocess.run(
        [sys.executable, str(project_root / "dataset_audit_pipeline" / "run_audit.py"), "--config", str(config_path)],
        cwd=str(project_root),
        check=True,
    )


def main() -> int:
    project_root = Path(__file__).resolve().parents[2]
    with TemporaryDirectory(prefix="dataset_audit_test_") as tmp:
        root = Path(tmp)
        write_dataset(root)

        server = ThreadingHTTPServer(("127.0.0.1", 0), MockHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            endpoint = f"http://127.0.0.1:{server.server_port}/api/chat/completions"
            config_path = write_config(root, endpoint)

            run_pipeline(config_path, project_root)

            run_dir = root / "runs" / "resume_retry_validation"
            summary = json.loads((run_dir / "model_risk_summary.json").read_text(encoding="utf-8"))
            predictions = [json.loads(line) for line in (run_dir / "model_risk_predictions.jsonl").read_text(encoding="utf-8").splitlines() if line]
            attempts = [json.loads(line) for line in (run_dir / "model_risk_attempts.jsonl").read_text(encoding="utf-8").splitlines() if line]

            assert summary["success_rows"] == 2, summary
            assert summary["failed_rows"] == 1, summary
            assert summary["validation_issue_rows"] == 1, summary
            assert summary["total_attempts"] == 6, summary
            assert len(predictions) == 3, predictions
            assert len(attempts) == 6, attempts
            assert any(row["status"] == "failed" and row["validation_issues"] for row in predictions), predictions

            attempts_before = len(attempts)
            counters_before = dict(MockHandler.counters)
            run_pipeline(config_path, project_root)

            summary_rerun = json.loads((run_dir / "model_risk_summary.json").read_text(encoding="utf-8"))
            attempts_after = [json.loads(line) for line in (run_dir / "model_risk_attempts.jsonl").read_text(encoding="utf-8").splitlines() if line]

            assert summary_rerun["skipped_success_rows"] == 2, summary_rerun
            assert summary_rerun["skipped_exhausted_rows"] == 1, summary_rerun
            assert summary_rerun["total_attempts"] == 0, summary_rerun
            assert len(attempts_after) == attempts_before, (attempts_before, len(attempts_after))
            assert dict(MockHandler.counters) == counters_before, (MockHandler.counters, counters_before)
            print("PASS resume/retry/validation test")
            return 0
        finally:
            server.shutdown()
            server.server_close()
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
