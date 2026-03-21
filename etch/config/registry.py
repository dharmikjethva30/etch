"""Global project registry management.

Maintains a global registry of all Etch projects at ~/.config/etch/projects.json
to enable multi-project support with daemon status tracking.
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional
from platformdirs import user_config_dir


def get_registry_path() -> Path:
    """Get the global registry path: ~/.config/etch/projects.json"""
    config_dir = Path(user_config_dir("etch", "etch"))
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "projects.json"


def load_registry() -> Dict:
    """Load global registry from disk.

    Returns:
        dict with 'projects' key containing project entries, or empty dict if not found.
    """
    registry_path = get_registry_path()
    if not registry_path.exists():
        return {"projects": {}}

    try:
        with open(registry_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"projects": {}}


def save_registry(data: Dict) -> None:
    """Save global registry to disk.

    Args:
        data: Registry dict with 'projects' key
    """
    registry_path = get_registry_path()
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    with open(registry_path, "w") as f:
        json.dump(data, f, indent=2)


def register_project(project_id: str, name: str, root: str, mcp_port: int) -> None:
    """Add or update a project in the global registry.

    Args:
        project_id: Unique project identifier (UUID)
        name: Human-readable project name
        root: Absolute path to project root
        mcp_port: MCP server port assigned to this project
    """
    registry = load_registry()

    registry["projects"][project_id] = {
        "project_id": project_id,
        "name": name,
        "root": str(root),
        "mcp_port": mcp_port,
        "added_at": int(time.time()),
    }

    save_registry(registry)


def unregister_project(project_id: str) -> None:
    """Remove a project from the global registry.

    Args:
        project_id: Unique project identifier
    """
    registry = load_registry()
    if project_id in registry.get("projects", {}):
        del registry["projects"][project_id]
        save_registry(registry)


def get_all_projects() -> List[Dict]:
    """Return list of all registered projects.

    Returns:
        List of project dicts, sorted by added_at (newest first)
    """
    registry = load_registry()
    projects = list(registry.get("projects", {}).values())
    # Sort by added_at descending (newest first)
    projects.sort(key=lambda p: p.get("added_at", 0), reverse=True)
    return projects


def get_project(project_id: str) -> Optional[Dict]:
    """Get a single project by ID.

    Args:
        project_id: Unique project identifier

    Returns:
        Project dict, or None if not found
    """
    registry = load_registry()
    return registry.get("projects", {}).get(project_id)
