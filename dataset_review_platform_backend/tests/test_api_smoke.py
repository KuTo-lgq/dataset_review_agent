from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient


def make_label(status: str = "VALID", skip_reason: str = "OTHER") -> dict:
    return {
        "status": status,
        "skip_reason": skip_reason,
        "l2_relationship": {"primary": "family"},
        "l3_scene": {"scene_tag": "dining"},
        "l4_auxiliary_tags": {
            "customer_count": 2,
            "group_gender": "mixed",
            "contains_child": False,
            "child_age_bucket": "none",
            "contains_elder": False,
            "young_group": False,
        },
        "ops_tags": [],
        "service_actions": [],
        "reasoning": "test",
        "confidence": 0.8,
    }


def build_fixture(root: Path) -> tuple[Path, Path]:
    dataset_dir = root / "dataset"
    run_dir = root / "run"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)

    image_path = dataset_dir / "sample.jpg"
    image_path.write_bytes(
        bytes.fromhex(
            "89504E470D0A1A0A0000000D4948445200000001000000010802000000907753DE0000000C49444154789C6360600000000400010D0A2DB40000000049454E44AE426082"
        )
    )

    train_sample = {
        "image": str(image_path),
        "conversations": [
            {"from": "human", "value": "order_id: order-1\nscene_id: scene-1\ncaptured_at: 2026-05-18T10:00:00"},
            {"from": "assistant", "value": json.dumps(make_label(), ensure_ascii=False)},
        ],
    }
    val_sample = {
        "image": str(image_path),
        "conversations": [
            {"from": "human", "value": "order_id: order-2\nscene_id: scene-2\ncaptured_at: 2026-05-18T10:05:00"},
            {"from": "assistant", "value": json.dumps(make_label(status="VALID", skip_reason="OTHER"), ensure_ascii=False)},
        ],
    }
    (dataset_dir / "train.jsonl").write_text(json.dumps(train_sample, ensure_ascii=False) + "\n", encoding="utf-8")
    (dataset_dir / "val.jsonl").write_text(json.dumps(val_sample, ensure_ascii=False) + "\n", encoding="utf-8")

    run_summary = {
        "dataset_name": "demo",
        "dataset_dir": str(dataset_dir),
        "run_name": "demo_run",
        "output_dir": str(run_dir),
        "total_rows": 2,
        "static_issue_count": 1,
        "consistency_issue_count": 0,
        "model_prediction_rows": 1,
        "model_flagged_rows": 1,
        "review_pack_image_count": 1,
    }
    (run_dir / "run_summary.json").write_text(json.dumps(run_summary, ensure_ascii=False, indent=2), encoding="utf-8")

    risk_row = {
        "split": "train",
        "line_no": 1,
        "image": str(image_path),
        "order_id": "order-1",
        "scene_id": "scene-1",
        "captured_at": "2026-05-18T10:00:00",
        "risk_score": 95,
        "risk_bucket": "bad_label",
        "static_issues": ["invalid_status"],
        "consistency_issues": [],
        "model_issues": ["model_mismatch:status"],
        "model_validation_issues": [],
        "model_mismatch_fields": ["status"],
        "label": make_label(),
        "model_prediction": make_label(status="SKIP", skip_reason="EMPTY_TABLE"),
    }
    (run_dir / "risk_ranked_rows.jsonl").write_text(json.dumps(risk_row, ensure_ascii=False) + "\n", encoding="utf-8")
    return dataset_dir, run_dir


