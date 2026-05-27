from __future__ import annotations

import csv
import json
import os
import re
import shlex
import shutil
import sqlite3
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .db import connect, init_db, transaction


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
EXPORTS_DIR = BASE_DIR / "exports"
STATIC_DIR = BASE_DIR / "static"
IMPORTED_RUNS_DIR = BASE_DIR / "imported_runs"
GENERATED_CONFIG_DIR = BASE_DIR / "generated_configs"
TASK_LOG_DIR = BASE_DIR / "task_logs"
REMOTE_SYNC_LOCK_DIR = DATA_DIR / "remote_sync_locks"
PIPELINE_DIR = BASE_DIR.parent / "dataset_audit_pipeline"
DEFAULT_DB_PATH = DATA_DIR / "review_platform.db"

DEFAULT_MODEL_ENDPOINT = os.environ.get("DATASET_REVIEW_MODEL_ENDPOINT", "http://127.0.0.1:8080/api/chat/completions")
DEFAULT_REMOTE_MODEL_ENDPOINT = os.environ.get("DATASET_REVIEW_REMOTE_MODEL_ENDPOINT", "http://127.0.0.1:8080/api/chat/completions")
DEFAULT_MODEL_NAME = os.environ.get("DATASET_REVIEW_MODEL_NAME", "openai-compatible-multimodal-model")
DEFAULT_API_KEY_ENV = os.environ.get("DATASET_REVIEW_API_KEY_ENV", "DATASET_AUDIT_API_KEY")
DEFAULT_SSH_USER = os.environ.get("DATASET_REVIEW_SSH_USER", "reviewer")
DEFAULT_SSH_HOST = os.environ.get("DATASET_REVIEW_SSH_HOST", "example-host")
DEFAULT_SSH_PORT = os.environ.get("DATASET_REVIEW_SSH_PORT", "22")
DEFAULT_SSH_ASKPASS = os.environ.get("DATASET_REVIEW_SSH_ASKPASS", str(BASE_DIR.parent / "askpass.cmd"))
DEFAULT_REMOTE_PIPELINE_DIR = os.environ.get("DATASET_REVIEW_REMOTE_PIPELINE_DIR", "/opt/dataset-review-agent/dataset_audit_pipeline")
DEFAULT_REMOTE_CONFIG_DIR = os.environ.get("DATASET_REVIEW_REMOTE_CONFIG_DIR", f"{DEFAULT_REMOTE_PIPELINE_DIR}/platform_generated_configs")
DEFAULT_REMOTE_RUNS_DIR = os.environ.get("DATASET_REVIEW_REMOTE_RUNS_DIR", f"{DEFAULT_REMOTE_PIPELINE_DIR}/platform_runs")
DEFAULT_REMOTE_STATUS_TIMEOUT_SECONDS = float(os.environ.get("DATASET_REVIEW_REMOTE_STATUS_TIMEOUT_SECONDS", "1.5"))
DEFAULT_REMOTE_RUNNING_HEARTBEAT_SECONDS = float(os.environ.get("DATASET_REVIEW_REMOTE_RUNNING_HEARTBEAT_SECONDS", "60"))
DEFAULT_REMOTE_FAILURE_GRACE_SECONDS = float(os.environ.get("DATASET_REVIEW_REMOTE_FAILURE_GRACE_SECONDS", "900"))
DEFAULT_REMOTE_SYNC_LOCK_SECONDS = float(os.environ.get("DATASET_REVIEW_REMOTE_SYNC_LOCK_SECONDS", "600"))

VALID_DECISIONS = {
    "keep",
    "confirm_bad_label",
    "needs_rule_update",
    "hold",
    "acceptance_pass",
    "acceptance_issue",
    "needs_rework",
    "label_corrected",
}
VALID_ACTIONS = {"keep", "replace_label", "drop", "hold"}
TASK_STATUSES = {"pending", "running", "completed", "failed"}
ACTIVE_SUBPROCESSES: dict[int, subprocess.Popen[str]] = {}
ACTIVE_SUBPROCESSES_LOCK = threading.Lock()
STOP_REQUESTED_TASKS: set[int] = set()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ensure_dirs() -> None:
    for path in (DATA_DIR, EXPORTS_DIR, STATIC_DIR, IMPORTED_RUNS_DIR, GENERATED_CONFIG_DIR, TASK_LOG_DIR, REMOTE_SYNC_LOCK_DIR):
        path.mkdir(parents=True, exist_ok=True)


def is_remote_path_like(path_text: str) -> bool:
    return path_text.strip().startswith("/")


def ssh_target() -> str:
    return f"{DEFAULT_SSH_USER}@{DEFAULT_SSH_HOST}"


def ssh_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env["SSH_ASKPASS"] = DEFAULT_SSH_ASKPASS
    env["SSH_ASKPASS_REQUIRE"] = "force"
    env.setdefault("DISPLAY", "codex")
    return env


def ssh_command(remote_command: str) -> list[str]:
    command = ["ssh", "-o", "StrictHostKeyChecking=no"]
    if DEFAULT_SSH_PORT and DEFAULT_SSH_PORT != "22":
        command.extend(["-p", DEFAULT_SSH_PORT])
    command.extend([ssh_target(), remote_command])
    return command


def scp_command(*args: str) -> list[str]:
    command = ["scp", "-o", "StrictHostKeyChecking=no"]
    if DEFAULT_SSH_PORT and DEFAULT_SSH_PORT != "22":
        command.extend(["-P", DEFAULT_SSH_PORT])
    command.extend(args)
    return command


