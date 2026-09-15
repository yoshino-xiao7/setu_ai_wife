from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    cloud_job_id INTEGER,
    user_id INTEGER,
    storage_date TEXT NOT NULL DEFAULT '',
    prompt_cn TEXT NOT NULL,
    prompt_positive TEXT NOT NULL,
    prompt_negative TEXT NOT NULL,
    style_notes TEXT NOT NULL DEFAULT '',
    seed INTEGER NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    steps INTEGER NOT NULL,
    cfg REAL NOT NULL,
    checkpoint TEXT NOT NULL,
    generation_mode TEXT NOT NULL DEFAULT 'SINGLE',
    lora_name TEXT NOT NULL DEFAULT '',
    lora_strength REAL NOT NULL DEFAULT 0,
    second_lora_name TEXT NOT NULL DEFAULT '',
    second_lora_strength REAL NOT NULL DEFAULT 0,
    character_id TEXT NOT NULL DEFAULT '',
    second_character_id TEXT NOT NULL DEFAULT '',
    character_mask_json TEXT NOT NULL DEFAULT '',
    regional_global_positive TEXT NOT NULL DEFAULT '',
    regional_left_positive TEXT NOT NULL DEFAULT '',
    regional_right_positive TEXT NOT NULL DEFAULT '',
    nsfw_visibility_level TEXT NOT NULL DEFAULT 'STANDARD',
    job_type TEXT NOT NULL DEFAULT 'TEXT2IMG',
    parent_job_id INTEGER,
    inpaint_instruction TEXT NOT NULL DEFAULT '',
    inpaint_mask_json TEXT NOT NULL DEFAULT '',
    source_image_path TEXT NOT NULL DEFAULT '',
    light_hires INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    comfy_prompt_id TEXT NOT NULL DEFAULT '',
    image_path TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    error TEXT NOT NULL DEFAULT ''
);
"""


class JobStore:
    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.init()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
            additions = {
                "cloud_job_id": "INTEGER",
                "user_id": "INTEGER",
                "storage_date": "TEXT NOT NULL DEFAULT ''",
                "generation_mode": "TEXT NOT NULL DEFAULT 'SINGLE'",
                "second_lora_name": "TEXT NOT NULL DEFAULT ''",
                "second_lora_strength": "REAL NOT NULL DEFAULT 0",
                "character_id": "TEXT NOT NULL DEFAULT ''",
                "second_character_id": "TEXT NOT NULL DEFAULT ''",
                "character_mask_json": "TEXT NOT NULL DEFAULT ''",
                "regional_global_positive": "TEXT NOT NULL DEFAULT ''",
                "regional_left_positive": "TEXT NOT NULL DEFAULT ''",
                "regional_right_positive": "TEXT NOT NULL DEFAULT ''",
                "nsfw_visibility_level": "TEXT NOT NULL DEFAULT 'STANDARD'",
                "job_type": "TEXT NOT NULL DEFAULT 'TEXT2IMG'",
                "parent_job_id": "INTEGER",
                "inpaint_instruction": "TEXT NOT NULL DEFAULT ''",
                "inpaint_mask_json": "TEXT NOT NULL DEFAULT ''",
                "source_image_path": "TEXT NOT NULL DEFAULT ''",
                "light_hires": "INTEGER NOT NULL DEFAULT 0",
            }
            for name, definition in additions.items():
                if name not in columns:
                    conn.execute(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")

    def create_job(self, job: dict[str, Any]) -> None:
        keys = ", ".join(job.keys())
        placeholders = ", ".join(f":{key}" for key in job.keys())
        with self.connect() as conn:
            conn.execute(f"INSERT INTO jobs ({keys}) VALUES ({placeholders})", job)

    def update_job(self, job_id: str, **updates: Any) -> None:
        if not updates:
            return
        updates["updated_at"] = "CURRENT_TIMESTAMP"
        assignments = []
        params: dict[str, Any] = {"id": job_id}
        for key, value in updates.items():
            if value == "CURRENT_TIMESTAMP":
                assignments.append(f"{key} = CURRENT_TIMESTAMP")
            else:
                assignments.append(f"{key} = :{key}")
                params[key] = value
        with self.connect() as conn:
            conn.execute(f"UPDATE jobs SET {', '.join(assignments)} WHERE id = :id", params)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    def list_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 200)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_completed_jobs(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status = 'completed' AND image_path != '' ORDER BY created_at ASC"
            ).fetchall()
        return [dict(row) for row in rows]
