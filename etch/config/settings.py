"""Configuration management for Etch projects."""

import json
import uuid
from pathlib import Path
from typing import Any, Dict, Optional
import time


class Settings:
    """Manages .etch/config.json file."""

    def __init__(self, etch_dir: Path):
        """Initialize settings manager.

        Args:
            etch_dir: Path to .etch directory
        """
        self.etch_dir = Path(etch_dir)
        self.config_path = self.etch_dir / "config.json"
        self._config: Optional[Dict[str, Any]] = None

    def load(self) -> Dict[str, Any]:
        """Load config from disk, or return empty dict if not found."""
        if self.config_path.exists():
            with open(self.config_path) as f:
                self._config = json.load(f)
            return self._config
        self._config = {}
        return self._config

    def save(self) -> None:
        """Write current config to disk."""
        if self._config is None:
            self.load()

        self.etch_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            json.dump(self._config, f, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value by dot-notation key (e.g. 'slm.backend')."""
        if self._config is None:
            self.load()

        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default

    def set(self, key: str, value: Any) -> None:
        """Set a config value by dot-notation key."""
        if self._config is None:
            self.load()

        keys = key.split(".")
        current = self._config
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        current[keys[-1]] = value

    def init_project(
        self,
        project_root: Path,
        project_name: str,
        language: str,
        branch: str,
    ) -> None:
        """Initialize config for a new project."""
        if self._config is None:
            self.load()

        project_id = str(uuid.uuid4())

        self._config = {
            "project_id": project_id,
            "project_root": str(project_root.resolve()),
            "project_name": project_name,
            "language": language,
            "active_branch": branch,
            "created_at": int(time.time()),
            "watcher": {
                "ignore_patterns": [
                    ".git", "node_modules", "__pycache__", ".venv",
                    "*.pyc", "*.log", "*.lock", ".DS_Store",
                    "dist", "build", ".next", "coverage",
                ],
                "session_gap_minutes": 30,
            },
            "git": {
                "poll_interval_seconds": 60,
                "history_days": 90,
            },
            "slm": {
                "backend": "heuristic",
                "model": "unknown",
                "fallback": "heuristic",
            },
            "mcp": {
                "host": "127.0.0.1",
                "port": 7777,
            },
            "daemon": {
                "pid_file": ".etch/daemon.pid",
                "log_file": ".etch/daemon.log",
            },
        }
        self.save()

    def to_dict(self) -> Dict[str, Any]:
        """Return entire config as dict."""
        if self._config is None:
            self.load()
        return self._config.copy()
