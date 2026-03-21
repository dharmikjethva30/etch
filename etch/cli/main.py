"""Main Typer app for Etch CLI."""

import typer

app = typer.Typer(
    name="etch",
    help="Passive memory layer for AI coding tools",
    no_args_is_help=True,
)


@app.command()
def init() -> None:
    """Auto-detect git repo, create .etch/ config, and harvest git history."""
    from .init_cmd import cmd_init
    cmd_init()


@app.command()
def start() -> None:
    """Start daemon in background."""
    from .start_cmd import cmd_start
    cmd_start()


@app.command()
def stop() -> None:
    """Stop daemon gracefully."""
    from .stop_cmd import cmd_stop
    cmd_stop()


@app.command()
def status() -> None:
    """Show tracked files, recent events, active session, and memory stats."""
    from .status_cmd import cmd_status
    cmd_status()


@app.command()
def projects() -> None:
    """Show all tracked projects and their daemon status."""
    from .projects_cmd import cmd_projects
    cmd_projects()


@app.command()
def context() -> None:
    """Debug: print what get_context() would return right now."""
    typer.echo("Coming soon - etch context")


@app.command("setup-slm")
def setup_slm() -> None:
    """Auto-detect hardware and install best local SLM."""
    typer.echo("Coming soon - etch setup-slm")


@app.command()
def mcp() -> None:
    """Print MCP server JSON config to paste into Claude Code / Cursor."""
    typer.echo("Coming soon - etch mcp")


@app.command()
def doctor() -> None:
    """Diagnose issues: daemon running, git found, SLM loaded."""
    typer.echo("Coming soon - etch doctor")


if __name__ == "__main__":
    app()
