import sqlite3
import json
import contextlib


class Database:
    def __init__(self, db_path: str = "ghost_writer.db"):
        self.db_path = db_path

    @contextlib.contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS drafts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT,
                    body TEXT,
                    pillar TEXT,
                    format TEXT,
                    source_activity_ids TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    published_at TEXT,
                    linkedin_post_id TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS activity_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    repo_full_name TEXT,
                    activity_type TEXT,
                    title TEXT,
                    description TEXT,
                    diff_summary TEXT,
                    pillar TEXT,
                    content_score REAL,
                    scanned_at TEXT DEFAULT (datetime('now')),
                    used_in_draft_id INTEGER,
                    raw_data TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    draft_id INTEGER,
                    linkedin_url TEXT,
                    posted_at TEXT,
                    impressions INTEGER DEFAULT 0,
                    likes INTEGER DEFAULT 0,
                    comments INTEGER DEFAULT 0,
                    shares INTEGER DEFAULT 0
                )
                """
            )

    def save_draft(self, title: str, body: str, pillar: str, format: str, source_activity_ids: list) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO drafts (title, body, pillar, format, source_activity_ids)
                VALUES (?, ?, ?, ?, ?)
                """,
                (title, body, pillar, format, json.dumps(source_activity_ids)),
            )
            return cursor.lastrowid

    def get_draft(self, draft_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM drafts WHERE id = ?", (draft_id,)
            ).fetchone()
            if row is None:
                return None
            return dict(row)

    def list_drafts(self, status: str | None = None) -> list[dict]:
        with self._connect() as conn:
            if status is not None:
                rows = conn.execute(
                    "SELECT * FROM drafts WHERE status = ?", (status,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM drafts").fetchall()
            return [dict(r) for r in rows]

    def update_draft(self, draft_id: int, **fields) -> None:
        if not fields:
            return
        fields["updated_at"] = "datetime('now')"
        set_parts = []
        values = []
        for key, value in fields.items():
            if key == "updated_at":
                set_parts.append("updated_at = datetime('now')")
            else:
                set_parts.append(f"{key} = ?")
                values.append(value)
        values.append(draft_id)
        sql = f"UPDATE drafts SET {', '.join(set_parts)} WHERE id = ?"
        with self._connect() as conn:
            conn.execute(sql, values)

    def save_activities(self, activities: list[dict]) -> list[int]:
        ids = []
        with self._connect() as conn:
            for activity in activities:
                cursor = conn.execute(
                    """
                    INSERT INTO activity_log
                        (repo_full_name, activity_type, title, description,
                         diff_summary, pillar, content_score, raw_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        activity.get("repo_full_name"),
                        activity.get("activity_type"),
                        activity.get("title"),
                        activity.get("description"),
                        activity.get("diff_summary"),
                        activity.get("pillar"),
                        activity.get("content_score"),
                        json.dumps(activity.get("raw_data")) if activity.get("raw_data") is not None else None,
                    ),
                )
                ids.append(cursor.lastrowid)
        return ids

    def get_activities_since(self, since_iso: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM activity_log WHERE scanned_at >= ?", (since_iso,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_last_scan_date(self) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT MAX(scanned_at) AS last_scan FROM activity_log"
            ).fetchone()
            if row is None:
                return None
            return row["last_scan"]
