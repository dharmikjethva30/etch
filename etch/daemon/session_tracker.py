"""Session tracking and grouping."""

import threading
import time
import uuid
from typing import Dict, List, Optional, Set

from etch.memory.store import Store


class SessionTracker:
    """Groups file events into work sessions."""

    def __init__(
        self,
        store: Store,
        project_id: str,
        session_gap_minutes: int = 30,
    ):
        """Initialize session tracker.

        Args:
            store: Store instance
            project_id: Project identifier
            session_gap_minutes: Gap in minutes to consider new session
        """
        self.store = store
        self.project_id = project_id
        self.session_gap_seconds = session_gap_minutes * 60
        self._current_session: Optional[str] = None
        self._session_start: Optional[int] = None
        self._session_files: Set[str] = set()
        self._last_event_time: Optional[int] = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

    def process_event(self, ts: int, file_path: str) -> Optional[str]:
        """Process a file event, tracking it in current session.

        Args:
            ts: Event timestamp
            file_path: File path

        Returns:
            Session ID (may be new)
        """
        with self._lock:
            now = time.time()
            ts_int = int(ts)

            # Check if we need to close current session
            if self._last_event_time and (ts_int - self._last_event_time) > self.session_gap_seconds:
                self._close_session()

            # Create new session if needed
            if self._current_session is None:
                self._current_session = str(uuid.uuid4())
                self._session_start = ts_int
                self._session_files = set()

            # Add file to session
            self._session_files.add(file_path)
            self._last_event_time = ts_int

            return self._current_session

    def _close_session(self) -> None:
        """Close current session and save to store."""
        if self._current_session and self._session_start:
            files_list = list(self._session_files)
            end_time = int(self._last_event_time) if self._last_event_time else int(time.time())

            self.store.add_session(
                session_id=self._current_session,
                started_at=self._session_start,
                ended_at=end_time,
                files_touched=files_list,
                project_id=self.project_id,
            )

            # Increment co-edit pairs for files in this session
            files_list_sorted = sorted(files_list)
            for i, file_a in enumerate(files_list_sorted):
                for file_b in files_list_sorted[i + 1 :]:
                    self.store.increment_co_edit_pair(file_a, file_b, self.project_id)

        # Reset
        self._current_session = None
        self._session_start = None
        self._session_files = set()

    def get_active_session(self) -> Optional[Dict]:
        """Get current active session info."""
        with self._lock:
            if self._current_session:
                now = int(time.time())
                duration_mins = (now - self._session_start) // 60 if self._session_start else 0
                return {
                    "session_id": self._current_session,
                    "started_at": self._session_start,
                    "duration_mins": duration_mins,
                    "files": list(self._session_files),
                }
        return None

    def run(self, check_interval: int = 10) -> None:
        """Run session tracker loop.

        Periodically checks if session should be closed due to inactivity.

        Args:
            check_interval: How often to check for stale sessions (seconds)
        """
        while not self._stop_event.is_set():
            with self._lock:
                if self._last_event_time:
                    now = int(time.time())
                    if (now - self._last_event_time) > self.session_gap_seconds:
                        self._close_session()

            self._stop_event.wait(check_interval)

    def flush(self) -> None:
        """Close any active session (called on shutdown)."""
        with self._lock:
            self._close_session()

    def stop(self) -> None:
        """Stop tracker."""
        self.flush()
        self._stop_event.set()
