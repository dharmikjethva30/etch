"""SQLite memory store for Engram."""

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import threading


class Store:
    """Thread-safe SQLite store for Engram memory."""

    def __init__(self, db_path: Path):
        """Initialize store and set up schema.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self._local = threading.local()
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                timeout=30,
            )
            self._local.conn.row_factory = sqlite3.Row
            # Try WAL mode, fall back silently if filesystem doesn't support it
            try:
                self._local.conn.execute("PRAGMA journal_mode=WAL")
            except Exception:
                pass
        return self._local.conn

    def _init_schema(self) -> None:
        """Initialize database schema from schema.sql."""
        schema_path = Path(__file__).parent / "schema.sql"
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        with open(schema_path) as f:
            schema_sql = f.read()

        conn = self._get_conn()
        for statement in schema_sql.split(";"):
            statement = statement.strip()
            if statement:
                conn.execute(statement)
        conn.commit()

    def close(self) -> None:
        """Close database connection."""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    # File Events
    def add_file_event(
        self,
        ts: int,
        file_path: str,
        event_type: str,
        project_id: str,
        session_id: Optional[str] = None,
    ) -> int:
        """Add a file event to the database.

        Args:
            ts: Timestamp (seconds since epoch)
            file_path: Relative path to file from project root
            event_type: Type of event (save, create, delete, rename)
            project_id: Project identifier
            session_id: Optional session ID

        Returns:
            Row ID of inserted event
        """
        conn = self._get_conn()
        cursor = conn.execute(
            """
            INSERT INTO file_events (ts, file_path, event_type, session_id, project_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ts, file_path, event_type, session_id, project_id),
        )
        conn.commit()
        return cursor.lastrowid

    def get_file_events(
        self,
        project_id: str,
        limit: int = 100,
        since_ts: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get recent file events for a project.

        Args:
            project_id: Project identifier
            limit: Maximum events to return
            since_ts: Only return events after this timestamp

        Returns:
            List of file event records
        """
        conn = self._get_conn()
        query = "SELECT * FROM file_events WHERE project_id = ?"
        params: List[Any] = [project_id]

        if since_ts is not None:
            query += " AND ts >= ?"
            params.append(since_ts)

        query += " ORDER BY ts DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    # Git Commits
    def add_git_commit(
        self,
        commit_hash: str,
        ts: int,
        message: str,
        author: str,
        diff_summary: str,
        files_changed: List[str],
        project_id: str,
    ) -> None:
        """Add a git commit to the database.

        Args:
            commit_hash: Git commit hash
            ts: Commit timestamp
            message: Commit message
            author: Commit author
            diff_summary: Compact diff summary
            files_changed: List of files changed
            project_id: Project identifier
        """
        conn = self._get_conn()
        files_json = json.dumps(files_changed)

        conn.execute(
            """
            INSERT OR IGNORE INTO git_commits
            (commit_hash, ts, message, author, diff_summary, files_changed, project_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (commit_hash, ts, message, author, diff_summary, files_json, project_id),
        )
        conn.commit()

    def get_latest_commit_hash(self, project_id: str) -> Optional[str]:
        """Get the most recent commit hash in the database.

        Args:
            project_id: Project identifier

        Returns:
            Commit hash or None if no commits
        """
        conn = self._get_conn()
        row = conn.execute(
            "SELECT commit_hash FROM git_commits WHERE project_id = ? ORDER BY ts DESC LIMIT 1",
            (project_id,),
        ).fetchone()
        return row[0] if row else None

    def get_git_commits(
        self,
        project_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get recent git commits for a project.

        Args:
            project_id: Project identifier
            limit: Maximum commits to return

        Returns:
            List of commit records
        """
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT id, commit_hash, ts, message, author, diff_summary, files_changed
            FROM git_commits
            WHERE project_id = ?
            ORDER BY ts DESC
            LIMIT ?
            """,
            (project_id, limit),
        ).fetchall()

        results = []
        for row in rows:
            record = dict(row)
            if record["files_changed"]:
                record["files_changed"] = json.loads(record["files_changed"])
            results.append(record)
        return results

    # Co-edit Pairs
    def increment_co_edit_pair(
        self,
        file_a: str,
        file_b: str,
        project_id: str,
    ) -> None:
        """Increment co-edit count for a pair of files.

        Args:
            file_a: First file path
            file_b: Second file path
            project_id: Project identifier
        """
        conn = self._get_conn()
        ts_now = int(time.time())

        # Ensure consistent ordering
        if file_a > file_b:
            file_a, file_b = file_b, file_a

        conn.execute(
            """
            INSERT INTO co_edit_pairs (file_a, file_b, co_edit_count, last_seen, project_id)
            VALUES (?, ?, 1, ?, ?)
            ON CONFLICT(file_a, file_b, project_id) DO UPDATE SET
                co_edit_count = co_edit_count + 1,
                last_seen = ?
            """,
            (file_a, file_b, ts_now, project_id, ts_now),
        )
        conn.commit()

    def get_co_edit_pairs(
        self,
        project_id: str,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Get co-edit pairs ranked by count.

        Args:
            project_id: Project identifier
            limit: Maximum pairs to return

        Returns:
            List of co-edit pair records
        """
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT file_a, file_b, co_edit_count, last_seen
            FROM co_edit_pairs
            WHERE project_id = ?
            ORDER BY co_edit_count DESC
            LIMIT ?
            """,
            (project_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_related_files(self, file_path: str, project_id: str, limit: int = 10) -> List[str]:
        """Get files frequently co-edited with a given file.

        Args:
            file_path: File to find related files for
            project_id: Project identifier
            limit: Maximum files to return

        Returns:
            List of related file paths
        """
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT file_b as related FROM co_edit_pairs
            WHERE file_a = ? AND project_id = ?
            UNION ALL
            SELECT file_a as related FROM co_edit_pairs
            WHERE file_b = ? AND project_id = ?
            ORDER BY co_edit_count DESC
            LIMIT ?
            """,
            (file_path, project_id, file_path, project_id, limit),
        ).fetchall()
        return [row[0] for row in rows]

    # File Scores
    def update_file_score(
        self,
        file_path: str,
        project_id: str,
        recency_score: float = 0.0,
        frequency_score: float = 0.0,
        centrality_score: float = 0.0,
    ) -> None:
        """Update scores for a file.

        Args:
            file_path: File path
            project_id: Project identifier
            recency_score: Recency score (0-1)
            frequency_score: Frequency score (0-1)
            centrality_score: Centrality score (0-1)
        """
        conn = self._get_conn()
        ts_now = int(time.time())

        conn.execute(
            """
            INSERT INTO file_scores
            (file_path, project_id, recency_score, frequency_score, centrality_score, last_updated)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_path, project_id) DO UPDATE SET
                recency_score = ?,
                frequency_score = ?,
                centrality_score = ?,
                last_updated = ?
            """,
            (
                file_path, project_id, recency_score, frequency_score, centrality_score, ts_now,
                recency_score, frequency_score, centrality_score, ts_now,
            ),
        )
        conn.commit()

    def get_file_scores(self, project_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get top files by recency score.

        Args:
            project_id: Project identifier
            limit: Maximum files to return

        Returns:
            List of file score records
        """
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT file_path, recency_score, frequency_score, centrality_score, last_updated
            FROM file_scores
            WHERE project_id = ?
            ORDER BY recency_score DESC
            LIMIT ?
            """,
            (project_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    # Sessions
    def add_session(
        self,
        session_id: str,
        started_at: int,
        ended_at: int,
        files_touched: List[str],
        project_id: str,
        inferred_task: Optional[str] = None,
        change_type: Optional[str] = None,
    ) -> None:
        """Record a work session.

        Args:
            session_id: Unique session identifier
            started_at: Session start timestamp
            ended_at: Session end timestamp
            files_touched: List of file paths edited
            project_id: Project identifier
            inferred_task: Inferred task description
            change_type: Detected change type
        """
        conn = self._get_conn()
        files_json = json.dumps(files_touched)

        conn.execute(
            """
            INSERT OR REPLACE INTO sessions
            (session_id, started_at, ended_at, files_touched, inferred_task, change_type, project_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, started_at, ended_at, files_json, inferred_task, change_type, project_id),
        )
        conn.commit()

    def get_active_session(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Get the most recent session (may still be active).

        Args:
            project_id: Project identifier

        Returns:
            Session record or None
        """
        conn = self._get_conn()
        row = conn.execute(
            """
            SELECT session_id, started_at, ended_at, files_touched, inferred_task, change_type
            FROM sessions
            WHERE project_id = ?
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()

        if not row:
            return None

        record = dict(row)
        if record["files_touched"]:
            record["files_touched"] = json.loads(record["files_touched"])
        return record

    def get_sessions(self, project_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent sessions.

        Args:
            project_id: Project identifier
            limit: Maximum sessions to return

        Returns:
            List of session records
        """
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT session_id, started_at, ended_at, files_touched, inferred_task, change_type
            FROM sessions
            WHERE project_id = ?
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (project_id, limit),
        ).fetchall()

        results = []
        for row in rows:
            record = dict(row)
            if record["files_touched"]:
                record["files_touched"] = json.loads(record["files_touched"])
            results.append(record)
        return results

    # Projects
    def add_project(
        self,
        project_id: str,
        root_path: str,
        name: str,
    ) -> None:
        """Register a project.

        Args:
            project_id: Unique project identifier
            root_path: Absolute path to project root
            name: Human-readable project name
        """
        conn = self._get_conn()
        ts_now = int(time.time())

        conn.execute(
            """
            INSERT OR REPLACE INTO projects
            (project_id, root_path, name, created_at, last_active)
            VALUES (?, ?, ?, ?, ?)
            """,
            (project_id, root_path, name, ts_now, ts_now),
        )
        conn.commit()

    def get_project_stats(self, project_id: str) -> Dict[str, Any]:
        """Get aggregated statistics for a project.

        Args:
            project_id: Project identifier

        Returns:
            Dict with stats
        """
        conn = self._get_conn()

        # File event count
        file_events_count = conn.execute(
            "SELECT COUNT(*) FROM file_events WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0]

        # Unique files
        unique_files = conn.execute(
            "SELECT COUNT(DISTINCT file_path) FROM file_events WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0]

        # Commit count
        commits_count = conn.execute(
            "SELECT COUNT(*) FROM git_commits WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0]

        # Co-edit pairs
        coedits_count = conn.execute(
            "SELECT COUNT(*) FROM co_edit_pairs WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0]

        # Session count
        sessions_count = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0]

        return {
            "file_events_count": file_events_count,
            "unique_files": unique_files,
            "commits_count": commits_count,
            "coedits_count": coedits_count,
            "sessions_count": sessions_count,
        }
