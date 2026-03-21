# Etch

Passive local CLI daemon that watches your project and serves minimum necessary context to AI coding tools via MCP.

Named after the biological term for a physical memory trace in the brain — exactly what this is.

## Installation

```bash
# Install globally via pip
pip install etch
```

## Quick Start

```bash
# Initialize a project (run from inside any git repo)
cd ~/my-project
etch init

# Start daemon
etch start

# Check project status
etch status

# See all tracked projects
etch projects

# Get MCP configuration
etch mcp
```

## CLI Commands

### Core Commands (Week 1)

- **`etch init`** — Auto-detect git repo, create `.etch/` config, harvest git history
- **`etch start`** — Start daemon in background (uses launchd on macOS)
- **`etch stop`** — Stop daemon gracefully
- **`etch status`** — Show tracked files, recent events, active session, memory stats (or list all projects if outside a project)
- **`etch projects`** — Show all tracked projects and their daemon status

### Intelligence Commands (Week 2+)

- **`etch context`** — Debug: print what `get_context()` would return right now
- **`etch mcp`** — Print MCP server JSON config to paste into Claude Code / Cursor

### System Commands (Week 3+)

- **`etch setup-slm`** — Auto-detect hardware and install best local SLM
- **`etch doctor`** — Diagnose issues: daemon running, git found, SLM loaded

## How It Works

1. **Watch** — File watcher monitors project changes, filters noise
2. **Poll** — Git poller checks for new commits every 60 seconds
3. **Track** — Session tracker groups edits into 30-minute work sessions
4. **Index** — Co-edit graph builds supporting context from file relationships
5. **Serve** — MCP server exposes `get_context()` for AI tools

## Configuration

Configuration is stored in `.etch/config.json`:

```json
{
  "project_id": "uuid",
  "project_root": "/path/to/project",
  "project_name": "my-app",
  "watcher": {
    "ignore_patterns": [".git", "node_modules", "__pycache__", ...],
    "session_gap_minutes": 30
  },
  "git": {
    "poll_interval_seconds": 60,
    "history_days": 90
  },
  "slm": {
    "backend": "heuristic",
    "model": "unknown",
    "fallback": "heuristic"
  },
  "mcp": {
    "host": "127.0.0.1",
    "port": 7777
  }
}
```

## Data Storage

### Per-Project (in `.etch/`)

- **`config.json`** — Project configuration including assigned MCP port
- **`memory.db`** — SQLite database with file events, commits, sessions, co-edit graph (stored in user data dir for SQLite compatibility)
- **`daemon.pid`** — Process ID when daemon is running
- **`daemon.log`** — Daemon logs

### Global (in `~/.config/etch/`)

- **`projects.json`** — Registry of all tracked projects and their MCP ports

## Design Principles

- **Passive** — No setup friction, no UI, no configuration
- **Local** — Everything stored on disk, no cloud sync
- **Minimal** — Diffs not full files, recency not similarity, supporting context not raw code
- **Behavioral** — Uses developer signals: which files get touched together, recent diffs

## Development

```bash
# Install in development mode with test deps
pip install -e ".[dev]"

# Run tests
pytest

# Check daemon logs
tail -f .etch/daemon.log
```

## License

MIT
