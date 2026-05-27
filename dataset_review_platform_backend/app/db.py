from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_name TEXT NOT NULL UNIQUE,
            dataset_name TEXT NOT NULL,
            dataset_dir TEXT NOT NULL,
            output_dir TEXT NOT NULL,
            platform_run_dir TEXT,
            total_rows INTEGER NOT NULL DEFAULT 0,
            static_issue_count INTEGER NOT NULL DEFAULT 0,
            consistency_issue_count INTEGER NOT NULL DEFAULT 0,
            model_prediction_rows INTEGER NOT NULL DEFAULT 0,
            model_flagged_rows INTEGER NOT NULL DEFAULT 0,
            review_pack_image_count INTEGER NOT NULL DEFAULT 0,
            summary_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_type TEXT NOT NULL,
            source_run_id INTEGER,
            result_run_id INTEGER,
            dataset_name TEXT NOT NULL,
            dataset_dir TEXT NOT NULL,
            run_name TEXT NOT NULL,
            config_path TEXT NOT NULL,
            log_path TEXT NOT NULL,
            result_run_dir TEXT,
            audit_report_path TEXT,
            llm_report_path TEXT,
            status TEXT NOT NULL,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (source_run_id) REFERENCES runs(id) ON DELETE SET NULL,
            FOREIGN KEY (result_run_id) REFERENCES runs(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS review_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            split TEXT NOT NULL,
            line_no INTEGER NOT NULL,
            image TEXT NOT NULL,
            order_id TEXT,
            scene_id TEXT,
            captured_at TEXT,
            risk_score INTEGER NOT NULL DEFAULT 0,
            risk_bucket TEXT NOT NULL,
            label_json TEXT,
            model_prediction_json TEXT,
            static_issues_json TEXT NOT NULL,
            consistency_issues_json TEXT NOT NULL,
            model_issues_json TEXT NOT NULL,
            model_validation_issues_json TEXT NOT NULL,
            model_mismatch_fields_json TEXT NOT NULL,
            import_payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE,
            UNIQUE(run_id, split, line_no)
        );

        CREATE TABLE IF NOT EXISTS review_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            review_item_id INTEGER NOT NULL,
            decision TEXT NOT NULL,
            action TEXT NOT NULL,
            corrected_label_json TEXT,
            owner TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (review_item_id) REFERENCES review_items(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_review_items_run_id ON review_items(run_id);
        CREATE INDEX IF NOT EXISTS idx_review_items_risk_bucket ON review_items(risk_bucket);
        CREATE INDEX IF NOT EXISTS idx_review_decisions_item_id ON review_decisions(review_item_id);
        CREATE INDEX IF NOT EXISTS idx_audit_tasks_source_run_id ON audit_tasks(source_run_id);
        CREATE INDEX IF NOT EXISTS idx_audit_tasks_status ON audit_tasks(status);
        """
    )
    ensure_column(conn, "runs", "platform_run_dir", "TEXT")
    conn.commit()


def ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, ddl: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
    if column_name not in columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}")


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
