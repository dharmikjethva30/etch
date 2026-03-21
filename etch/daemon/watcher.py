"""File watcher using watchdog."""

import fnmatch
import re
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional, Set

from watchdog.observers import Observer
from watchdog.events import (
    FileModifiedEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileMovedEvent,
    FileSystemEventHandler,
)

from etch.memory.store import Store


class FileWatcher:
    """Watches project files for changes using watchdog."""

    def __init__(
        self,
        project_root: Path,
        store: Store,
        project_id: str,
        ignore_patterns: List[str],
        watched_extensions: Optional[Set[str]] = None,
    ):
        """Initialize file watcher.

        Args:
            project_root: Root directory to watch
            store: Store instance for recording events
            project_id: Project identifier
            ignore_patterns: List of glob patterns to ignore
            watched_extensions: Set of extensions to watch (e.g., {'.py', '.js'})
        """
        self.project_root = Path(project_root)
        self.store = store
        self.project_id = project_id
        self.ignore_patterns = ignore_patterns
        self.watched_extensions = watched_extensions or {
            ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".rb",
            ".cpp", ".c", ".h", ".cs", ".json", ".yaml", ".yml", ".toml",
            ".env", ".sql", ".md"
        }
        self.observer: Optional[Observer] = None
        self._debounce_cache: dict[str, float] = {}
        self._debounce_delay = 2.0  # seconds

    def _should_ignore(self, path: str) -> bool:
        """Check if path matches ignore patterns."""
        rel_path = Path(path).relative_to(self.project_root) if self.project_root in Path(path).parents or Path(path) == self.project_root else Path(path)
        path_str = str(rel_path).replace("\\", "/")

        for pattern in self.ignore_patterns:
            if fnmatch.fnmatch(path_str, pattern):
                return True
            if fnmatch.fnmatch(path_str, f"*/{pattern}"):
                return True
            if fnmatch.fnmatch(path_str, f"*/{pattern}/*"):
                return True

        return False

    def _should_track(self, path: str) -> bool:
        """Check if file should be tracked (extension and not ignored)."""
        p = Path(path)
        if p.suffix not in self.watched_extensions:
            return False
        return not self._should_ignore(path)

    def _get_relative_path(self, path: str) -> str:
        """Get path relative to project root."""
        p = Path(path)
        try:
            return str(p.relative_to(self.project_root))
        except ValueError:
            return str(p)

    def _debounce(self, path: str) -> bool:
        """Check debounce: return True if should process event, False if already recent."""
        now = time.time()
        last_seen = self._debounce_cache.get(path)

        if last_seen and (now - last_seen) < self._debounce_delay:
            return False

        self._debounce_cache[path] = now
        return True

    def _record_event(self, path: str, event_type: str) -> None:
        """Record file event in database."""
        if not self._should_track(path):
            return

        if not self._debounce(path):
            return

        rel_path = self._get_relative_path(path)
        ts = int(time.time())

        self.store.add_file_event(
            ts=ts,
            file_path=rel_path,
            event_type=event_type,
            project_id=self.project_id,
            session_id=None,  # Will be set by session tracker
        )

    def on_modified(self, event: FileModifiedEvent) -> None:
        """Handle file modification."""
        if not event.is_directory:
            self._record_event(event.src_path, "save")

    def on_created(self, event: FileCreatedEvent) -> None:
        """Handle file creation."""
        if not event.is_directory:
            self._record_event(event.src_path, "create")

    def on_deleted(self, event: FileDeletedEvent) -> None:
        """Handle file deletion."""
        if not event.is_directory:
            self._record_event(event.src_path, "delete")

    def on_renamed(self, event: FileMovedEvent) -> None:
        """Handle file rename."""
        if not event.is_directory:
            self._record_event(event.src_path, "rename")
            self._record_event(event.dest_path, "create")

    def start(self) -> None:
        """Start watching directory."""
        handler = FileWatcherHandler(self)
        self.observer = Observer()
        self.observer.schedule(handler, str(self.project_root), recursive=True)
        self.observer.start()

    def stop(self) -> None:
        """Stop watching directory."""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None


class FileWatcherHandler(FileSystemEventHandler):
    """Event handler for watchdog observer."""

    def __init__(self, watcher: FileWatcher):
        """Initialize handler with reference to watcher."""
        self.watcher = watcher

    def on_modified(self, event: FileModifiedEvent) -> None:
        """Handle file modification."""
        self.watcher.on_modified(event)

    def on_created(self, event: FileCreatedEvent) -> None:
        """Handle file creation."""
        self.watcher.on_created(event)

    def on_deleted(self, event: FileDeletedEvent) -> None:
        """Handle file deletion."""
        self.watcher.on_deleted(event)

    def on_renamed(self, event: FileMovedEvent) -> None:
        """Handle file rename."""
        self.watcher.on_renamed(event)
