"""Implementation of 'etch start' command."""

import os
import platform
import subprocess
import sys
import time
from pathlib import Path

import typer
from platformdirs import user_data_dir
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
    raise FileNotFoundError("No .etch directory found. Run 'etch init' first.")


def _get_local_dir(project_id: str) -> Path:
    """Return local (non-mounted) dir for PID, log, DB."""
    local_dir = Path(user_data_dir("etch", "etch")) / project_id
    local_dir.mkdir(parents=True, exist_ok=True)
    return local_dir


def cmd_start() -> None:
    """Start Etch daemon."""
    try:
        etch_dir = _find_etch_dir()
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    settings = Settings(etch_dir)
    settings.load()

    project_name = settings.get("project_name")
    project_id = settings.get("project_id")
    local_dir = _get_local_dir(project_id)
    pid_file = local_dir / "daemon.pid"
    log_file = local_dir / "daemon.log"

    console.print()
    console.print(f"[bold]Starting Etch daemon for {project_name}...[/bold]")

    # Check if already running
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)  # signal 0 = just check existence
            console.print(f"[yellow]⚠ Daemon already running (PID {pid})[/yellow]")
            console.print(f"  etch status  →  to monitor")
            console.print(f"  etch stop    →  to stop")
            raise typer.Exit(0)
        except (OSError, ValueError):
            pid_file.unlink(missing_ok=True)  # stale PID

    try:
        if platform.system() == "Darwin":
            # macOS: use launchd for proper background management
            _start_macos_launchd(etch_dir, project_id, local_dir)
        else:
            # Linux/VM: use nohup for reliable detachment from parent session
            _start_nohup(etch_dir, log_file)

        # Wait up to 5s for daemon to write PID file
        for _ in range(10):
            time.sleep(0.5)
            if pid_file.exists():
                break

        if pid_file.exists():
            pid = int(pid_file.read_text().strip())
            console.print(f"[green]✓[/green] Daemon started (PID {pid})")
            console.print(f"  Logs: {log_file}")
            console.print()
            console.print("[cyan]Next steps:[/cyan]")
            console.print("  etch status    (monitor activity)")
            console.print("  etch mcp       (get Claude/Cursor config)")
            console.print()
        else:
            console.print("[yellow]⚠ Daemon did not start. Check logs:[/yellow]")
            console.print(f"  tail -f {log_file}")

    except Exception as e:
        console.print(f"[red]✗ Failed to start daemon: {e}[/red]")
        raise typer.Exit(1)


def _start_nohup(etch_dir: Path, log_file: Path) -> None:
    """Start daemon with nohup so it survives the parent process exiting."""
    subprocess.Popen(
        [
            "nohup",
            sys.executable, "-m", "etch.daemon.runner", str(etch_dir),
        ],
        stdout=open(log_file, "a"),
        stderr=open(log_file, "a"),
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )


def _start_macos_launchd(etch_dir: Path, project_id: str, local_dir: Path) -> None:
    """Register and load a launchd plist on macOS."""
    plist_path = (
        Path.home() / "Library" / "LaunchAgents" / f"ai.etch.{project_id}.plist"
    )
    plist_path.parent.mkdir(parents=True, exist_ok=True)

    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>ai.etch.{project_id}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{sys.executable}</string>
        <string>-m</string>
        <string>etch.daemon.runner</string>
        <string>{etch_dir}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{etch_dir.parent}</string>
    <key>StandardOutPath</key>
    <string>{local_dir / "daemon.log"}</string>
    <key>StandardErrorPath</key>
    <string>{local_dir / "daemon.log"}</string>
    <key>KeepAlive</key>
    <true/>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
"""
    plist_path.write_text(plist_content)

    # Unload if already loaded (ignore error), then load
    subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
    subprocess.run(["launchctl", "load", str(plist_path)], check=True, capture_output=True)
