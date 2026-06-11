from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from app.config import DATA_DIR

DB_PATH = DATA_DIR / "linkedin.db"


class StorageRepository:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _init_schema(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS invited_profiles (
                    profile_url TEXT PRIMARY KEY,
                    profile_name TEXT NOT NULL,
                    invited_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS run_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    sent_count INTEGER NOT NULL DEFAULT 0,
                    skipped_count INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT
                );
                """
            )

    def was_invited(self, profile_url: str) -> bool:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT 1 FROM invited_profiles WHERE profile_url = ?",
                (profile_url,),
            ).fetchone()
        return row is not None

    def register_invite(self, profile_url: str, profile_name: str) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO invited_profiles (profile_url, profile_name, invited_at)
                VALUES (?, ?, ?)
                """,
                (profile_url, profile_name, datetime.now().isoformat()),
            )

    def count_invites_since(self, since: datetime) -> int:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM invited_profiles WHERE invited_at >= ?",
                (since.isoformat(),),
            ).fetchone()
        return int(row["total"])

    def count_invites_today(self) -> int:
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return self.count_invites_since(today)

    def count_invites_this_week(self) -> int:
        now = datetime.now()
        week_start = now - timedelta(days=now.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        return self.count_invites_since(week_start)

    def total_invites(self) -> int:
        with self._connection() as connection:
            row = connection.execute("SELECT COUNT(*) AS total FROM invited_profiles").fetchone()
        return int(row["total"])

    def start_run(self) -> int:
        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO run_logs (started_at, status, sent_count, skipped_count)
                VALUES (?, 'running', 0, 0)
                """,
                (datetime.now().isoformat(),),
            )
            return int(cursor.lastrowid)

    def finish_run(
        self,
        run_id: int,
        status: str,
        sent_count: int,
        skipped_count: int,
        error_message: str | None = None,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE run_logs
                SET finished_at = ?, status = ?, sent_count = ?, skipped_count = ?, error_message = ?
                WHERE id = ?
                """,
                (
                    datetime.now().isoformat(),
                    status,
                    sent_count,
                    skipped_count,
                    error_message,
                    run_id,
                ),
            )

    def get_latest_run(self) -> dict | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT id, started_at, finished_at, status, sent_count, skipped_count, error_message
                FROM run_logs
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        return dict(row) if row else None

    def get_recent_runs(self, limit: int = 10) -> list[dict]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT id, started_at, finished_at, status, sent_count, skipped_count, error_message
                FROM run_logs
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