def wait_task(client: TestClient, task_id: int, timeout_seconds: float = 30.0) -> dict:
    deadline = time.time() + timeout_seconds
    last_payload = None
    while time.time() < deadline:
        poll = client.get(f"/api/tasks/{task_id}")
        assert poll.status_code == 200, poll.text
        last_payload = poll.json()
        if last_payload["status"] in {"completed", "failed"}:
            break
        time.sleep(0.5)
    assert last_payload is not None
    return last_payload


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="review_platform_test_", ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        dataset_dir, run_dir = build_fixture(root)
        os.environ["DATASET_REVIEW_DB_PATH"] = str(root / "review.db")
        project_root = Path(__file__).resolve().parents[2]
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

        from dataset_review_platform_backend.app.main import create_app

        with TestClient(create_app()) as client:

            health = client.get("/health")
            assert health.status_code == 200

            imported = client.post("/api/intake", json={"path": str(run_dir)})
            assert imported.status_code == 200, imported.text
            imported_payload = imported.json()
            assert imported_payload["mode"] == "imported_run"
            run_id = imported_payload["run"]["run_id"]

            runs = client.get("/api/runs")
            assert runs.status_code == 200
            assert runs.json()["items"][0]["run_name"] == "demo_run"

            items = client.get(f"/api/runs/{run_id}/items")
            assert items.status_code == 200
            assert items.json()["total"] == 1
            item_id = items.json()["items"][0]["id"]

            decision = client.post(
                f"/api/items/{item_id}/decision",
                json={
                    "decision": "confirm_bad_label",
                    "action": "replace_label",
                    "corrected_label_json": make_label(status="SKIP", skip_reason="EMPTY_TABLE"),
                    "owner": "tester",
                    "notes": "fix status",
                },
            )
            assert decision.status_code == 200, decision.text
            assert decision.json()["decision"]["action"] == "replace_label"
            assert len(decision.json()["decision_history"]) == 1

            decision_2 = client.post(
                f"/api/items/{item_id}/decision",
                json={
                    "decision": "confirm_bad_label",
                    "action": "replace_label",
                    "corrected_label_json": make_label(status="SKIP", skip_reason="LOW_QUALITY"),
                    "owner": "reviewer_b",
                    "notes": "second pass",
                },
            )
            assert decision_2.status_code == 200, decision_2.text
            payload_2 = decision_2.json()
            assert payload_2["decision"]["action"] == "replace_label"
            assert len(payload_2["decision_history"]) == 2

            filtered = client.get(
                f"/api/runs/{run_id}/items",
                params={"action": "replace_label", "owner": "reviewer_b", "issue_source": "static"},
            )
            assert filtered.status_code == 200, filtered.text
            assert filtered.json()["total"] == 1

            reports = client.get(f"/api/runs/{run_id}/reports")
            assert reports.status_code == 200, reports.text

            agent_analysis = client.get(f"/api/runs/{run_id}/agent-analysis")
            assert agent_analysis.status_code == 200, agent_analysis.text
            agent_payload = agent_analysis.json()
            assert agent_payload["run_id"] == run_id
            assert agent_payload["metrics"]["risk_items"] == 1
            assert agent_payload["review_plan"]
            assert "acceptance" in agent_payload

            exported = client.post(f"/api/runs/{run_id}/export-cleaned", json={"export_name": "demo_export"})
            assert exported.status_code == 200, exported.text
            export_payload = exported.json()
            assert export_payload["label_change_count"] == 1
            assert Path(export_payload["cleaned_dataset_dir"]).exists()

            acceptance_decision = client.post(
                f"/api/items/{item_id}/decision",
                json={
                    "decision": "label_corrected",
                    "action": "replace_label",
                    "corrected_label_json": make_label(status="SKIP", skip_reason="STAFF_ONLY"),
                    "owner": "acceptance_tester",
                    "notes": "label corrected during acceptance",
                },
            )
            assert acceptance_decision.status_code == 200, acceptance_decision.text
            assert acceptance_decision.json()["decision"]["decision"] == "label_corrected"

            acceptance_report = client.post(f"/api/runs/{run_id}/acceptance-report")
            assert acceptance_report.status_code == 200, acceptance_report.text
            report_payload = acceptance_report.json()
            assert Path(report_payload["path"]).exists()
            assert "修后数据集验收报告" in report_payload["content"]
            assert report_payload["analysis"]["acceptance"]["corrected_count"] == 1

            re_audit_task = client.post(
                f"/api/runs/{run_id}/start-audit",
                json={
                    "dataset_dir": str(dataset_dir),
                    "dataset_name": "demo_reaudit",
                    "run_name": "demo_reaudit_run",
                },
            )
            assert re_audit_task.status_code == 200, re_audit_task.text
            re_audit_payload = wait_task(client, re_audit_task.json()["id"])
            assert re_audit_payload["status"] == "completed", re_audit_payload
            assert Path(re_audit_payload["result_run_dir"]).exists()

            task_log = client.get(f"/api/tasks/{re_audit_task.json()['id']}/log")
            assert task_log.status_code == 200, task_log.text
            assert "run_audit.py" in task_log.json()["content"]

            rerun_reports = client.get(f"/api/runs/{re_audit_payload['result_run_id']}/reports")
            assert rerun_reports.status_code == 200, rerun_reports.text
            assert "审计报告" in rerun_reports.json()["audit_report_content"]

            direct_task = client.post(
                "/api/intake",
                json={
                    "path": str(dataset_dir),
                    "dataset_name": "direct_dataset_audit",
                    "run_name": "direct_dataset_audit_run",
                },
            )
            assert direct_task.status_code == 200, direct_task.text
            direct_task_payload = direct_task.json()
            assert direct_task_payload["mode"] == "audit_task"
            direct_payload = wait_task(client, direct_task_payload["task"]["id"])
            assert direct_payload["status"] == "completed", direct_payload
            assert Path(direct_payload["result_run_dir"]).exists()
        print("PASS backend api smoke test")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
