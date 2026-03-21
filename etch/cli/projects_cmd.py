"""Implementation of 'etch projects' command."""

import os
from pathlib import Path
import typer
from rich.console import Console
from rich.table import Table
from platformdirs import user_data_dir

from etch.config.registry import get_all_projects

console = Console()


def _is_daemon_running(project_id: str) -> bool:
    """Check if daemon for a project is running via PID file.

    Args:
        project_id: The project ID

    Returns:
        True if daemon process is alive, False otherwise
    """
    local_dir = Path(user_data_dir("etch", "etch")) / project_id
    pid_file = local_dir / "daemon.pid"

    if not pid_file.exists():
        return False

    try:
        with open(pid_file) as f:
            pid = int(f.read().strip())
        # Check if process is running with signal 0 (no-op kill)
        os.kill(pid, 0)
        return True
    except (OSError, ValueError, FileNotFoundError):
        return False


def cmd_projects() -> None:
    """Show all tracked Etch projects and their daemon status."""
    console.print()

    projects = get_all_projects()

    if not projects:
        console.print("[cyan]No projects tracked yet.[/cyan]")
        console.print()
        console.print("  Create your first project with: [bold]cd ~/my-project && etch init[/bold]")
        console.print()
        return

    # Header
    project_word = "project" if len(projects) == 1 else "projects"
    console.print(f"[bold cyan]● Etch — {len(projects)} {project_word} tracked[/bold cyan]")
    console.print()

    # Build table
    table = Table(show_header=True, header_style="bold", show_lines=False)
    table.add_column("Project", style="cyan", width=20)
    table.add_column("Path", style="dim", width=40)
    table.add_column("Port", justify="right", width=8)
    table.add_column("Status", justify="right", width=12)

    for project in projects:
        name = project.get("name", "unknown")
        root = project.get("root", "unknown")
        port = project.get("mcp_port", "?")
        project_id = project.get("project_id")

        # Check daemon status
        running = _is_daemon_running(project_id) if project_id else False
        status_text = "[green]● running[/green]" if running else "[dim]○ stopped[/dim]"

        # Shorten path display
        root_path = Path(root).expanduser()
        try:
            # Try to make path relative to home
            root_display = str(root_path.relative_to(Path.home()))
        except ValueError:
            # If not under home, use full path but truncate if very long
            root_display = str(root_path)
            if len(root_display) > 40:
                root_display = "..." + root_display[-37:]

        table.add_row(name, root_display, str(port), status_text)

    console.print(table)
    console.print()
    console.print("Run [cyan]cd <project>[/cyan] then [cyan]etch status[/cyan] for details.")
    console.print()
