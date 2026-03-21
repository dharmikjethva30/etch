"""Implementation of 'etch status' command."""

import os
import time
from pathlib import Path
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from etch.config.settings import Settings
from etch.memory.store import Store


console = Console()


def _find_etch_dir() -> Path:
    """Find .etch directory by walking up from cwd."""
    current = Path.cwd()
    while current != current.parent:
        etch_dir = current / ".etch"
        if etch_dir.exists() and (etch_dir / "config.json").exists():
            return etch_dir
        current = current.parent

    raise FileNotFoundError("No .etch directory found.")


def _format_duration(seconds: int) -> str:
    """Format seconds into human-readable duration."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        mins = seconds // 60
        return f"{mins}m"
    else:
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        return f"{hours}h {mins}m"


def _format_timestamp(ts: int) -> str:
    """Format timestamp as HH:MM."""
    dt = time.localtime(ts)
    return time.strftime("%H:%M", dt)


def cmd_status() -> None:
    """Show daemon status and project statistics.

    Falls back to showing all tracked projects if run outside a project context.
    """
    try:
        etch_dir = _find_etch_dir()
    except FileNotFoundError:
        # Fall back to showing all projects when run outside a project context
        from .projects_cmd import cmd_projects
        cmd_projects()
        return

    settings = Settings(etch_dir)
    settings.load()

    project_name = settings.get("project_name")
    project_id = settings.get("project_id")

    console.print()

    # Header with project name
    header_text = f"● Etch — {project_name}"
    console.print(f"[bold cyan]{header_text}[/bold cyan]")

    # Use local paths for PID and DB (same logic as runner.py)
    from platformdirs import user_data_dir
    local_dir = Path(user_data_dir("etch", "etch")) / project_id

    # Check daemon status
    pid_file = local_dir / "daemon.pid"
    daemon_running = False
    daemon_pid = None
    uptime = None

    if pid_file.exists():
        try:
            with open(pid_file) as f:
                daemon_pid = int(f.read().strip())
            # Check if process is running
            os.kill(daemon_pid, 0)
            daemon_running = True

            # Calculate uptime (get process start time if available)
            try:
                import psutil
                proc = psutil.Process(daemon_pid)
                uptime_secs = int(time.time() - proc.create_time())
                uptime = _format_duration(uptime_secs)
            except Exception:
                uptime = "unknown"

        except (OSError, ValueError):
            pass

    # Print daemon status
    if daemon_running and daemon_pid:
        status_text = f"running (pid {daemon_pid})"
        if uptime:
            status_text += f" — Uptime: {uptime}"
        console.print(f"  Daemon: [green]✓[/green] {status_text}")
    else:
        console.print("  Daemon: [red]✗[/red] not running")
        console.print()
        console.print("  Start with: [cyan]etch start[/cyan]")
        console.print()
        return

    # Load store and get stats
    try:
        db_path_str = settings.get("daemon.db_path")
        db_path = Path(db_path_str) if db_path_str else local_dir / "memory.db"
        store = Store(db_path)

        # Recent events
        console.print()
        console.print("  [bold]Recent activity (last 10 events):[/bold]")

        events = store.get_file_events(project_id, limit=10)
        if events:
            for event in events:
                ts = event["ts"]
                event_type = event["event_type"]
                file_path = event["file_path"]
                time_str = _format_timestamp(ts)

                # Emoji for event type
                icons = {"save": "💾", "create": "✨", "delete": "🗑", "rename": "🔄"}
                icon = icons.get(event_type, "•")

                console.print(f"    {time_str}  {icon}  {event_type}  {file_path}")
        else:
            console.print("    (no activity yet)")

        # Active session
        console.print()
        console.print("  [bold]Active session:[/bold]")

        session = store.get_active_session(project_id)
        if session and session["ended_at"] is None:
            # Calculate duration
            now = int(time.time())
            duration_mins = (now - session["started_at"]) // 60
            files = session.get("files_touched", [])
            files_str = ", ".join(files[:4])
            if len(files) > 4:
                files_str += f", ... ({len(files)} total)"

            console.print(f"    {duration_mins} min — {len(files)} files")
            console.print(f"    {files_str}")
        else:
            console.print("    (no active session)")

        # Memory stats
        console.print()
        console.print("  [bold]Memory stats:[/bold]")

        stats = store.get_project_stats(project_id)
        console.print(f"    Files indexed: {stats['unique_files']}")
        console.print(f"    Co-edit pairs: {stats['coedits_count']}")
        console.print(f"    Sessions recorded: {stats['sessions_count']}")
        console.print(f"    Git commits: {stats['commits_count']}")

        store.close()

    except Exception as e:
        console.print(f"  [red]Error reading stats: {e}[/red]")

    console.print()
