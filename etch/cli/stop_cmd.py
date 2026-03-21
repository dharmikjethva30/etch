"""Implementation of 'etch stop' command."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
import typer
from rich.console import Console

from etch.config.settings import Settings


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


def _stop_macos_launchd(etch_dir: Path) -> None:
    """Stop daemon using launchd on macOS."""
    settings = Settings(etch_dir)
    settings.load()

    project_id = settings.get("project_id")
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"ai.etch.{project_id}.plist"

    if plist_path.exists():
        try:
            subprocess.run(
                ["launchctl", "unload", str(plist_path)],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError:
            pass


def cmd_stop() -> None:
    """Stop Etch daemon."""
    try:
        etch_dir = _find_etch_dir()
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    settings = Settings(etch_dir)
    settings.load()

    project_name = settings.get("project_name")

    console.print()
    console.print(f"[bold]Stopping Etch daemon for {project_name}...[/bold]")

    pid_file = etch_dir / "daemon.pid"

    # Get PID if available
    pid = None
    if pid_file.exists():
        try:
            with open(pid_file) as f:
                pid = int(f.read().strip())
        except (ValueError, IOError):
            pass

    # Try platform-specific stop
    import platform
    system = platform.system()

    if system == "Darwin":  # macOS
        _stop_macos_launchd(etch_dir)

    # Try to kill the process directly
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            # Wait for graceful shutdown
            for _ in range(10):
                try:
                    os.kill(pid, 0)  # Check if still alive
                    time.sleep(0.5)
                except OSError:
                    break
            else:
                # If still alive, force kill
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass

            console.print(f"[green]✓[/green] Daemon stopped (PID {pid})")
        except ProcessNotFoundError:
            console.print("[yellow]⚠ Daemon process not found[/yellow]")
    elif pid_file.exists():
        console.print("[yellow]⚠ Could not read PID from file[/yellow]")
    else:
        console.print("[yellow]⚠ No daemon running[/yellow]")

    # Clean up PID file
    if pid_file.exists():
        try:
            pid_file.unlink()
        except OSError:
            pass

    console.print()
