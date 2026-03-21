"""Implementation of 'etch memory' command group — inspect project memory."""

import json
import time
from pathlib import Path
from typing import Optional

import typer
from platformdirs import user_data_dir
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from etch.config.settings import Settings
from etch.memory.store import Store


console = Console()
app = typer.Typer(help="Inspect what Etch has learned about this project.")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_etch_dir() -> Path:
    current = Path.cwd()
    while current != current.parent:
        d = current / ".etch"
        if d.exists() and (d / "config.json").exists():
            return d
        current = current.parent
    raise FileNotFoundError("No .etch directory found. Run 'etch init' first.")


def _load_store() -> tuple[Store, Settings, str]:
    """Return (store, settings, project_id).

    DB resolution order:
    1. Local user_data_dir path (preferred — always local to current machine)
    2. Stored daemon.db_path from config (fallback if local doesn't exist)
    """
    etch_dir = _find_etch_dir()
    settings = Settings(etch_dir)
    settings.load()
    project_id = settings.get("project_id")

    local_dir = Path(user_data_dir("etch", "etch")) / project_id
    local_dir.mkdir(parents=True, exist_ok=True)
    local_db = local_dir / "memory.db"

    # Prefer local DB; fall back to config path if local doesn't exist
    db_path_str = settings.get("daemon.db_path")
    if local_db.exists():
        db_path = local_db
    elif db_path_str and Path(db_path_str).exists():
        db_path = Path(db_path_str)
    else:
        db_path = local_db  # will be created fresh (empty) if missing

    store = Store(db_path)
    return store, settings, project_id


def _fmt_time(ts: int) -> str:
    if not ts:
        return "—"
    now = int(time.time())
    diff = now - ts
    if diff < 60:
        return "just now"
    elif diff < 3600:
        return f"{diff // 60}m ago"
    elif diff < 86400:
        return f"{diff // 3600}h ago"
    else:
        return time.strftime("%Y-%m-%d", time.localtime(ts))


def _short_path(path: str, max_len: int = 48) -> str:
    if len(path) <= max_len:
        return path
    parts = Path(path).parts
    if len(parts) > 3:
        return str(Path(*parts[:1]) / "…" / Path(*parts[-2:]))
    return f"…/{Path(path).name}"


# ── Commands ──────────────────────────────────────────────────────────────────

