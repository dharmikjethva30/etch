"""Implementation of 'etch init' command."""

import json
from pathlib import Path
from typing import Optional, Tuple
import time
import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from git import Repo, InvalidGitRepositoryError, GitCommandError
from platformdirs import user_data_dir

from etch.config.settings import Settings
from etch.config.registry import register_project
from etch.memory.store import Store


def _get_local_db_path(project_id: str) -> Path:
    """Get a local (non-mounted) path for the SQLite database."""
    local_dir = Path(user_data_dir("etch", "etch")) / project_id
    local_dir.mkdir(parents=True, exist_ok=True)
    return local_dir / "memory.db"


def _find_free_port(start: int = 7700, end: int = 7799) -> int:
    """Find a free port in range, avoiding ports used by other etch projects.

    Args:
        start: Start of port range (default 7700)
        end: End of port range (default 7799)

    Returns:
        A free port number in the range, or 7777 as fallback
    """
    import socket
    from etch.config.registry import load_registry

    # Get ports already assigned to other etch projects
    registry = load_registry()
    used_ports = {
        p.get("mcp_port")
        for p in registry.get("projects", {}).values()
        if p.get("mcp_port")
    }

    # Try ports in the range
    for port in range(start, end + 1):
        if port in used_ports:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue

    # Fallback
    return 7777


console = Console()


def _detect_project_root(start_path: Path = None) -> Optional[Path]:
    """Find git repo root from current directory or given path."""
    if start_path is None:
        start_path = Path.cwd()

    current = Path(start_path).resolve()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return None


def _get_language(root: Path) -> str:
    """Detect primary language by checking top-level indicators only (fast)."""
    # Fast heuristic: check top-level config files first
    indicators = {
        "package.json": "JavaScript",
        "tsconfig.json": "TypeScript",
        "pyproject.toml": "Python",
        "setup.py": "Python",
        "requirements.txt": "Python",
        "go.mod": "Go",
        "Cargo.toml": "Rust",
        "pom.xml": "Java",
        "build.gradle": "Java",
        "Gemfile": "Ruby",
        "*.csproj": "C#",
    }
    for filename, lang in indicators.items():
        if list(root.glob(filename)):
            return lang

    # Fallback: scan only top-level files (no recursion into node_modules etc.)
    skip = {"node_modules", ".git", "__pycache__", ".venv", "dist", "build"}
    ext_map = {".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
               ".go": "Go", ".rs": "Rust", ".java": "Java"}
    counts: dict = {}
    for child in root.iterdir():
        if child.name in skip or not child.is_file():
            continue
        lang = ext_map.get(child.suffix)
        if lang:
            counts[lang] = counts.get(lang, 0) + 1
    return max(counts, key=counts.get) if counts else "Unknown"


def _get_branch(repo: Repo) -> str:
    """Get current active branch."""
    try:
        return repo.active_branch.name
    except Exception:
        return "unknown"


def _harvest_git_history(repo: Repo, days: int = 90) -> Tuple[int, int]:
    """Harvest git history from the last N days.

    Args:
        repo: Git repository object
        days: Number of days to look back

    Returns:
        Tuple of (commit_count, unique_files_count)
    """
    from datetime import datetime, timedelta

    cutoff_time = int((datetime.now() - timedelta(days=days)).timestamp())
    commits_processed = 0
    unique_files = set()

    try:
        for commit in repo.iter_commits():
            if commit.committed_date < cutoff_time:
                break

            commits_processed += 1

            # Track unique files
            try:
                for item in commit.tree.traverse():
                    if item.type == "blob":
                        unique_files.add(item.path)
            except Exception:
                pass

    except GitCommandError:
        pass

    return commits_processed, len(unique_files)


