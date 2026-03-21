"""Daemon runner - orchestrates all background threads."""

import atexit
import logging
import os
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from etch.config.settings import Settings
from etch.memory.store import Store
from etch.daemon.watcher import FileWatcher
from etch.daemon.git_poller import GitPoller
from etch.daemon.session_tracker import SessionTracker


class DaemonRunner:
    """Runs Etch daemon with all background threads."""

    def __init__(self, etch_dir: Path):
        """Initialize daemon runner.

        Args:
            etch_dir: Path to .etch directory
        """
        self.etch_dir = Path(etch_dir)
        self.settings = Settings(self.etch_dir)
        self.settings.load()

        self.project_root = Path(self.settings.get("project_root"))
        self.project_id = self.settings.get("project_id")

        # Use local paths for PID/log/DB — avoids issues on mounted filesystems
        from platformdirs import user_data_dir
        local_dir = Path(user_data_dir("etch", "etch")) / self.project_id
        local_dir.mkdir(parents=True, exist_ok=True)

        self.pid_file = local_dir / "daemon.pid"
        self.log_file = local_dir / "daemon.log"

        # DB path: prefer config value, fall back to local_dir
        db_path_str = self.settings.get("daemon.db_path")
        db_path = Path(db_path_str) if db_path_str else local_dir / "memory.db"

        # Setup logging
        self.logger = self._setup_logging()

        # Initialize store
        self.store = Store(db_path)

        # Components
        self.watcher: Optional[FileWatcher] = None
        self.git_poller: Optional[GitPoller] = None
        self.session_tracker: Optional[SessionTracker] = None

        # Threads
        self._watcher_thread: Optional[threading.Thread] = None
        self._git_poller_thread: Optional[threading.Thread] = None
        self._session_tracker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Ignore SIGHUP (sent when parent terminal closes — not relevant for daemon)
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
        # Register signal handlers for clean shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _setup_logging(self) -> logging.Logger:
        """Set up logging to file."""
        logger = logging.getLogger("etch.daemon")
        logger.setLevel(logging.INFO)

        # File handler
        handler = logging.FileHandler(str(self.log_file))
        handler.setLevel(logging.INFO)

        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        return logger

    def _signal_handler(self, signum, frame):
        """Handle SIGTERM and SIGINT — just set the stop event; run() will clean up."""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self._stop_event.set()

    def _write_pid(self) -> None:
        """Write process ID to file."""
        with open(self.pid_file, "w") as f:
            f.write(str(os.getpid()))
        self.logger.info(f"Wrote PID {os.getpid()} to {self.pid_file}")

    def _cleanup_pid(self) -> None:
        """Remove PID file."""
        if self.pid_file.exists():
            self.pid_file.unlink()

    def start(self) -> None:
        """Start daemon with all components."""
        self.logger.info("Starting Engram daemon...")
        self._write_pid()

        # Initialize components
        ignore_patterns = self.settings.get("watcher.ignore_patterns", [])
        self.watcher = FileWatcher(
            project_root=self.project_root,
            store=self.store,
            project_id=self.project_id,
            ignore_patterns=ignore_patterns,
        )

        self.git_poller = GitPoller(
            repo_path=self.project_root,
            store=self.store,
            project_id=self.project_id,
        )

        session_gap = self.settings.get("watcher.session_gap_minutes", 30)
        self.session_tracker = SessionTracker(
            store=self.store,
            project_id=self.project_id,
            session_gap_minutes=session_gap,
        )

        # Start components
        self.watcher.start()
        self.logger.info("File watcher started")

        # Git poller thread
        poll_interval = self.settings.get("git.poll_interval_seconds", 60)
        self._git_poller_thread = threading.Thread(
            target=self.git_poller.run,
            args=(poll_interval,),
            daemon=True,
        )
        self._git_poller_thread.start()
        self.logger.info("Git poller started")

        # Session tracker thread
        self._session_tracker_thread = threading.Thread(
            target=self.session_tracker.run,
            daemon=True,
        )
        self._session_tracker_thread.start()
        self.logger.info("Session tracker started")

        self.logger.info("Daemon started successfully")

    def run(self) -> None:
        """Run daemon indefinitely."""
        self.start()
        try:
            # Keep the main thread alive
            while not self._stop_event.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self) -> None:
        """Stop daemon and cleanup."""
        self.logger.info("Stopping daemon...")

        # Stop components
        if self.session_tracker:
            self.session_tracker.stop()

        if self.git_poller:
            self.git_poller.stop()

        if self.watcher:
            self.watcher.stop()

        # Wait for threads
        if self._session_tracker_thread:
            self._session_tracker_thread.join(timeout=5)
        if self._git_poller_thread:
            self._git_poller_thread.join(timeout=5)

        # Close store
        self.store.close()

        # Cleanup PID
        self._cleanup_pid()

        self.logger.info("Daemon stopped")
        self._stop_event.set()

    @staticmethod
    def run_daemon(engram_dir: Path) -> None:
        """Static method to run daemon (used by start command)."""
        runner = DaemonRunner(engram_dir)
        runner.run()


if __name__ == "__main__":
    import sys as _sys
    if len(_sys.argv) < 2:
        print("Usage: python -m engram.daemon.runner <engram_dir>")
        _sys.exit(1)
    _engram_dir = Path(_sys.argv[1])
    if not _engram_dir.exists():
        print(f"Error: {_engram_dir} does not exist")
        _sys.exit(1)
    DaemonRunner.run_daemon(_engram_dir)