@app.callback(invoke_without_command=True)
def memory_overview(ctx: typer.Context):
    """Show a full overview of everything stored in project memory."""
    if ctx.invoked_subcommand is not None:
        return

    try:
        store, settings, project_id = _load_store()
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    project_name = settings.get("project_name", "unknown")
    project_root = settings.get("project_root", "")

    console.print()
    console.print(f"[bold cyan]◆ Etch Memory — {project_name}[/bold cyan]")
    console.print(f"  [dim]{project_root}[/dim]")
    console.print()

    # ── Stats summary ─────────────────────────────────────────────────────────
    conn = store._get_conn()

    commit_count = conn.execute(
        "SELECT COUNT(*) FROM git_commits WHERE project_id = ?", (project_id,)
    ).fetchone()[0]

    event_count = conn.execute(
        "SELECT COUNT(*) FROM file_events WHERE project_id = ?", (project_id,)
    ).fetchone()[0]

    session_count = conn.execute(
        "SELECT COUNT(*) FROM sessions WHERE project_id = ?", (project_id,)
    ).fetchone()[0]

    co_edit_count = conn.execute(
        "SELECT COUNT(*) FROM co_edit_pairs WHERE project_id = ?", (project_id,)
    ).fetchone()[0]

    files_count = conn.execute(
        """SELECT COUNT(DISTINCT f) FROM (
            SELECT file_a as f FROM co_edit_pairs WHERE project_id = ?
            UNION SELECT file_b as f FROM co_edit_pairs WHERE project_id = ?
        )""", (project_id, project_id)
    ).fetchone()[0]

    # Stats panels
    stats = [
        Panel(f"[bold]{commit_count}[/bold]\n[dim]git commits[/dim]", expand=True, border_style="dim"),
        Panel(f"[bold]{files_count}[/bold]\n[dim]files tracked[/dim]", expand=True, border_style="dim"),
        Panel(f"[bold]{co_edit_count}[/bold]\n[dim]co-edit pairs[/dim]", expand=True, border_style="dim"),
        Panel(f"[bold]{session_count}[/bold]\n[dim]work sessions[/dim]", expand=True, border_style="dim"),
        Panel(f"[bold]{event_count}[/bold]\n[dim]file events[/dim]", expand=True, border_style="dim"),
    ]
    console.print(Columns(stats))
    console.print()

    # ── Top co-edit relationships ─────────────────────────────────────────────
    top_pairs = store.get_co_edit_pairs(project_id, limit=8)
    if top_pairs:
        console.print("[bold]Top co-edit relationships[/bold]  [dim](files always changed together)[/dim]")
        t = Table(box=box.SIMPLE, show_header=True, header_style="bold dim", padding=(0, 1))
        t.add_column("File A", style="cyan", max_width=42)
        t.add_column("File B", style="cyan", max_width=42)
        t.add_column("Times", justify="right", style="bold green")
        t.add_column("Last seen", style="dim")
        for p in top_pairs:
            t.add_row(
                _short_path(p["file_a"]),
                _short_path(p["file_b"]),
                str(p["co_edit_count"]),
                _fmt_time(p["last_seen"]),
            )
        console.print(t)

    # ── Recent commits ────────────────────────────────────────────────────────
    commits = store.get_git_commits(project_id, limit=5)
    if commits:
        console.print("[bold]Recent commits[/bold]")
        t = Table(box=box.SIMPLE, show_header=True, header_style="bold dim", padding=(0, 1))
        t.add_column("Hash", style="yellow", width=8)
        t.add_column("Message", max_width=52)
        t.add_column("Author", style="dim", max_width=18)
        t.add_column("When", style="dim")
        for c in commits:
            msg = (c["message"] or "")[:52]
            t.add_row(c["commit_hash"][:7], msg, c["author"] or "", _fmt_time(c["ts"]))
        console.print(t)

    # ── Recent file events ────────────────────────────────────────────────────
    events = store.get_file_events(project_id, limit=8)
    if events:
        console.print("[bold]Recent file activity[/bold]")
        t = Table(box=box.SIMPLE, show_header=True, header_style="bold dim", padding=(0, 1))
        t.add_column("File", style="cyan", max_width=58)
        t.add_column("Event", style="dim", width=8)
        t.add_column("When", style="dim")
        icons = {"save": "💾", "create": "✨", "delete": "🗑", "rename": "🔄"}
        for e in events:
            icon = icons.get(e["event_type"], "•")
            t.add_row(_short_path(e["file_path"]), f"{icon} {e['event_type']}", _fmt_time(e["ts"]))
        console.print(t)

    console.print()
    console.print("[dim]Subcommands: etch memory files · commits · sessions · graph <file>[/dim]")
    console.print()


@app.command("files")
def cmd_files(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of files to show"),
    sort: str = typer.Option("co-edits", "--sort", "-s", help="Sort by: co-edits | recency | frequency"),
):
    """Show all files Etch knows about, ranked by importance."""
    try:
        store, settings, project_id = _load_store()
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    conn = store._get_conn()

    # Build file list from co_edit_pairs (most reliable source — always populated after init)
    rows = conn.execute(
        """
        SELECT file_path, COUNT(*) as pair_count, SUM(co_edit_count) as total_co_edits,
               MAX(last_seen) as last_seen
        FROM (
            SELECT file_a as file_path, co_edit_count, last_seen FROM co_edit_pairs WHERE project_id = ?
            UNION ALL
            SELECT file_b as file_path, co_edit_count, last_seen FROM co_edit_pairs WHERE project_id = ?
        )
        GROUP BY file_path
        ORDER BY total_co_edits DESC
        LIMIT ?
        """,
        (project_id, project_id, limit),
    ).fetchall()

    console.print()
    console.print(f"[bold cyan]◆ Files in memory[/bold cyan]  [dim]({settings.get('project_name')})[/dim]")
    console.print()

    if not rows:
        console.print("  [dim]No files indexed yet. Run 'etch start' and make some edits.[/dim]")
        return

    t = Table(box=box.SIMPLE, show_header=True, header_style="bold dim", padding=(0, 1))
    t.add_column("#", style="dim", width=3)
    t.add_column("File", style="cyan", max_width=58)
    t.add_column("Co-edit pairs", justify="right", style="bold green")
    t.add_column("Total co-edits", justify="right", style="green")
    t.add_column("Last seen", style="dim")

    for i, row in enumerate(rows, 1):
        t.add_row(
            str(i),
            _short_path(row["file_path"]),
            str(row["pair_count"]),
            str(row["total_co_edits"]),
            _fmt_time(row["last_seen"]),
        )

    console.print(t)
    console.print()