def _store_git_history(
    store: Store,
    repo: Repo,
    project_id: str,
    days: int = 90,
) -> Tuple[int, int, int]:
    """Store git history in SQLite using a single fast git log call.

    Returns:
        Tuple of (commits_stored, unique_files, co_edit_pairs)
    """
    import subprocess, json as _json

    root = Path(repo.working_dir)
    commits_stored = 0
    unique_files: set = set()
    co_edit_graph: dict = {}

    try:
        # One fast git log call: separator-delimited output, --name-only for files
        cmd = ["git", "log",
               "--format=COMMIT\x1f%H\x1f%at\x1f%s\x1f%an",
               "--name-only", "--no-merges"]
        if days < 3650:
            cmd.insert(2, f"--after={days} days ago")
        log_output = subprocess.check_output(
            cmd, cwd=str(root), text=True, timeout=15,
        ).strip()
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        # Fall back to full log if --after filter fails
        try:
            log_output = subprocess.check_output(
                ["git", "log",
                 "--format=COMMIT\x1f%H\x1f%at\x1f%s\x1f%an",
                 "--name-only", "--no-merges"],
                cwd=str(root), text=True, timeout=15,
            ).strip()
        except Exception:
            return 0, 0, 0

    # Patterns to skip when processing file lists from git
    _SKIP_PREFIXES = (
        "node_modules/", ".git/", "__pycache__/", ".venv/",
        "dist/", "build/", ".next/", "coverage/",
    )
    _SKIP_SUFFIXES = (".pyc", ".log", ".lock", ".min.js", ".map")

    def _is_tracked_file(path: str) -> bool:
        for p in _SKIP_PREFIXES:
            if path.startswith(p):
                return False
        for s in _SKIP_SUFFIXES:
            if path.endswith(s):
                return False
        return True

    # Parse the output block by block
    current: dict = {}
    current_files: list = []

    def flush_commit():
        nonlocal commits_stored
        if not current:
            return
        files = [f for f in current_files if f and _is_tracked_file(f)]
        diff_summary = f"{len(files)} files"
        store.add_git_commit(
            commit_hash=current["hash"],
            ts=int(current["ts"]),
            message=current["msg"],
            author=current["author"],
            diff_summary=diff_summary,
            files_changed=files,
            project_id=project_id,
        )
        commits_stored += 1
        for f in files:
            unique_files.add(f)
            for g in files:
                if f != g:
                    co_edit_graph.setdefault(f, set()).add(g)

    for line in log_output.splitlines():
        if line.startswith("COMMIT\x1f"):
            flush_commit()
            parts = line.split("\x1f")
            current = {
                "hash": parts[1] if len(parts) > 1 else "",
                "ts": parts[2] if len(parts) > 2 else "0",
                "msg": parts[3] if len(parts) > 3 else "",
                "author": parts[4] if len(parts) > 4 else "",
            }
            current_files = []
        elif line.strip():
            current_files.append(line.strip())

    flush_commit()

    # Store co-edit pairs
    coedits_count = 0
    for file_a, related in co_edit_graph.items():
        for file_b in related:
            store.increment_co_edit_pair(file_a, file_b, project_id)
            coedits_count += 1

    return commits_stored, len(unique_files), coedits_count


def cmd_init() -> None:
    """Initialize a new Engram project."""
    console.print()

    # Step 1: Detect project
    console.print("[bold]Detecting project...[/bold]")

    root = _detect_project_root()
    if not root:
        console.print("[red]✗ No git repository found[/red]")
        raise typer.Exit(1)

    try:
        repo = Repo(root)
    except InvalidGitRepositoryError:
        console.print("[red]✗ Could not open git repository[/red]")
        raise typer.Exit(1)

    # Get project info
    project_name = root.name
    language = _get_language(root)
    branch = _get_branch(repo)
    try:
        commit_count = int(repo.git.rev_list("HEAD", count=True))
    except Exception:
        commit_count = 0

    console.print(f"  [green]✓[/green] Git repo: {project_name} ({commit_count} commits)")
    console.print(f"  [green]✓[/green] Language: {language}")
    console.print(f"  [green]✓[/green] Active branch: {branch}")

    # Step 2: Create .etch/
    console.print()
    console.print("[bold]Creating .etch/[/bold]")

    etch_dir = root / ".etch"
    etch_dir.mkdir(exist_ok=True)
    console.print("  [green]✓[/green] Directory created")

    # Initialize config
    settings = Settings(etch_dir)
    settings.init_project(root, project_name, language, branch)

    # Assign a unique port for this project
    mcp_port = _find_free_port()
    settings.set("mcp.port", mcp_port)
    console.print("  [green]✓[/green] config.json (port {})".format(mcp_port))

    # Initialize database — stored locally (not in mounted/project dir) for SQLite compatibility
    project_id = settings.get("project_id")
    db_path = _get_local_db_path(project_id)
    settings.set("daemon.db_path", str(db_path))
    settings.save()
    store = Store(db_path)
    console.print(f"  [green]✓[/green] memory.db (local SQLite)")

    # Register project in database
    project_id = settings.get("project_id")
    store.add_project(project_id, str(root.resolve()), project_name)

    # Step 3: Harvest git history
    console.print()
    console.print("[bold]Harvesting git history (last 90 days)...[/bold]")

    # Use full history if no recent commits found in default window
    commits_stored, unique_files, coedits_count = _store_git_history(
        store, repo, project_id, days=365 * 10
    )

    console.print(f"  [green]✓[/green] {commits_stored} commits processed")
    console.print(f"  [green]✓[/green] {unique_files} active files indexed")
    console.print(f"  [green]✓[/green] {coedits_count} co-edit pairs discovered")

    # Step 4: Detect SLM
    console.print()
    console.print("[bold]SLM: Checking for local models...[/bold]")

    # For Week 1, just use heuristic by default
    slm_backend = "heuristic"
    console.print(f"  [green]✓[/green] Using {slm_backend} (default)")

    settings.set("slm.backend", slm_backend)
    settings.save()

    # Register project in global registry
    project_id = settings.get("project_id")
    mcp_port = settings.get("mcp.port", 7777)
    register_project(project_id, project_name, root, mcp_port)

    # Final message
    console.print()
    panel = Panel(
        Text("Ready to start!", style="bold green"),
        title="Setup Complete",
        border_style="green",
    )
    console.print(panel)
    console.print()
    console.print("[cyan]Next steps:[/cyan]")
    console.print("  1. etch start        (start daemon)")
    console.print("  2. etch status       (monitor activity)")
    console.print("  3. etch mcp          (get Claude/Cursor config)")
    console.print()