def read_remote_json_file(remote_path: str) -> dict[str, Any] | None:
    try:
        result = subprocess.run(
            ssh_command(f"if [ -f {shlex.quote(remote_path)} ]; then cat {shlex.quote(remote_path)}; fi"),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=ssh_subprocess_env(),
            timeout=DEFAULT_REMOTE_STATUS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return None
    if result.returncode != 0:
        return None
    text = (result.stdout or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    return json.loads(value)


class ImportRunRequest(BaseModel):
    run_dir: str = Field(..., description="Audit run directory path")


class IntakePathRequest(BaseModel):
    path: str = Field(..., description="Audit run dir or dataset dir path")
    dataset_name: str | None = None
    run_name: str | None = None
    generate_llm_report: bool = True


class DecisionRequest(BaseModel):
    decision: str
    action: str
    corrected_label_json: dict[str, Any] | None = None
    owner: str = ""
    notes: str = ""


class ExportRequest(BaseModel):
    export_name: str | None = None


class StartAuditTaskRequest(BaseModel):
    dataset_dir: str | None = None
    dataset_name: str | None = None
    run_name: str | None = None
    generate_llm_report: bool = True
    execution_mode: str = "auto"


def get_db_path() -> Path:
    value = os.environ.get("DATASET_REVIEW_DB_PATH", "").strip()
    return Path(value) if value else DEFAULT_DB_PATH


def get_conn() -> Iterator[sqlite3.Connection]:
    db_path = get_db_path()
    ensure_dirs()
    conn = connect(db_path)
    init_db(conn)
    try:
        yield conn
    finally:
        conn.close()


def standalone_conn() -> sqlite3.Connection:
    db_path = get_db_path()
    ensure_dirs()
    conn = connect(db_path)
    init_db(conn)
    return conn


def fetch_run(conn: sqlite3.Connection, run_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="run not found")
    return row


def fetch_item(conn: sqlite3.Connection, item_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM review_items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="review item not found")
    return row


def fetch_task(conn: sqlite3.Connection, task_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM audit_tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="task not found")
    return row


def is_within(parent: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def safe_remove_path(path_text: str | None) -> None:
    if not path_text:
        return
    path = Path(path_text)
    allowed_roots = [IMPORTED_RUNS_DIR, EXPORTS_DIR, GENERATED_CONFIG_DIR, TASK_LOG_DIR]
    if not any(is_within(root, path) for root in allowed_roots):
        return
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        try:
            path.unlink()
        except OSError:
            pass


def latest_decision_for_item(conn: sqlite3.Connection, item_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM review_decisions
        WHERE review_item_id = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (item_id,),
    ).fetchone()


def summarize_decision(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "decision": row["decision"],
        "action": row["action"],
        "corrected_label_json": loads(row["corrected_label_json"], None),
        "owner": row["owner"] or "",
        "notes": row["notes"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def decision_history_for_item(conn: sqlite3.Connection, item_id: int, limit: int = 20) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM review_decisions
        WHERE review_item_id = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT ?
        """,
        (item_id, limit),
    ).fetchall()
    return [summarize_decision(row) for row in rows]


def validate_corrected_label(action: str, label: dict[str, Any] | None) -> None:
    if action == "replace_label" and not isinstance(label, dict):
        raise HTTPException(status_code=400, detail="replace_label requires corrected_label_json object")


def import_run(conn: sqlite3.Connection, run_dir: Path) -> dict[str, Any]:
    run_summary_path = run_dir / "run_summary.json"
    ranked_rows_path = run_dir / "risk_ranked_rows.jsonl"
    manifest_path = run_dir / "manual_review_pack" / "manifest.json"
    if not run_summary_path.exists():
        raise HTTPException(status_code=400, detail="run_summary.json not found")
    if not ranked_rows_path.exists():
        raise HTTPException(status_code=400, detail="risk_ranked_rows.jsonl not found")

    summary = json.loads(run_summary_path.read_text(encoding="utf-8"))
    run_name = summary["run_name"]
    timestamp = now_iso()

    ranked_rows = [
        json.loads(line)
        for line in ranked_rows_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    positive_rows = [row for row in ranked_rows if int(row.get("risk_score", 0)) > 0]
    manual_image_map: dict[tuple[str, int], str] = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for item in manifest:
            key = (str(item.get("split", "")), int(item.get("line_no", 0)))
            copied_name = Path(str(item.get("copied_image", ""))).name
            source_local = run_dir / "manual_review_pack" / "source_images" / copied_name
            if source_local.exists():
                manual_image_map[key] = str(source_local)
                continue
            local_image = run_dir / "manual_review_pack" / "images" / copied_name
            if local_image.exists():
                manual_image_map[key] = str(local_image)

    with transaction(conn):
        existing = conn.execute("SELECT id FROM runs WHERE run_name = ?", (run_name,)).fetchone()
        if existing:
            run_id = int(existing["id"])
            conn.execute("DELETE FROM review_decisions WHERE review_item_id IN (SELECT id FROM review_items WHERE run_id = ?)", (run_id,))
            conn.execute("DELETE FROM review_items WHERE run_id = ?", (run_id,))
            conn.execute(
                """
                UPDATE runs
                SET dataset_name = ?, dataset_dir = ?, output_dir = ?, platform_run_dir = ?, total_rows = ?,
                    static_issue_count = ?, consistency_issue_count = ?, model_prediction_rows = ?,
                    model_flagged_rows = ?, review_pack_image_count = ?, summary_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    summary.get("dataset_name", ""),
                    summary.get("dataset_dir", ""),
                    summary.get("output_dir", ""),
                    str(run_dir),
                    int(summary.get("total_rows", 0)),
                    int(summary.get("static_issue_count", 0)),
                    int(summary.get("consistency_issue_count", 0)),
                    int(summary.get("model_prediction_rows", 0)),
                    int(summary.get("model_flagged_rows", 0)),
                    int(summary.get("review_pack_image_count", 0)),
                    dumps(summary),
                    timestamp,
                    run_id,
                ),
            )
        else:
            cursor = conn.execute(
                """
                INSERT INTO runs (
                    run_name, dataset_name, dataset_dir, output_dir, platform_run_dir, total_rows,
                    static_issue_count, consistency_issue_count, model_prediction_rows,
                    model_flagged_rows, review_pack_image_count, summary_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_name,
                    summary.get("dataset_name", ""),
                    summary.get("dataset_dir", ""),
                    summary.get("output_dir", ""),
                    str(run_dir),
                    int(summary.get("total_rows", 0)),
                    int(summary.get("static_issue_count", 0)),
                    int(summary.get("consistency_issue_count", 0)),
                    int(summary.get("model_prediction_rows", 0)),
                    int(summary.get("model_flagged_rows", 0)),
                    int(summary.get("review_pack_image_count", 0)),
                    dumps(summary),
                    timestamp,
                    timestamp,
                ),
            )
            run_id = int(cursor.lastrowid)

        conn.executemany(
            """
            INSERT INTO review_items (
                run_id, split, line_no, image, order_id, scene_id, captured_at, risk_score, risk_bucket,
                label_json, model_prediction_json, static_issues_json, consistency_issues_json,
                model_issues_json, model_validation_issues_json, model_mismatch_fields_json,
                import_payload_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    run_id,
                    row.get("split", ""),
                    int(row.get("line_no", 0)),
                    manual_image_map.get((row.get("split", ""), int(row.get("line_no", 0))), row.get("image", "")),
                    row.get("order_id", ""),
                    row.get("scene_id", ""),
                    row.get("captured_at", ""),
                    int(row.get("risk_score", 0)),
                    row.get("risk_bucket", "clean"),
                    dumps(row.get("label")),
                    dumps(row.get("model_prediction")),
                    dumps(row.get("static_issues", [])),
                    dumps(row.get("consistency_issues", [])),
                    dumps(row.get("model_issues", [])),
                    dumps(row.get("model_validation_issues", [])),
                    dumps(row.get("model_mismatch_fields", [])),
                    dumps(row),
                    timestamp,
                    timestamp,
                )
                for row in positive_rows
            ],
        )

    return {"run_id": run_id, "run_name": run_name, "imported_items": len(positive_rows)}


def detect_intake_path_kind(path: Path) -> str:
    if not path.exists() or not path.is_dir():
        raise HTTPException(status_code=400, detail=f"path not found: {path}")
    if (path / "run_summary.json").exists() and (path / "risk_ranked_rows.jsonl").exists():
        return "audit_run"
    if (path / "train.jsonl").exists() or (path / "val.jsonl").exists():
        return "dataset_dir"
    raise HTTPException(
        status_code=400,
        detail="path is neither an audit run directory nor a dataset directory",
    )


def detect_remote_intake_path_kind(path_text: str) -> str:
    remote_path = shlex.quote(path_text)
    remote_command = (
        f"if [ -d {remote_path} ]; then "
        f"if [ -f {remote_path}/run_summary.json ] && [ -f {remote_path}/risk_ranked_rows.jsonl ]; then "
        f"echo audit_run; "
        f"elif [ -f {remote_path}/train.jsonl ] || [ -f {remote_path}/val.jsonl ]; then "
        f"echo dataset_dir; "
        f"else echo unknown; fi; "
        f"else echo missing; fi"
    )
    result = subprocess.run(
        ssh_command(remote_command),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=ssh_subprocess_env(),
    )
    kind = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    if result.returncode != 0:
        raise HTTPException(status_code=400, detail=f"remote path probe failed: {result.stderr.strip() or result.stdout.strip()}")
    if kind == "missing":
        raise HTTPException(status_code=400, detail=f"remote path not found: {path_text}")
    if kind not in {"audit_run", "dataset_dir"}:
        raise HTTPException(status_code=400, detail="remote path is neither an audit run directory nor a dataset directory")
    return f"server_{kind}"


def local_import_target_for_remote_run(remote_path: str) -> Path:
    name = Path(remote_path.rstrip("/")).name or f"remote_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    return IMPORTED_RUNS_DIR / name


def import_remote_run(conn: sqlite3.Connection, remote_run_dir: str) -> dict[str, Any]:
    local_run_dir = local_import_target_for_remote_run(remote_run_dir)
    if local_run_dir.exists():
        shutil.rmtree(local_run_dir)
    result = subprocess.run(
        scp_command("-r", f"{ssh_target()}:{remote_run_dir}", str(IMPORTED_RUNS_DIR)),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=ssh_subprocess_env(),
    )
    if result.returncode != 0:
        raise HTTPException(status_code=400, detail=f"remote run import failed: {result.stderr.strip() or result.stdout.strip()}")
    if not local_run_dir.exists():
        raise HTTPException(status_code=400, detail=f"remote run import failed: {remote_run_dir}")
    return import_run(conn, local_run_dir)


def resolve_run_dir(row: sqlite3.Row) -> Path | None:
    for candidate in (row["platform_run_dir"], row["output_dir"]):
        if candidate:
            path = Path(candidate)
            if path.exists():
                return path
    return None


def load_run_reports(row: sqlite3.Row) -> dict[str, Any]:
    run_dir = resolve_run_dir(row)
    if run_dir is None:
        return {
            "run_dir": "",
            "audit_report_path": "",
            "audit_report_content": "",
            "llm_report_path": "",
            "llm_report_content": "",
        }
    audit_path = run_dir / "audit_report.md"
    llm_path = run_dir / "llm_analysis_report.md"
    return {
        "run_dir": str(run_dir),
        "audit_report_path": str(audit_path) if audit_path.exists() else "",
        "audit_report_content": audit_path.read_text(encoding="utf-8") if audit_path.exists() else "",
        "llm_report_path": str(llm_path) if llm_path.exists() else "",
        "llm_report_content": llm_path.read_text(encoding="utf-8") if llm_path.exists() else "",
    }


def load_auto_fix_artifacts(row: sqlite3.Row) -> dict[str, Any]:
    run_dir = resolve_run_dir(row)
    summary = loads(row["summary_json"], {})
    response: dict[str, Any] = {
        "run_dir": str(run_dir) if run_dir else "",
        "summary_path": "",
        "changes_path": "",
        "fixed_dataset_dir": summary.get("effective_dataset_dir", row["dataset_dir"]),
        "summary": None,
        "changes": [],
    }
    if run_dir is None:
        return response

    auto_fix_summary_path = run_dir / "auto_fix_summary.json"
    auto_fix_changes_path = run_dir / "auto_fix_changes.jsonl"
    response["summary_path"] = str(auto_fix_summary_path) if auto_fix_summary_path.exists() else ""
    response["changes_path"] = str(auto_fix_changes_path) if auto_fix_changes_path.exists() else ""

    if auto_fix_summary_path.exists():
        try:
            response["summary"] = json.loads(auto_fix_summary_path.read_text(encoding="utf-8"))
            response["fixed_dataset_dir"] = response["summary"].get("fixed_dataset_dir", response["fixed_dataset_dir"])
        except json.JSONDecodeError:
            response["summary"] = None

    if auto_fix_changes_path.exists():
        changes: list[dict[str, Any]] = []
        with auto_fix_changes_path.open("r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    changes.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        response["changes"] = changes

    return response


def item_response(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    import_payload = loads(row["import_payload_json"], {})
    raw_image = import_payload.get("image") or row["image"]
    decision = latest_decision_for_item(conn, int(row["id"]))
    return {
        "id": int(row["id"]),
        "run_id": int(row["run_id"]),
        "split": row["split"],
        "line_no": int(row["line_no"]),
        "image": row["image"],
        "raw_image": raw_image,
        "has_raw_image": bool(raw_image and Path(raw_image).exists() and raw_image != row["image"]),
        "order_id": row["order_id"] or "",
        "scene_id": row["scene_id"] or "",
        "captured_at": row["captured_at"] or "",
        "risk_score": int(row["risk_score"]),
        "risk_bucket": row["risk_bucket"],
        "label_json": loads(row["label_json"], None),
        "model_prediction_json": loads(row["model_prediction_json"], None),
        "static_issues": loads(row["static_issues_json"], []),
        "consistency_issues": loads(row["consistency_issues_json"], []),
        "model_issues": loads(row["model_issues_json"], []),
        "model_validation_issues": loads(row["model_validation_issues_json"], []),
        "model_mismatch_fields": loads(row["model_mismatch_fields_json"], []),
        "decision": summarize_decision(decision),
        "decision_history": decision_history_for_item(conn, int(row["id"])),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def run_response(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    item_count = conn.execute("SELECT COUNT(*) AS c FROM review_items WHERE run_id = ?", (row["id"],)).fetchone()["c"]
    decided_count = conn.execute(
        """
        SELECT COUNT(DISTINCT review_item_id) AS c
        FROM review_decisions
        WHERE review_item_id IN (SELECT id FROM review_items WHERE run_id = ?)
        """,
        (row["id"],),
    ).fetchone()["c"]
    return {
        "id": int(row["id"]),
        "run_name": row["run_name"],
        "dataset_name": row["dataset_name"],
        "dataset_dir": row["dataset_dir"],
        "output_dir": row["output_dir"],
        "platform_run_dir": row["platform_run_dir"] or "",
        "total_rows": int(row["total_rows"]),
        "static_issue_count": int(row["static_issue_count"]),
        "consistency_issue_count": int(row["consistency_issue_count"]),
        "model_prediction_rows": int(row["model_prediction_rows"]),
        "model_flagged_rows": int(row["model_flagged_rows"]),
        "review_pack_image_count": int(row["review_pack_image_count"]),
        "imported_item_count": int(item_count),
        "decided_item_count": int(decided_count),
        "summary": loads(row["summary_json"], {}),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _count_issue_values(rows: list[sqlite3.Row], column: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        for value in loads(row[column], []):
            key = str(value)
            counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[1], reverse=True))


def _top_dict_items(values: dict[str, int], limit: int = 8) -> list[dict[str, Any]]:
    return [{"name": key, "count": count} for key, count in list(values.items())[:limit]]


def build_agent_analysis(conn: sqlite3.Connection, run: sqlite3.Row) -> dict[str, Any]:
    run_payload = run_response(conn, run)
    run_summary = run_payload.get("summary", {})
    reports = load_run_reports(run)
    rows = conn.execute("SELECT * FROM review_items WHERE run_id = ? ORDER BY risk_score DESC, id ASC", (run["id"],)).fetchall()
    item_total = len(rows)
    decided_count = int(run_payload["decided_item_count"])
    undecided_count = max(0, item_total - decided_count)

    decision_rows = conn.execute(
        """
        SELECT rd.action, COUNT(DISTINCT rd.review_item_id) AS c
        FROM review_decisions rd
        WHERE rd.review_item_id IN (SELECT id FROM review_items WHERE run_id = ?)
          AND rd.id IN (
              SELECT MAX(id)
              FROM review_decisions
              WHERE review_item_id = rd.review_item_id
          )
        GROUP BY rd.action
        """,
        (run["id"],),
    ).fetchall()
    decision_counts = {row["action"]: int(row["c"]) for row in decision_rows}

    decision_type_rows = conn.execute(
        """
        SELECT rd.decision, COUNT(DISTINCT rd.review_item_id) AS c
        FROM review_decisions rd
        WHERE rd.review_item_id IN (SELECT id FROM review_items WHERE run_id = ?)
          AND rd.id IN (
              SELECT MAX(id)
              FROM review_decisions
              WHERE review_item_id = rd.review_item_id
          )
        GROUP BY rd.decision
        """,
        (run["id"],),
    ).fetchall()
    decision_type_counts = {row["decision"]: int(row["c"]) for row in decision_type_rows}

    risk_bucket_counts: dict[str, int] = {}
    for row in rows:
        bucket = row["risk_bucket"] or "unknown"
        risk_bucket_counts[bucket] = risk_bucket_counts.get(bucket, 0) + 1

    static_counts = _count_issue_values(rows, "static_issues_json")
    consistency_counts = _count_issue_values(rows, "consistency_issues_json")
    model_counts = _count_issue_values(rows, "model_issues_json")
    validation_counts = _count_issue_values(rows, "model_validation_issues_json")
    mismatch_counts = _count_issue_values(rows, "model_mismatch_fields_json")

    p0: list[str] = []
    p1: list[str] = []

    total_rows = max(1, int(run["total_rows"]))
    if static_counts.get("missing_image_file", 0) >= max(1, total_rows // 2):
        p0.append("图片路径不可读占比过高，需先修复数据挂载或路径映射。")
    if static_counts.get("label_not_json_object", 0):
        p0.append("存在非 JSON 对象标签，训练前需要清理或重标。")
    if static_counts.get("shared_order_id_between_train_val", 0):
        p0.append("存在 train/val 订单级泄漏，建议按 order_id 重新切分。")
    if static_counts.get("conflicting_duplicate_image", 0):
        p1.append("存在同图不同标的冲突样本，建议人工复核后只保留一版。")
    if consistency_counts:
        p1.append("同订单或同场景存在一致性冲突，建议优先抽查边界样本。")
    if model_counts or mismatch_counts:
        p1.append("模型辅助结果与原标签存在分歧，适合作为人工复核优先队列。")

    auto_fix_enabled = bool(run_summary.get("auto_fix_enabled", False))
    auto_fix_changed = int(run_summary.get("auto_fix_changed_rows", 0) or 0)
    auto_fix_remaining = int(run_summary.get("auto_fix_final_static_issue_count", 0) or 0)
    if auto_fix_enabled and auto_fix_changed > 0 and auto_fix_remaining > 0:
        p1.append(f"自动修复已处理部分静态冲突，但仍剩 {auto_fix_remaining} 个静态问题。")

    sorted_buckets = sorted(risk_bucket_counts.items(), key=lambda item: item[1], reverse=True)
    non_clean_buckets = [(bucket, count) for bucket, count in sorted_buckets if bucket != "clean"]
    clean_only_queue = bool(sorted_buckets) and not non_clean_buckets and sorted_buckets[0][0] == "clean"
    no_remaining_risk = (
        not p0
        and int(run["static_issue_count"]) == 0
        and int(run["consistency_issue_count"]) == 0
        and int(run["model_flagged_rows"]) == 0
        and not model_counts
        and not mismatch_counts
        and not validation_counts
        and clean_only_queue
    )

    if p0:
        lifecycle_state = "BLOCKED"
        headline = "当前数据集仍有阻塞项，建议先处理 P0 问题。"
    elif no_remaining_risk:
        lifecycle_state = "READY_TO_EXPORT"
        if auto_fix_enabled and auto_fix_changed > 0:
            headline = "自动修复后未发现剩余风险，可直接导出或做少量抽查。"
        else:
            headline = "当前未发现剩余风险，可直接导出或做少量抽查。"
    elif undecided_count > 0 and item_total > 0:
        lifecycle_state = "HUMAN_REVIEWING"
        headline = "审计已完成，建议按高风险队列继续人工复核。"
    elif decided_count > 0:
        lifecycle_state = "READY_TO_EXPORT"
        headline = "人工复核已有结论，可以导出 cleaned dataset 并复测。"
    else:
        lifecycle_state = "AUDIT_DONE"
        headline = "审计已完成，可以开始生成复核计划。"

    review_plan: list[dict[str, Any]] = []
    if not no_remaining_risk:
        priority_buckets = non_clean_buckets or sorted_buckets
        for bucket, count in priority_buckets[:5]:
            review_plan.append(
                {
                    "title": f"优先复核 {bucket}",
                    "filter": {"risk_bucket": bucket, "decision_status": "undecided"},
                    "target_count": min(100, count),
                    "reason": f"该风险桶共有 {count} 条，建议先看未处理样本。",
                }
            )

        for issue, count in list(static_counts.items())[:3]:
            review_plan.append(
                {
                    "title": f"静态问题专项：{issue}",
                    "filter": {"issue_source": "static", "q": issue, "decision_status": "undecided"},
                    "target_count": min(50, count),
                    "reason": "静态规则命中通常更接近确定性问题，适合优先清理。",
                }
            )

    next_actions: list[dict[str, str]] = []
    if p0:
        next_actions.append({"action": "fix_blocker", "label": "先处理阻塞项", "detail": p0[0]})
    elif no_remaining_risk:
        next_actions.append({"action": "export", "label": "导出 cleaned dataset", "detail": "当前仅剩 clean 样本，可直接导出当前结果。"})
        next_actions.append({"action": "spot_check", "label": "按需少量抽查", "detail": "如果你想更稳妥，可以额外抽查少量 clean 样本再导出。"})
    if undecided_count > 0 and not no_remaining_risk:
        next_actions.append({"action": "review", "label": "继续人工复核", "detail": "按 Agent 的复核计划筛选未处理高风险样本。"})
    if decided_count > 0 and not no_remaining_risk:
        next_actions.append({"action": "export", "label": "导出 cleaned dataset", "detail": "人工决策会以最高优先级写入导出数据集。"})
    if reports.get("audit_report_content") or reports.get("llm_report_content"):
        next_actions.append({"action": "compare", "label": "结合报告复核", "detail": "先看审计报告和模型分析报告，再处理 Top 风险样本。"})

    corrected_count = int(decision_type_counts.get("label_corrected", 0))
    acceptance_issue_count = int(decision_type_counts.get("acceptance_issue", 0)) + int(decision_type_counts.get("needs_rework", 0))
    sampled_count = (
        int(decision_type_counts.get("acceptance_pass", 0))
        + int(decision_type_counts.get("acceptance_issue", 0))
        + int(decision_type_counts.get("needs_rework", 0))
        + corrected_count
    )

    if p0:
        acceptance_verdict = "不通过"
        acceptance_reason = "仍存在 P0 阻塞问题，暂不建议进入训练。"
    elif acceptance_issue_count > 0:
        acceptance_verdict = "需复查"
        acceptance_reason = "人工抽查已发现问题，建议退回重修或扩大抽查范围。"
    elif corrected_count > 0:
        acceptance_verdict = "修正后通过"
        acceptance_reason = "人工复核发现少量错标，修正后建议导出清洗数据集再复测一次。"
    elif no_remaining_risk:
        acceptance_verdict = "通过"
        if auto_fix_enabled and auto_fix_changed > 0:
            acceptance_reason = "自动修复已清空剩余风险，当前可直接导出 cleaned dataset，或做少量抽查后进入训练。"
        else:
            acceptance_reason = "当前未发现剩余风险，可直接导出 cleaned dataset，或做少量抽查后进入训练。"
    elif sampled_count > 0:
        acceptance_verdict = "通过"
        acceptance_reason = "自动审计未发现阻塞项，人工抽查暂未发现明显问题。"
    else:
        acceptance_verdict = "待抽查"
        acceptance_reason = "自动审计已完成，但还没有足够的人工抽查记录。"

    train_ready = not p0 and acceptance_verdict in {"通过", "待抽查", "修正后通过"}

    return {
        "run_id": int(run["id"]),
        "run_name": run["run_name"],
        "lifecycle_state": lifecycle_state,
        "headline": headline,
        "metrics": {
            "total_rows": int(run["total_rows"]),
            "risk_items": item_total,
            "decided_items": decided_count,
            "undecided_items": undecided_count,
            "static_issue_count": int(run["static_issue_count"]),
            "consistency_issue_count": int(run["consistency_issue_count"]),
            "model_prediction_rows": int(run["model_prediction_rows"]),
            "model_flagged_rows": int(run["model_flagged_rows"]),
            "auto_fix_changed_rows": auto_fix_changed,
            "auto_fix_initial_static_issue_count": int(run_summary.get("auto_fix_initial_static_issue_count", 0) or 0),
            "auto_fix_final_static_issue_count": auto_fix_remaining,
        },
        "decision_counts": decision_counts,
        "decision_type_counts": decision_type_counts,
        "acceptance": {
            "verdict": acceptance_verdict,
            "reason": acceptance_reason,
            "train_ready": train_ready,
            "sampled_count": sampled_count,
            "issue_count": acceptance_issue_count,
            "corrected_count": corrected_count,
        },
        "priority_findings": {"p0": p0, "p1": p1},
        "top_risk_buckets": _top_dict_items(risk_bucket_counts),
        "top_static_issues": _top_dict_items(static_counts),
        "top_consistency_issues": _top_dict_items(consistency_counts),
        "top_model_issues": _top_dict_items(model_counts),
        "top_validation_issues": _top_dict_items(validation_counts),
        "top_mismatch_fields": _top_dict_items(mismatch_counts),
        "review_plan": review_plan[:8],
        "next_actions": next_actions,
        "report_status": {
            "has_audit_report": bool(reports.get("audit_report_content")),
            "has_llm_report": bool(reports.get("llm_report_content")),
        },
        "auto_fix": {
            "enabled": auto_fix_enabled,
            "rounds": int(run_summary.get("auto_fix_rounds", 0) or 0),
            "changed_rows": auto_fix_changed,
            "initial_static_issue_count": int(run_summary.get("auto_fix_initial_static_issue_count", 0) or 0),
            "final_static_issue_count": auto_fix_remaining,
            "effective_dataset_dir": run_summary.get("effective_dataset_dir", run["dataset_dir"]),
        },
    }


def safe_report_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "acceptance_report"


def generate_acceptance_report(conn: sqlite3.Connection, run: sqlite3.Row) -> dict[str, Any]:
    analysis = build_agent_analysis(conn, run)
    report_dir = EXPORTS_DIR / "acceptance_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{safe_report_name(run['run_name'])}_acceptance_report.md"

    review_rows = conn.execute(
        """
        SELECT ri.id, ri.split, ri.line_no, ri.image, ri.risk_bucket, ri.risk_score,
               rd.decision, rd.action, rd.owner, rd.notes, rd.updated_at
        FROM review_decisions rd
        JOIN review_items ri ON ri.id = rd.review_item_id
        WHERE ri.run_id = ?
          AND rd.id IN (
              SELECT MAX(id)
              FROM review_decisions
              WHERE review_item_id = rd.review_item_id
          )
        ORDER BY rd.updated_at DESC, rd.id DESC
        LIMIT 200
        """,
        (run["id"],),
    ).fetchall()

    def bullet_items(values: list[str]) -> str:
        return "\n".join(f"- {item}" for item in values) if values else "- 暂无"

    def top_items(values: list[dict[str, Any]]) -> str:
        if not values:
            return "| 项目 | 数量 |\n| --- | --- |\n| 暂无 | 0 |"
        table = ["| 项目 | 数量 |", "| --- | --- |"]
        table.extend(f"| `{item['name']}` | {item['count']} |" for item in values)
        return "\n".join(table)

    review_lines = ["| 样本 | 风险 | 验收结论 | 处理动作 | 复核人 | 备注 |", "| --- | --- | --- | --- | --- | --- |"]
    if review_rows:
        for row in review_rows:
            review_lines.append(
                "| "
                f"#{row['id']} `{row['split']}:{row['line_no']}` | "
                f"{row['risk_bucket']} / {row['risk_score']} | "
                f"{row['decision']} | {row['action']} | "
                f"{row['owner'] or '-'} | {(row['notes'] or '-').replace('|', '/')} |"
            )
    else:
        review_lines.append("| 暂无 | - | - | - | - | - |")

    metrics = analysis["metrics"]
    acceptance = analysis["acceptance"]
    content = f"""# 修后数据集验收报告：{run['dataset_name']}

## 一、验收结论
- 验收状态：**{acceptance['verdict']}**
- 是否建议进入训练：**{'是' if acceptance['train_ready'] else '否'}**
- 结论说明：{acceptance['reason']}

## 二、数据概览
- run：`{run['run_name']}`
- dataset：`{run['dataset_name']}`
- 数据目录：`{run['dataset_dir']}`
- 总行数：{metrics['total_rows']}
- 高风险样本：{metrics['risk_items']}
- 已处理样本：{metrics['decided_items']}
- 待处理样本：{metrics['undecided_items']}

## 三、主要风险
### P0 阻塞项
{bullet_items(analysis['priority_findings']['p0'])}

### P1 关注项
{bullet_items(analysis['priority_findings']['p1'])}

## 四、问题分布
### 风险桶 Top
{top_items(analysis['top_risk_buckets'])}

### 静态问题 Top
{top_items(analysis['top_static_issues'])}

### 一致性问题 Top
{top_items(analysis['top_consistency_issues'])}

### 模型问题 Top
{top_items(analysis['top_model_issues'])}

## 五、人工复核结果
- 抽查样本数：{acceptance['sampled_count']}
- 发现问题数：{acceptance['issue_count']}
- 已改标通过数：{acceptance['corrected_count']}

{chr(10).join(review_lines)}

## 六、自动修复摘要
- 自动修复启用：{'是' if analysis['auto_fix']['enabled'] else '否'}
- 修复轮数：{analysis['auto_fix']['rounds']}
- 修改样本数：{analysis['auto_fix']['changed_rows']}
- 静态问题变化：{analysis['auto_fix']['initial_static_issue_count']} -> {analysis['auto_fix']['final_static_issue_count']}
- 当前有效数据集目录：`{analysis['auto_fix']['effective_dataset_dir']}`

## 七、建议动作
{bullet_items([f"{item['label']}：{item['detail']}" for item in analysis['next_actions']])}
"""
    report_path.write_text(content, encoding="utf-8")
    return {"path": str(report_path), "analysis": analysis}

def task_response(conn: sqlite3.Connection, row: sqlite3.Row, *, allow_remote_lookup: bool = True) -> dict[str, Any]:
    progress = estimate_task_progress(row, allow_remote_lookup=allow_remote_lookup)
    source_kind = "server" if is_remote_path_like(row["dataset_dir"] or "") else "local"
    return {
        "id": int(row["id"]),
        "task_type": row["task_type"],
        "source_run_id": row["source_run_id"],
        "result_run_id": row["result_run_id"],
        "dataset_name": row["dataset_name"],
        "dataset_dir": row["dataset_dir"],
        "run_name": row["run_name"],
        "config_path": row["config_path"],
        "log_path": row["log_path"],
        "result_run_dir": row["result_run_dir"] or "",
        "audit_report_path": row["audit_report_path"] or "",
        "llm_report_path": row["llm_report_path"] or "",
        "status": row["status"],
        "source_kind": source_kind,
        "can_resume": row["status"] == "failed",
        "progress_percent": progress["percent"],
        "progress_label": progress["label"],
        "progress_stage": progress["stage"],
        "progress_updated_at": progress.get("updated_at", ""),
        "error_message": row["error_message"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }



def estimate_task_progress(row: sqlite3.Row, *, allow_remote_lookup: bool = True) -> dict[str, Any]:
    status = row["status"]
    log_path = Path(row["log_path"]) if row["log_path"] else None
    text = ""
    if log_path and log_path.exists():
        try:
            text = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""

    updated_at = row["updated_at"]
    if status == "completed":
        return {"percent": 100, "label": "100%", "stage": "已完成", "updated_at": updated_at}
    if status == "failed":
        return {"percent": 100, "label": "失败", "stage": "执行失败", "updated_at": updated_at}
    if status == "pending":
        return {"percent": 3, "label": "3%", "stage": "等待执行", "updated_at": updated_at}

    if row["task_type"] == "audit_remote":
        stage = "连接服务器"
        percent = 8
        if "scp -o StrictHostKeyChecking=no" in text:
            stage = "上传配置"
            percent = 16
        if "python3 run_audit.py --config" in text:
            stage = "服务器审计中"
            percent = 35

        remote_run_dir = f"{DEFAULT_REMOTE_RUNS_DIR}/{row['run_name']}"
        remote_progress = read_remote_json_file(f"{remote_run_dir}/model_risk_progress.json") if allow_remote_lookup else None
        if remote_progress:
            total_int = max(1, int(remote_progress.get("selected_rows", 0) or 0))
            known_prediction_rows = int(remote_progress.get("known_prediction_rows", 0) or 0)
            processed_rows_this_run = int(remote_progress.get("processed_rows_this_run", 0) or 0)
            skipped_success_rows = int(remote_progress.get("skipped_success_rows", 0) or 0)
            skipped_exhausted_rows = int(remote_progress.get("skipped_exhausted_rows", 0) or 0)
            done_candidates = [
                known_prediction_rows,
                processed_rows_this_run,
                skipped_success_rows + skipped_exhausted_rows + processed_rows_this_run,
            ]
            done_int = min(total_int, max(done_candidates))
            percent = min(85, 35 + int(done_int / total_int * 45))
            stage = f"服务器模型复核 {done_int}/{total_int}"
            updated_at = remote_progress.get("updated_at") or updated_at
        else:
            matches = re.findall(r"\[model-risk\] processed (\d+)/(\d+)", text)
            if matches:
                done, total = matches[-1]
                total_int = max(1, int(total))
                done_int = min(total_int, int(done))
                percent = min(85, 35 + int(done_int / total_int * 45))
                stage = f"服务器模型复核 {done_int}/{total_int}"

        if "generate_llm_analysis_report.py" in text:
            stage = "生成 Gemini 报告"
            percent = 92
        if "remote task completed" in text:
            stage = "已完成"
            percent = 100
        return {"percent": percent, "label": f"{percent}%", "stage": stage, "updated_at": updated_at}

    stage = "准备审计"
    percent = 8
    if "run_audit.py --config" in text:
        stage = "连接服务"
        percent = 25
    matches = re.findall(r"\[model-risk\] processed (\d+)/(\d+)", text)
    if matches:
        done, total = matches[-1]
        total_int = max(1, int(total))
        done_int = min(total_int, int(done))
        percent = min(88, 25 + int(done_int / total_int * 55))
        stage = f"模型复核 {done_int}/{total_int}"
    if "generate_llm_analysis_report.py" in text:
        stage = "生成 Gemini 报告"
        percent = 94
    return {"percent": percent, "label": f"{percent}%", "stage": stage, "updated_at": updated_at}


def remote_task_probe(row: sqlite3.Row) -> dict[str, bool]:
    remote_config_path, remote_run_dir = remote_task_paths(row["run_name"])
    command = (
        f"RUN_DIR={shlex.quote(remote_run_dir)} REMOTE_CONFIG={shlex.quote(remote_config_path)} "
        "python3 - <<'PY'\n"
        "import os\n"
        "import subprocess\n"
        "from pathlib import Path\n"
        "\n"
        "run_dir = Path(os.environ['RUN_DIR'])\n"
        "remote_config = os.environ['REMOTE_CONFIG']\n"
        "audit_marker = f'run_audit.py --config {remote_config}'\n"
        "llm_marker = f'generate_llm_analysis_report.py --run-dir {run_dir}'\n"
        "ps_lines = subprocess.run(['ps', '-eo', 'args='], capture_output=True, text=True, check=False).stdout.splitlines()\n"
        "\n"
        "def is_live_python_process(line: str, marker: str) -> bool:\n"
        "    return marker in line and 'python' in line and 'bash -c' not in line and 'ssh ' not in line\n"
        "\n"
        "print(f'RUN_DIR={int(run_dir.is_dir())}')\n"
        "print(f'RUN_SUMMARY={int((run_dir / \"run_summary.json\").is_file())}')\n"
        "print(f'LLM_REPORT={int((run_dir / \"llm_analysis_report.md\").is_file())}')\n"
        "print(f'AUDIT_RUNNING={int(any(is_live_python_process(line, audit_marker) for line in ps_lines))}')\n"
        "print(f'LLM_RUNNING={int(any(is_live_python_process(line, llm_marker) for line in ps_lines))}')\n"
        "PY"
    )
    try:
        result = subprocess.run(
            ssh_command(command),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=ssh_subprocess_env(),
            timeout=DEFAULT_REMOTE_STATUS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {
            "run_dir": False,
            "run_summary": False,
            "llm_report": False,
            "audit_running": False,
            "llm_running": False,
        }
    if result.returncode != 0:
        return {
            "run_dir": False,
            "run_summary": False,
            "llm_report": False,
            "audit_running": False,
            "llm_running": False,
        }
    values: dict[str, bool] = {}
    for line in (result.stdout or "").splitlines():
        if "=" not in line:
            continue
        key, raw = line.split("=", 1)
        values[key.strip()] = raw.strip() == "1"
    return {
        "run_dir": values.get("RUN_DIR", False),
        "run_summary": values.get("RUN_SUMMARY", False),
        "llm_report": values.get("LLM_REPORT", False),
        "audit_running": values.get("AUDIT_RUNNING", False),
        "llm_running": values.get("LLM_RUNNING", False),
    }


def local_task_probe(row: sqlite3.Row) -> dict[str, bool]:
    local_run_dir = IMPORTED_RUNS_DIR / row["run_name"]
    return {
        "run_dir": local_run_dir.exists(),
        "run_summary": (local_run_dir / "run_summary.json").exists(),
        "llm_report": (local_run_dir / "llm_analysis_report.md").exists(),
    }


def local_task_is_active(task_id: int) -> bool:
    with ACTIVE_SUBPROCESSES_LOCK:
        process = ACTIVE_SUBPROCESSES.get(task_id)
    if process is None:
        return False
    return process.poll() is None


def should_reconcile_task(row: sqlite3.Row) -> bool:
    status = row["status"]
    if status in {"pending", "running"}:
        return True
    if row["task_type"] == "audit_remote" and status == "failed" and not row["result_run_id"]:
        return True
    return False


def parse_iso_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def timestamp_is_recent(value: Any, seconds: float) -> bool:
    stamp = parse_iso_datetime(value)
    if stamp is None:
        return False
    return (datetime.now() - stamp).total_seconds() <= seconds


def task_status_is_recent(row: sqlite3.Row, seconds: float) -> bool:
    return timestamp_is_recent(row["updated_at"], seconds) or timestamp_is_recent(row["created_at"], seconds)


def path_mtime_is_recent(path: Path, seconds: float) -> bool:
    if not path.exists():
        return False
    return (time.time() - path.stat().st_mtime) <= seconds


def remote_progress_is_recent(progress: dict[str, Any] | None, minutes: int = 15) -> bool:
    if not progress:
        return False
    return timestamp_is_recent(progress.get("updated_at"), minutes * 60)


def mark_task_completed_from_local_dir(conn: sqlite3.Connection, row: sqlite3.Row, local_run_dir: Path) -> sqlite3.Row:
    imported = import_run(conn, local_run_dir)
    llm_report_path = str(local_run_dir / "llm_analysis_report.md") if (local_run_dir / "llm_analysis_report.md").exists() else ""
    update_task_status(
        int(row["id"]),
        status="completed",
        result_run_id=imported["run_id"],
        result_run_dir=str(local_run_dir),
        audit_report_path=str(local_run_dir / "audit_report.md"),
        llm_report_path=llm_report_path,
        error_message="",
    )
    return fetch_task(conn, int(row["id"]))


def mark_task_running_if_stale(conn: sqlite3.Connection, row: sqlite3.Row, task_id: int) -> sqlite3.Row:
    if row["status"] != "running" or not task_status_is_recent(row, DEFAULT_REMOTE_RUNNING_HEARTBEAT_SECONDS):
        update_task_status(task_id, status="running", error_message="")
        return fetch_task(conn, task_id)
    return row


def reconcile_task_state(conn: sqlite3.Connection, row: sqlite3.Row) -> sqlite3.Row:
    status = row["status"]
    if status == "completed":
        return row

    task_id = int(row["id"])
    if row["task_type"] == "audit_remote":
        remote_config_path, remote_run_dir = remote_task_paths(row["run_name"])
        local_run_dir = IMPORTED_RUNS_DIR / row["run_name"]
        probe = remote_task_probe(row)
        if probe["run_summary"]:
            if (local_run_dir / "run_summary.json").exists():
                return mark_task_completed_from_local_dir(conn, row, local_run_dir)

            sync_root = IMPORTED_RUNS_DIR / "_remote_sync"
            sync_local_run_dir = sync_root / row["run_name"]
            if (sync_local_run_dir / "run_summary.json").exists():
                return mark_task_completed_from_local_dir(conn, row, sync_local_run_dir)

            lock_name = re.sub(r"[^A-Za-z0-9._-]+", "_", row["run_name"]).strip("_") or f"task_{task_id}"
            sync_lock_path = REMOTE_SYNC_LOCK_DIR / f"{lock_name}.lock"
            if path_mtime_is_recent(sync_lock_path, DEFAULT_REMOTE_SYNC_LOCK_SECONDS):
                return mark_task_running_if_stale(conn, row, task_id)

            download_parent = IMPORTED_RUNS_DIR
            target_local_run_dir = local_run_dir
            if local_run_dir.exists():
                try:
                    shutil.rmtree(local_run_dir)
                except OSError:
                    sync_root.mkdir(parents=True, exist_ok=True)
                    target_local_run_dir = sync_root / row["run_name"]
                    if target_local_run_dir.exists():
                        shutil.rmtree(target_local_run_dir, ignore_errors=True)
                    download_parent = sync_root
            sync_lock_path.write_text(now_iso(), encoding="utf-8")
            try:
                download_result = subprocess.run(
                    scp_command("-r", f"{ssh_target()}:{remote_run_dir}", str(download_parent)),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=ssh_subprocess_env(),
                )
            finally:
                sync_lock_path.unlink(missing_ok=True)
            if download_result.returncode == 0 and target_local_run_dir.exists():
                return mark_task_completed_from_local_dir(conn, row, target_local_run_dir)
            if local_run_dir.exists() and (local_run_dir / "run_summary.json").exists():
                return mark_task_completed_from_local_dir(conn, row, local_run_dir)
        if probe["audit_running"] or probe["llm_running"]:
            return mark_task_running_if_stale(conn, row, task_id)

        progress = read_remote_json_file(f"{remote_run_dir}/model_risk_progress.json")
        if status == "pending":
            launch_audit_task(task_id)
            update_task_status(task_id, status="running", error_message="")
            return fetch_task(conn, task_id)

        # If there is no visible audit process but the progress file is still
        # updating recently, keep polling instead of freezing the UI on failed.
        if remote_progress_is_recent(progress):
            return mark_task_running_if_stale(conn, row, task_id)

        # Give a running remote task a cooldown window before flipping to failed.
        # This avoids visible status flapping when SSH/process probing misses one poll.
        if status == "running" and task_status_is_recent(row, DEFAULT_REMOTE_FAILURE_GRACE_SECONDS):
            return row

        if probe["run_dir"] or progress:
            update_task_status(task_id, status="failed", error_message="remote audit pipeline interrupted")
            return fetch_task(conn, task_id)

        update_task_status(task_id, status="failed", error_message="remote audit pipeline did not start")
        return fetch_task(conn, task_id)

    # local task
    local_probe = local_task_probe(row)
    local_run_dir = IMPORTED_RUNS_DIR / row["run_name"]
    if local_probe["run_summary"]:
        return mark_task_completed_from_local_dir(conn, row, local_run_dir)
    if status == "pending":
        launch_audit_task(task_id)
        update_task_status(task_id, status="running", error_message="")
        return fetch_task(conn, task_id)
    if local_task_is_active(task_id):
        return mark_task_running_if_stale(conn, row, task_id)
    if status == "running" and task_status_is_recent(row, DEFAULT_REMOTE_FAILURE_GRACE_SECONDS):
        return row
    update_task_status(task_id, status="failed", error_message="local audit pipeline interrupted")
    return fetch_task(conn, task_id)


def latest_decisions_by_key(conn: sqlite3.Connection, run_id: int) -> dict[tuple[str, int], dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            ri.split,
            ri.line_no,
            rd.decision,
            rd.action,
            rd.corrected_label_json,
            rd.owner,
            rd.notes,
            rd.updated_at
        FROM review_items ri
        JOIN review_decisions rd ON rd.review_item_id = ri.id
        WHERE ri.run_id = ?
        AND rd.id IN (
            SELECT MAX(id)
            FROM review_decisions
            WHERE review_item_id = ri.id
        )
        """,
        (run_id,),
    ).fetchall()
    result: dict[tuple[str, int], dict[str, Any]] = {}
    for row in rows:
        result[(row["split"], int(row["line_no"]))] = {
            "decision": row["decision"],
            "action": row["action"],
            "corrected_label_json": loads(row["corrected_label_json"], None),
            "owner": row["owner"] or "",
            "notes": row["notes"] or "",
            "updated_at": row["updated_at"],
        }
    return result


def export_cleaned_dataset(conn: sqlite3.Connection, run_id: int, export_name: str | None) -> dict[str, Any]:
    run = fetch_run(conn, run_id)
    dataset_dir = Path(run["dataset_dir"])
    if not dataset_dir.exists():
        raise HTTPException(status_code=400, detail=f"dataset_dir not found: {dataset_dir}")

    run_name = run["run_name"]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    export_dir = EXPORTS_DIR / f"{export_name or run_name}_{stamp}"
    cleaned_dir = export_dir / "cleaned_dataset"
    cleaned_dir.mkdir(parents=True, exist_ok=True)

    decisions = latest_decisions_by_key(conn, run_id)
    summary = {"keep": 0, "replace_label": 0, "drop": 0, "hold": 0}
    label_changes: list[dict[str, Any]] = []
    dropped_rows: list[dict[str, Any]] = []

    for split_name in ("train", "val"):
        source_path = dataset_dir / f"{split_name}.jsonl"
        if not source_path.exists():
            continue
        target_path = cleaned_dir / f"{split_name}.jsonl"
        lines_out: list[str] = []
        with source_path.open("r", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, start=1):
                obj = json.loads(line)
                decision = decisions.get((split_name, line_no))
                if decision is None:
                    lines_out.append(json.dumps(obj, ensure_ascii=False))
                    continue

                action = decision["action"]
                summary[action] = summary.get(action, 0) + 1
                if action == "drop":
                    dropped_rows.append(
                        {
                            "split": split_name,
                            "line_no": line_no,
                            "image": obj.get("image", ""),
                            "decision": decision["decision"],
                            "action": action,
                            "owner": decision["owner"],
                            "notes": decision["notes"],
                        }
                    )
                    continue

                if action == "replace_label":
                    corrected = decision["corrected_label_json"]
                    convs = obj.get("conversations", [])
                    if len(convs) > 1:
                        before = convs[1].get("value")
                        convs[1]["value"] = json.dumps(corrected, ensure_ascii=False)
                    else:
                        before = None
                    label_changes.append(
                        {
                            "split": split_name,
                            "line_no": line_no,
                            "image": obj.get("image", ""),
                            "before_label": before,
                            "after_label": json.dumps(corrected, ensure_ascii=False),
                            "decision": decision["decision"],
                            "action": action,
                            "owner": decision["owner"],
                            "notes": decision["notes"],
                        }
                    )

                lines_out.append(json.dumps(obj, ensure_ascii=False))

        target_path.write_text("\n".join(lines_out) + ("\n" if lines_out else ""), encoding="utf-8")

    if label_changes:
        with (export_dir / "label_changes.csv").open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=["split", "line_no", "image", "before_label", "after_label", "decision", "action", "owner", "notes"],
            )
            writer.writeheader()
            writer.writerows(label_changes)
    else:
        (export_dir / "label_changes.csv").write_text("", encoding="utf-8")

    if dropped_rows:
        with (export_dir / "dropped_rows.csv").open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=["split", "line_no", "image", "decision", "action", "owner", "notes"],
            )
            writer.writeheader()
            writer.writerows(dropped_rows)
    else:
        (export_dir / "dropped_rows.csv").write_text("", encoding="utf-8")

    writeback_summary = {
        "run_id": run_id,
        "run_name": run_name,
        "dataset_dir": str(dataset_dir),
        "export_dir": str(export_dir),
        "cleaned_dataset_dir": str(cleaned_dir),
        "decision_counts": summary,
        "label_change_count": len(label_changes),
        "dropped_count": len(dropped_rows),
        "generated_at": now_iso(),
    }
    (export_dir / "writeback_summary.json").write_text(
        json.dumps(writeback_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return writeback_summary


def build_task_config(
    dataset_name: str,
    dataset_dir: Path | str,
    run_name: str,
    *,
    output_root: Path | str | None = None,
    model_endpoint: str | None = None,
) -> dict[str, Any]:
    model_enabled = bool(os.environ.get(DEFAULT_API_KEY_ENV, "").strip())
    endpoint_value = (model_endpoint or DEFAULT_MODEL_ENDPOINT).strip()
    model_name = DEFAULT_MODEL_NAME.strip()
    return {
        "dataset_name": dataset_name,
        "dataset_dir": str(dataset_dir),
        "splits": ["train.jsonl", "val.jsonl"],
        "output_root": str(output_root or IMPORTED_RUNS_DIR),
        "run_name": run_name,
        "consistency": {"fast_window_seconds": 90},
        "manual_review": {"max_items": 100},
        "auto_fix": {
            "enabled": True,
            "use_rule_fixes": True,
            "use_model_fixes": model_enabled,
            "max_rounds": 1,
            "max_rows_per_round": 200,
            "target_static_issue_count": 0,
            "target_static_issue_ratio": 0.0,
            "endpoint": endpoint_value,
            "model_name": model_name,
            "api_key_env": DEFAULT_API_KEY_ENV,
            "timeout": 120,
            "max_image_side": 1280,
            "request_gap_ms": 0,
            "temperature": 0,
            "max_tokens": 4096,
        },
        "model_risk": {
            "enabled": model_enabled,
            "endpoint": endpoint_value,
            "model_name": model_name,
            "api_key_env": DEFAULT_API_KEY_ENV,
            "selection": "top_risk",
            "sample_size": 300,
            "max_rows": 300,
            "timeout": 120,
            "max_image_side": 1280,
            "request_gap_ms": 0,
            "temperature": 0,
            "max_tokens": 2048,
            "resume": True,
            "max_attempts": 3,
            "retry_backoff_seconds": 2,
            "retry_request_errors": True,
            "retry_validation_failures": True,
        },
    }


def write_task_log(log_path: Path, text: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(text)
        if not text.endswith("\n"):
            fh.write("\n")


def is_stop_requested(task_id: int) -> bool:
    return task_id in STOP_REQUESTED_TASKS


def clear_stop_request(task_id: int) -> None:
    STOP_REQUESTED_TASKS.discard(task_id)


def run_subprocess(
    command: list[str],
    cwd: Path,
    log_path: Path,
    env: dict[str, str] | None = None,
    *,
    task_id: int | None = None,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    if task_id is not None:
        with ACTIVE_SUBPROCESSES_LOCK:
            ACTIVE_SUBPROCESSES[task_id] = process
    stdout = ""
    stderr = ""
    try:
        while True:
            try:
                stdout, stderr = process.communicate(timeout=0.5)
                break
            except subprocess.TimeoutExpired:
                if task_id is not None and is_stop_requested(task_id):
                    process.kill()
                    stdout, stderr = process.communicate()
                    result = subprocess.CompletedProcess(command, -9, stdout, stderr)
                    write_task_log(log_path, f"$ {' '.join(command)}")
                    if stdout:
                        write_task_log(log_path, stdout)
                    if stderr:
                        write_task_log(log_path, stderr)
                    return result
                time.sleep(0.05)
    finally:
        if task_id is not None:
            with ACTIVE_SUBPROCESSES_LOCK:
                ACTIVE_SUBPROCESSES.pop(task_id, None)
    result = subprocess.CompletedProcess(command, process.returncode or 0, stdout, stderr)
    write_task_log(log_path, f"$ {' '.join(command)}")
    if result.stdout:
        write_task_log(log_path, result.stdout)
    if result.stderr:
        write_task_log(log_path, result.stderr)
    return result


def update_task_status(task_id: int, **fields: Any) -> None:
    conn = standalone_conn()
    try:
        fetch_task(conn, task_id)
        assignments = ", ".join(f"{key} = ?" for key in fields.keys())
        params = list(fields.values()) + [now_iso(), task_id]
        with transaction(conn):
            conn.execute(
                f"UPDATE audit_tasks SET {assignments}, updated_at = ? WHERE id = ?",
                params,
            )
    finally:
        conn.close()


def stop_task_execution(task_id: int) -> None:
    STOP_REQUESTED_TASKS.add(task_id)
    with ACTIVE_SUBPROCESSES_LOCK:
        process = ACTIVE_SUBPROCESSES.get(task_id)
    if process is not None and process.poll() is None:
        try:
            process.kill()
        except OSError:
            pass


def delete_run_record(conn: sqlite3.Connection, run_id: int) -> None:
    row = fetch_run(conn, run_id)
    platform_run_dir = row["platform_run_dir"] or ""
    output_dir = row["output_dir"] or ""
    with transaction(conn):
        conn.execute("UPDATE audit_tasks SET source_run_id = NULL WHERE source_run_id = ?", (run_id,))
        conn.execute("UPDATE audit_tasks SET result_run_id = NULL WHERE result_run_id = ?", (run_id,))
        conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
    safe_remove_path(platform_run_dir)
    # Only delete output_dir if it is one of our local managed directories.
    if output_dir and (output_dir.startswith(str(IMPORTED_RUNS_DIR)) or output_dir.startswith(str(EXPORTS_DIR))):
        safe_remove_path(output_dir)


def delete_task_record(conn: sqlite3.Connection, task_id: int) -> None:
    row = fetch_task(conn, task_id)
    status = row["status"]
    if status in {"pending", "running"}:
        try:
            stop_task(conn, task_id)
        except Exception:
            stop_task_execution(task_id)
    row = fetch_task(conn, task_id)
    config_path = row["config_path"] or ""
    log_path = row["log_path"] or ""
    with transaction(conn):
        conn.execute("DELETE FROM audit_tasks WHERE id = ?", (task_id,))
    safe_remove_path(config_path)
    safe_remove_path(log_path)


def execute_local_audit_task(task_id: int) -> None:
    conn = standalone_conn()
    try:
        task = fetch_task(conn, task_id)
        log_path = Path(task["log_path"])
        config_path = Path(task["config_path"])
        result_run_dir = IMPORTED_RUNS_DIR / task["run_name"]
        update_task_status(task_id, status="running", error_message="")
        write_task_log(log_path, f"[{now_iso()}] task started")

        audit_cmd = [
            os.environ.get("PYTHON", "python"),
            str(PIPELINE_DIR / "run_audit.py"),
            "--config",
            str(config_path),
        ]
        audit_result = run_subprocess(audit_cmd, PIPELINE_DIR, log_path, task_id=task_id)
        if audit_result.returncode == -9 or is_stop_requested(task_id):
            update_task_status(task_id, status="failed", error_message="鐢ㄦ埛鎵嬪姩鍋滄")
            clear_stop_request(task_id)
            return
        if audit_result.returncode != 0:
            update_task_status(task_id, status="failed", error_message="audit pipeline failed")
            return

        llm_report_path = ""
        llm_warning = ""
        if Path(result_run_dir / "run_summary.json").exists() and os.environ.get(DEFAULT_API_KEY_ENV, "").strip():
            llm_cmd = [
                os.environ.get("PYTHON", "python"),
                str(PIPELINE_DIR / "generate_llm_analysis_report.py"),
                "--run-dir",
                str(result_run_dir),
                "--endpoint",
                DEFAULT_MODEL_ENDPOINT,
                "--model-name",
                DEFAULT_MODEL_NAME,
                "--api-key-env",
                DEFAULT_API_KEY_ENV,
            ]
            llm_result = run_subprocess(llm_cmd, PIPELINE_DIR, log_path, task_id=task_id)
            if llm_result.returncode == -9 or is_stop_requested(task_id):
                update_task_status(task_id, status="failed", error_message="鐢ㄦ埛鎵嬪姩鍋滄")
                clear_stop_request(task_id)
                return
            if llm_result.returncode == 0 and (result_run_dir / "llm_analysis_report.md").exists():
                llm_report_path = str(result_run_dir / "llm_analysis_report.md")
            else:
                llm_warning = "LLM report generation failed"
        else:
            llm_warning = f"LLM report skipped: missing env {DEFAULT_API_KEY_ENV}"

        imported = import_run(conn, result_run_dir)
        update_task_status(
            task_id,
            status="completed",
            result_run_id=imported["run_id"],
            result_run_dir=str(result_run_dir),
            audit_report_path=str(result_run_dir / "audit_report.md"),
            llm_report_path=llm_report_path,
            error_message=llm_warning,
        )
        write_task_log(log_path, f"[{now_iso()}] task completed")
    except Exception as exc:  # pragma: no cover
        update_task_status(task_id, status="failed", error_message=str(exc))
    finally:
        clear_stop_request(task_id)
        conn.close()


def remote_runtime_env_exports() -> str:
    api_key = os.environ.get(DEFAULT_API_KEY_ENV, "").strip()
    exports: list[str] = []
    if api_key:
        exports.append(f"{DEFAULT_API_KEY_ENV}={shlex.quote(api_key)}")
    return " ".join(exports)


def remote_task_paths(run_name: str) -> tuple[str, str]:
    remote_config_path = f"{DEFAULT_REMOTE_CONFIG_DIR}/{run_name}.json"
    remote_run_dir = f"{DEFAULT_REMOTE_RUNS_DIR}/{run_name}"
    return remote_config_path, remote_run_dir


def execute_remote_audit_task(task_id: int) -> None:
    conn = standalone_conn()
    try:
        task = fetch_task(conn, task_id)
        log_path = Path(task["log_path"])
        local_config_path = Path(task["config_path"])
        run_name = task["run_name"]
        local_run_dir = IMPORTED_RUNS_DIR / run_name
        remote_config_path, remote_run_dir = remote_task_paths(run_name)

        update_task_status(task_id, status="running", error_message="")
        write_task_log(log_path, f"[{now_iso()}] remote task started")

        local_config = build_task_config(
            task["dataset_name"],
            task["dataset_dir"],
            run_name,
            output_root=DEFAULT_REMOTE_RUNS_DIR,
            model_endpoint=DEFAULT_REMOTE_MODEL_ENDPOINT,
        )
        local_config_path.write_text(json.dumps(local_config, ensure_ascii=False, indent=2), encoding="utf-8")

        mkdir_result = run_subprocess(
            ssh_command(
                f"mkdir -p {shlex.quote(DEFAULT_REMOTE_CONFIG_DIR)} {shlex.quote(DEFAULT_REMOTE_RUNS_DIR)}"
            ),
            BASE_DIR,
            log_path,
            env=ssh_subprocess_env(),
            task_id=task_id,
        )
        if mkdir_result.returncode == -9 or is_stop_requested(task_id):
            update_task_status(task_id, status="failed", error_message="鐢ㄦ埛鎵嬪姩鍋滄")
            clear_stop_request(task_id)
            return
        if mkdir_result.returncode != 0:
            update_task_status(task_id, status="failed", error_message="remote setup failed")
            return

        copy_config_result = run_subprocess(
            scp_command(str(local_config_path), f"{ssh_target()}:{remote_config_path}"),
            BASE_DIR,
            log_path,
            env=ssh_subprocess_env(),
            task_id=task_id,
        )
        if copy_config_result.returncode == -9 or is_stop_requested(task_id):
            update_task_status(task_id, status="failed", error_message="鐢ㄦ埛鎵嬪姩鍋滄")
            clear_stop_request(task_id)
            return
        if copy_config_result.returncode != 0:
            update_task_status(task_id, status="failed", error_message="remote config upload failed")
            return

        env_exports = remote_runtime_env_exports()
        audit_prefix = f"{env_exports} " if env_exports else ""
        audit_cmd = (
            f"cd {shlex.quote(DEFAULT_REMOTE_PIPELINE_DIR)} && "
            f"{audit_prefix}python3 run_audit.py --config {shlex.quote(remote_config_path)}"
        )
        audit_result = run_subprocess(ssh_command(audit_cmd), BASE_DIR, log_path, env=ssh_subprocess_env(), task_id=task_id)
        if audit_result.returncode == -9 or is_stop_requested(task_id):
            update_task_status(task_id, status="failed", error_message="鐢ㄦ埛鎵嬪姩鍋滄")
            clear_stop_request(task_id)
            return
        if audit_result.returncode != 0:
            update_task_status(task_id, status="failed", error_message="remote audit pipeline failed")
            return

        llm_report_path = ""
        llm_warning = ""
        if os.environ.get(DEFAULT_API_KEY_ENV, "").strip():
            llm_cmd = (
                f"cd {shlex.quote(DEFAULT_REMOTE_PIPELINE_DIR)} && "
                f"{audit_prefix}python3 generate_llm_analysis_report.py "
                f"--run-dir {shlex.quote(remote_run_dir)} "
                f"--endpoint {shlex.quote(DEFAULT_REMOTE_MODEL_ENDPOINT)} "
                f"--model-name {shlex.quote(DEFAULT_MODEL_NAME)} "
                f"--api-key-env {shlex.quote(DEFAULT_API_KEY_ENV)}"
            )
            llm_result = run_subprocess(ssh_command(llm_cmd), BASE_DIR, log_path, env=ssh_subprocess_env(), task_id=task_id)
            if llm_result.returncode == -9 or is_stop_requested(task_id):
                update_task_status(task_id, status="failed", error_message="鐢ㄦ埛鎵嬪姩鍋滄")
                clear_stop_request(task_id)
                return
            if llm_result.returncode == 0:
                llm_report_path = str(local_run_dir / "llm_analysis_report.md")
            else:
                llm_warning = "remote LLM report generation failed"
        else:
            llm_warning = f"LLM report skipped: missing env {DEFAULT_API_KEY_ENV}"

        if local_run_dir.exists():
            shutil.rmtree(local_run_dir)
        download_result = run_subprocess(
            scp_command("-r", f"{ssh_target()}:{remote_run_dir}", str(IMPORTED_RUNS_DIR)),
            BASE_DIR,
            log_path,
            env=ssh_subprocess_env(),
            task_id=task_id,
        )
        if download_result.returncode == -9 or is_stop_requested(task_id):
            update_task_status(task_id, status="failed", error_message="鐢ㄦ埛鎵嬪姩鍋滄")
            clear_stop_request(task_id)
            return
        if download_result.returncode != 0 or not local_run_dir.exists():
            update_task_status(task_id, status="failed", error_message="remote run download failed")
            return

        imported = import_run(conn, local_run_dir)
        if not (local_run_dir / "llm_analysis_report.md").exists():
            llm_report_path = ""
        update_task_status(
            task_id,
            status="completed",
            result_run_id=imported["run_id"],
            result_run_dir=str(local_run_dir),
            audit_report_path=str(local_run_dir / "audit_report.md"),
            llm_report_path=llm_report_path,
            error_message=llm_warning,
        )
        write_task_log(log_path, f"[{now_iso()}] remote task completed")
    except Exception as exc:  # pragma: no cover
        update_task_status(task_id, status="failed", error_message=str(exc))
    finally:
        clear_stop_request(task_id)
        conn.close()


def execute_audit_task(task_id: int) -> None:
    conn = standalone_conn()
    try:
        task = fetch_task(conn, task_id)
        task_type = task["task_type"]
    finally:
        conn.close()
    if task_type == "audit_remote":
        execute_remote_audit_task(task_id)
        return
    execute_local_audit_task(task_id)


def launch_audit_task(task_id: int) -> None:
    thread = threading.Thread(target=execute_audit_task, args=(task_id,), daemon=True)
    thread.start()


def create_audit_task(conn: sqlite3.Connection, source_run_id: int | None, payload: StartAuditTaskRequest) -> dict[str, Any]:
    source_run = fetch_run(conn, source_run_id) if source_run_id is not None else None
    dataset_dir_value = (payload.dataset_dir or (source_run["dataset_dir"] if source_run is not None else "")).strip()
    execution_mode = payload.execution_mode or "auto"
    remote_mode = execution_mode == "server" or (
        execution_mode == "auto" and is_remote_path_like(dataset_dir_value) and not Path(dataset_dir_value).exists()
    )
    if not dataset_dir_value:
        raise HTTPException(status_code=400, detail="dataset_dir is required")
    if remote_mode:
        detect_remote_intake_path_kind(dataset_dir_value)
        dataset_dir_text = dataset_dir_value
    else:
        dataset_dir = Path(dataset_dir_value)
        if not dataset_dir.exists():
            raise HTTPException(status_code=400, detail=f"dataset_dir not found: {dataset_dir}")
        dataset_dir_text = str(dataset_dir)

    dataset_name = payload.dataset_name or (
        source_run["dataset_name"] if source_run is not None else Path(dataset_dir_text.rstrip("/")).name
    )
    run_name = payload.run_name or f"{dataset_name}_audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    config = build_task_config(
        dataset_name,
        dataset_dir_text,
        run_name,
        output_root=DEFAULT_REMOTE_RUNS_DIR if remote_mode else IMPORTED_RUNS_DIR,
        model_endpoint=DEFAULT_REMOTE_MODEL_ENDPOINT if remote_mode else DEFAULT_MODEL_ENDPOINT,
    )
    config_path = GENERATED_CONFIG_DIR / f"{run_name}.json"
    log_path = TASK_LOG_DIR / f"{run_name}.log"
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    timestamp = now_iso()

    with transaction(conn):
        cursor = conn.execute(
            """
            INSERT INTO audit_tasks (
                task_type, source_run_id, dataset_name, dataset_dir, run_name, config_path, log_path,
                status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "audit_remote" if remote_mode else "audit",
                source_run_id,
                dataset_name,
                dataset_dir_text,
                run_name,
                str(config_path),
                str(log_path),
                "pending",
                timestamp,
                timestamp,
            ),
        )
        task_id = int(cursor.lastrowid)

    launch_audit_task(task_id)
    return task_response(conn, fetch_task(conn, task_id))


def resume_task(conn: sqlite3.Connection, task_id: int) -> dict[str, Any]:
    row = fetch_task(conn, task_id)
    if row["status"] == "completed":
        raise HTTPException(status_code=400, detail="completed task does not need resume")
    if row["task_type"] == "audit_remote":
        probe = remote_task_probe(row)
        local_run_dir = IMPORTED_RUNS_DIR / row["run_name"]
        remote_run_dir = remote_task_paths(row["run_name"])[1]
        if probe["run_summary"]:
            if local_run_dir.exists():
                shutil.rmtree(local_run_dir)
            download_result = subprocess.run(
                scp_command("-r", f"{ssh_target()}:{remote_run_dir}", str(IMPORTED_RUNS_DIR)),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=ssh_subprocess_env(),
            )
            if download_result.returncode == 0 and local_run_dir.exists():
                row = mark_task_completed_from_local_dir(conn, row, local_run_dir)
                return task_response(conn, row)
        if probe["audit_running"] or probe["llm_running"]:
            update_task_status(task_id, status="running", error_message="")
            return task_response(conn, fetch_task(conn, task_id))
    else:
        local_probe = local_task_probe(row)
        local_run_dir = IMPORTED_RUNS_DIR / row["run_name"]
        if local_probe["run_summary"]:
            row = mark_task_completed_from_local_dir(conn, row, local_run_dir)
            return task_response(conn, row)

    update_task_status(task_id, status="pending", error_message="")
    launch_audit_task(task_id)
    return task_response(conn, fetch_task(conn, task_id))


def stop_task(conn: sqlite3.Connection, task_id: int) -> dict[str, Any]:
    row = fetch_task(conn, task_id)
    if row["status"] in {"completed", "failed"}:
        raise HTTPException(status_code=400, detail="task is not running")

    stop_task_execution(task_id)
    if row["task_type"] == "audit_remote":
        remote_config_path, remote_run_dir = remote_task_paths(row["run_name"])
        audit_pattern = shlex.quote(f"run_audit.py --config {remote_config_path}")
        llm_pattern = shlex.quote(f"generate_llm_analysis_report.py --run-dir {remote_run_dir}")
        stop_command = (
            f"pkill -f {audit_pattern} >/dev/null 2>&1 || true; "
            f"pkill -f {llm_pattern} >/dev/null 2>&1 || true"
        )
        try:
            subprocess.run(
                ssh_command(stop_command),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=ssh_subprocess_env(),
                timeout=DEFAULT_REMOTE_STATUS_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            pass
    update_task_status(task_id, status="failed", error_message="鐢ㄦ埛鎵嬪姩鍋滄")
    clear_stop_request(task_id)
    return task_response(conn, fetch_task(conn, task_id), allow_remote_lookup=False)


def recover_incomplete_tasks() -> None:
    conn = standalone_conn()
    try:
        rows = conn.execute("SELECT * FROM audit_tasks WHERE status IN ('pending', 'running') ORDER BY id ASC").fetchall()
        for row in rows:
            try:
                reconcile_task_state(conn, row)
            except Exception:
                continue
    finally:
        conn.close()


def create_app() -> FastAPI:
    ensure_dirs()
    app = FastAPI(title="Dataset Review Platform Backend", version="0.2.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def _startup_recover_tasks() -> None:
        recover_incomplete_tasks()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/static/{filename}")
    def static_file(filename: str) -> FileResponse:
        path = STATIC_DIR / filename
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="static file not found")
        return FileResponse(path)

    @app.get("/api/runs")
    def list_runs(conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
        rows = conn.execute("SELECT * FROM runs ORDER BY updated_at DESC, id DESC").fetchall()
        return {"items": [run_response(conn, row) for row in rows]}

    @app.post("/api/runs/import")
    def api_import_run(payload: ImportRunRequest, conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
        return import_run(conn, Path(payload.run_dir))

    @app.post("/api/intake")
    def api_intake_path(payload: IntakePathRequest, conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
        raw_path = payload.path.strip()
        if not raw_path:
            raise HTTPException(status_code=400, detail="path is required")
        local_path = Path(raw_path)
        if local_path.exists():
            kind = detect_intake_path_kind(local_path)
            if kind == "audit_run":
                imported = import_run(conn, local_path)
                return {
                    "mode": "imported_run",
                    "path_kind": kind,
                    "run": imported,
                }
        elif is_remote_path_like(raw_path):
            kind = detect_remote_intake_path_kind(raw_path)
            if kind == "server_audit_run":
                imported = import_remote_run(conn, raw_path)
                return {
                    "mode": "imported_run",
                    "path_kind": kind,
                    "run": imported,
                }
        else:
            raise HTTPException(status_code=400, detail=f"path not found: {raw_path}")

        if kind == "audit_run":
            imported = import_run(conn, local_path)
            return {
                "mode": "imported_run",
                "path_kind": kind,
                "run": imported,
            }
        task = create_audit_task(
            conn,
            None,
            StartAuditTaskRequest(
                dataset_dir=raw_path,
                dataset_name=payload.dataset_name,
                run_name=payload.run_name,
                generate_llm_report=payload.generate_llm_report,
                execution_mode="server" if kind.startswith("server_") else "auto",
            ),
        )
        return {
            "mode": "audit_task",
            "path_kind": kind,
            "task": task,
        }

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: int, conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
        row = fetch_run(conn, run_id)
        return run_response(conn, row)

    @app.delete("/api/runs/{run_id}")
    def delete_run(run_id: int, conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
        delete_run_record(conn, run_id)
        return {"ok": True, "run_id": run_id}

    @app.get("/api/runs/{run_id}/reports")
    def get_run_reports(run_id: int, conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
        row = fetch_run(conn, run_id)
        return load_run_reports(row)

    @app.get("/api/runs/{run_id}/auto-fix-records")
    def get_run_auto_fix_records(run_id: int, conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
        row = fetch_run(conn, run_id)
        return load_auto_fix_artifacts(row)

    @app.get("/api/runs/{run_id}/agent-analysis")
    def get_run_agent_analysis(run_id: int, conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
        row = fetch_run(conn, run_id)
        return build_agent_analysis(conn, row)

    @app.post("/api/runs/{run_id}/acceptance-report")
    def create_acceptance_report(run_id: int, conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
        row = fetch_run(conn, run_id)
        return generate_acceptance_report(conn, row)

    @app.post("/api/runs/{run_id}/start-audit")
    def start_audit(run_id: int, payload: StartAuditTaskRequest, conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
        return create_audit_task(conn, run_id, payload)

    @app.post("/api/tasks/start-audit")
    def start_dataset_audit(payload: StartAuditTaskRequest, conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
        if not payload.dataset_dir:
            raise HTTPException(status_code=400, detail="dataset_dir is required")
        return create_audit_task(conn, None, payload)

    @app.get("/api/runs/{run_id}/items")
    def list_run_items(
        run_id: int,
        risk_bucket: str | None = None,
        split: str | None = Query(default=None, pattern="^(train|val)?$"),
        decision_status: str | None = Query(default=None, pattern="^(undecided|decided)?$"),
        action: str | None = Query(default=None, pattern="^(keep|replace_label|drop|hold)?$"),
        owner: str | None = None,
        issue_source: str | None = Query(default=None, pattern="^(static|consistency|model|validation)?$"),
        q: str | None = None,
        limit: int = Query(default=50, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        conn: sqlite3.Connection = Depends(get_conn),
    ) -> dict[str, Any]:
        fetch_run(conn, run_id)
        base_sql = "SELECT * FROM review_items WHERE run_id = ?"
        params: list[Any] = [run_id]
        if risk_bucket:
            base_sql += " AND risk_bucket = ?"
            params.append(risk_bucket)
        if split:
            base_sql += " AND split = ?"
            params.append(split)
        rows = conn.execute(base_sql + " ORDER BY risk_score DESC, id ASC", tuple(params)).fetchall()
        items = [item_response(conn, row) for row in rows]
        if decision_status == "decided":
            items = [item for item in items if item["decision"] is not None]
        elif decision_status == "undecided":
            items = [item for item in items if item["decision"] is None]
        if action:
            items = [item for item in items if item["decision"] and item["decision"]["action"] == action]
        if owner:
            owner_query = owner.strip().lower()
            items = [item for item in items if item["decision"] and owner_query in (item["decision"].get("owner", "") or "").lower()]
        if issue_source == "static":
            items = [item for item in items if item.get("static_issues")]
        elif issue_source == "consistency":
            items = [item for item in items if item.get("consistency_issues")]
        elif issue_source == "model":
            items = [item for item in items if item.get("model_issues")]
        elif issue_source == "validation":
            items = [item for item in items if item.get("model_validation_issues")]
        query = (q or "").strip().lower()
        if query:
            items = [
                item
                for item in items
                if query in (item.get("order_id", "") or "").lower()
                or query in (item.get("scene_id", "") or "").lower()
                or query in (item.get("image", "") or "").lower()
                or query in (item.get("risk_bucket", "") or "").lower()
                or any(query in str(value).lower() for value in item.get("static_issues", []))
                or any(query in str(value).lower() for value in item.get("consistency_issues", []))
                or any(query in str(value).lower() for value in item.get("model_issues", []))
                or any(query in str(value).lower() for value in item.get("model_validation_issues", []))
            ]
        total = len(items)
        return {"items": items[offset : offset + limit], "total": total, "limit": limit, "offset": offset}

    @app.get("/api/items/{item_id}")
    def get_item(item_id: int, conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
        return item_response(conn, fetch_item(conn, item_id))

    @app.get("/api/items/{item_id}/image")
    def get_item_image(item_id: int, conn: sqlite3.Connection = Depends(get_conn)) -> FileResponse:
        item = fetch_item(conn, item_id)
        image_path = Path(item["image"])
        if not image_path.exists():
            raise HTTPException(status_code=404, detail="image file not found")
        return FileResponse(image_path)

    @app.get("/api/items/{item_id}/raw-image")
    def get_item_raw_image(item_id: int, conn: sqlite3.Connection = Depends(get_conn)) -> FileResponse:
        item = fetch_item(conn, item_id)
        import_payload = loads(item["import_payload_json"], {})
        raw_image = import_payload.get("image") or item["image"]
        image_path = Path(raw_image)
        if not image_path.exists():
            image_path = Path(item["image"])
        if not image_path.exists():
            raise HTTPException(status_code=404, detail="raw image file not found")
        return FileResponse(image_path)

    @app.post("/api/items/{item_id}/decision")
    def save_decision(item_id: int, payload: DecisionRequest, conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
        if payload.decision not in VALID_DECISIONS:
            raise HTTPException(status_code=400, detail=f"invalid decision: {payload.decision}")
        if payload.action not in VALID_ACTIONS:
            raise HTTPException(status_code=400, detail=f"invalid action: {payload.action}")
        validate_corrected_label(payload.action, payload.corrected_label_json)
        fetch_item(conn, item_id)
        timestamp = now_iso()
        with transaction(conn):
            conn.execute(
                """
                INSERT INTO review_decisions (
                    review_item_id, decision, action, corrected_label_json, owner, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    payload.decision,
                    payload.action,
                    dumps(payload.corrected_label_json) if payload.corrected_label_json is not None else None,
                    payload.owner,
                    payload.notes,
                    timestamp,
                    timestamp,
                ),
            )
            conn.execute("UPDATE review_items SET updated_at = ? WHERE id = ?", (timestamp, item_id))
        return item_response(conn, fetch_item(conn, item_id))

    @app.post("/api/runs/{run_id}/export-cleaned")
    def api_export_cleaned(run_id: int, payload: ExportRequest, conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
        return export_cleaned_dataset(conn, run_id, payload.export_name)

    @app.get("/api/tasks")
    def list_tasks(conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
        rows = conn.execute("SELECT * FROM audit_tasks ORDER BY updated_at DESC, id DESC").fetchall()
        items: list[dict[str, Any]] = []
        live_lookup_budget = 3
        for row in rows:
            allow_remote_lookup = False
            if should_reconcile_task(row) and live_lookup_budget > 0:
                row = reconcile_task_state(conn, row)
                allow_remote_lookup = True
                live_lookup_budget -= 1
            items.append(task_response(conn, row, allow_remote_lookup=allow_remote_lookup))
        return {"items": items}

    @app.get("/api/tasks/{task_id}")
    def get_task(task_id: int, conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
        row = fetch_task(conn, task_id)
        if should_reconcile_task(row):
            row = reconcile_task_state(conn, row)
        return task_response(conn, row)

    @app.post("/api/tasks/{task_id}/resume")
    def api_resume_task(task_id: int, conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
        return resume_task(conn, task_id)

    @app.post("/api/tasks/{task_id}/stop")
    def api_stop_task(task_id: int, conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
        return stop_task(conn, task_id)

    @app.delete("/api/tasks/{task_id}")
    def api_delete_task(task_id: int, conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
        delete_task_record(conn, task_id)
        return {"ok": True, "task_id": task_id}

    @app.get("/api/tasks/{task_id}/log")
    def get_task_log(task_id: int, conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
        task = fetch_task(conn, task_id)
        log_path = Path(task["log_path"])
        return {
            "log_path": str(log_path),
            "content": log_path.read_text(encoding="utf-8") if log_path.exists() else "",
        }

    return app


app = create_app()