@app.command("commits")
def cmd_commits(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of commits to show"),
    file: Optional[str] = typer.Option(None, "--file", "-f", help="Filter by file path"),
):
    """Show git commits stored in memory."""
    try:
        store, settings, project_id = _load_store()
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    conn = store._get_conn()

    if file:
        # Filter commits that touched this file
        rows = conn.execute(
            """
            SELECT commit_hash, ts, message, author, diff_summary, files_changed
            FROM git_commits
            WHERE project_id = ? AND files_changed LIKE ?
            ORDER BY ts DESC LIMIT ?
            """,
            (project_id, f"%{file}%", limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT commit_hash, ts, message, author, diff_summary, files_changed
            FROM git_commits WHERE project_id = ? ORDER BY ts DESC LIMIT ?
            """,
            (project_id, limit),
        ).fetchall()

    console.print()
    title = f"[bold cyan]◆ Git commits in memory[/bold cyan]  [dim]({settings.get('project_name')})"
    if file:
        title += f" · filtered by [cyan]{file}[/cyan]"
    title += "[/dim]"
    console.print(title)
    console.print()

    if not rows:
        console.print("  [dim]No commits found.[/dim]")
        return

    for row in rows:
        files = json.loads(row["files_changed"]) if row["files_changed"] else []
        msg = (row["message"] or "").strip()
        hash_short = row["commit_hash"][:7]
        when = _fmt_time(row["ts"])
        author = row["author"] or ""

        console.print(
            f"  [yellow]{hash_short}[/yellow]  [bold]{msg}[/bold]  "
            f"[dim]{author} · {when}[/dim]"
        )
        if row["diff_summary"]:
            console.print(f"  [dim]         {row['diff_summary']}[/dim]")
        if files:
            shown = files[:4]
            rest = len(files) - 4
            file_str = "  ".join(f"[dim cyan]{_short_path(f)}[/dim cyan]" for f in shown)
            extra = f"  [dim]+{rest} more[/dim]" if rest > 0 else ""
            console.print(f"           {file_str}{extra}")
        console.print()


@app.command("sessions")
def cmd_sessions(
    limit: int = typer.Option(15, "--limit", "-n", help="Number of sessions to show"),
):
    """Show recorded work sessions."""
    try:
        store, settings, project_id = _load_store()
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    conn = store._get_conn()
    rows = conn.execute(
        """
        SELECT session_id, started_at, ended_at, files_touched, inferred_task, change_type
        FROM sessions WHERE project_id = ? ORDER BY started_at DESC LIMIT ?
        """,
        (project_id, limit),
    ).fetchall()

    console.print()
    console.print(f"[bold cyan]◆ Work sessions[/bold cyan]  [dim]({settings.get('project_name')})[/dim]")
    console.print()

    if not rows:
        console.print("  [dim]No sessions recorded yet. The daemon records sessions as you work.[/dim]")
        return

    for row in rows:
        started = row["started_at"] or 0
        ended = row["ended_at"] or int(time.time())
        duration_mins = max(1, (ended - started) // 60)
        files = json.loads(row["files_touched"]) if row["files_touched"] else []
        change_type = row["change_type"] or "unknown"
        task = row["inferred_task"] or ""

        change_colors = {
            "bug_fix": "red", "refactor": "yellow", "new_feature": "green",
            "config": "blue", "test": "magenta", "dependency": "cyan", "unknown": "dim"
        }
        color = change_colors.get(change_type, "dim")

        console.print(
            f"  [bold]{_fmt_time(started)}[/bold]  "
            f"[{color}]{change_type}[/{color}]  "
            f"[dim]{duration_mins}m · {len(files)} files[/dim]"
        )
        if task:
            console.print(f"  [dim]  → {task}[/dim]")
        if files:
            shown = files[:5]
            rest = len(files) - 5
            for f in shown:
                console.print(f"    [dim cyan]{_short_path(f)}[/dim cyan]")
            if rest > 0:
                console.print(f"    [dim]+ {rest} more files[/dim]")
        console.print()


@app.command("graph")
def cmd_graph(
    file: str = typer.Argument(..., help="File path to show co-edit relationships for"),
    limit: int = typer.Option(15, "--limit", "-n", help="Max related files to show"),
):
    """Show co-edit graph for a specific file — what it's related to and why."""
    try:
        store, settings, project_id = _load_store()
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    conn = store._get_conn()

    # Get all co-edit pairs involving this file (partial match)
    rows = conn.execute(
        """
        SELECT file_a, file_b, co_edit_count, last_seen
        FROM co_edit_pairs
        WHERE project_id = ? AND (file_a LIKE ? OR file_b LIKE ?)
        ORDER BY co_edit_count DESC
        LIMIT ?
        """,
        (project_id, f"%{file}%", f"%{file}%", limit),
    ).fetchall()

    console.print()
    console.print(f"[bold cyan]◆ Co-edit graph[/bold cyan]  [dim]{file}[/dim]")
    console.print()

    if not rows:
        console.print(f"  [dim]No co-edit relationships found for '{file}'[/dim]")
        console.print(f"  [dim]Try a partial path, e.g. 'auth' or 'models'[/dim]")
        return

    # Find the canonical file name (the one that matched)
    matched_files = set()
    for row in rows:
        if file in row["file_a"]:
            matched_files.add(row["file_a"])
        if file in row["file_b"]:
            matched_files.add(row["file_b"])

    # Build relationship view
    t = Table(box=box.SIMPLE, show_header=True, header_style="bold dim", padding=(0, 1))
    t.add_column("Related file", style="cyan", max_width=52)
    t.add_column("Co-edits", justify="right", style="bold green")
    t.add_column("Last together", style="dim")
    t.add_column("Strength", style="dim")

    max_count = rows[0]["co_edit_count"] if rows else 1

    for row in rows:
        # Which file is the "other" one
        a, b = row["file_a"], row["file_b"]
        other = b if any(file in a for a in [a]) and file not in b else a
        if file in a and file in b:
            other = b  # both match, show b

        count = row["co_edit_count"]
        strength_pct = int((count / max_count) * 100)
        bar = "█" * (strength_pct // 10) + "░" * (10 - strength_pct // 10)

        t.add_row(
            _short_path(other),
            str(count),
            _fmt_time(row["last_seen"]),
            f"[green]{bar}[/green] {strength_pct}%",
        )

    console.print(t)

    # Also show commits where this file appeared
    commit_rows = conn.execute(
        """
        SELECT commit_hash, ts, message, author
        FROM git_commits
        WHERE project_id = ? AND files_changed LIKE ?
        ORDER BY ts DESC LIMIT 5
        """,
        (project_id, f"%{file}%"),
    ).fetchall()

    if commit_rows:
        console.print("[bold]Recent commits touching this file:[/bold]")
        for row in commit_rows:
            console.print(
                f"  [yellow]{row['commit_hash'][:7]}[/yellow]  "
                f"{(row['message'] or '').strip()[:60]}  "
                f"[dim]{_fmt_time(row['ts'])}[/dim]"
            )
    console.print()
