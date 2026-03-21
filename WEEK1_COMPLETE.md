# Engram Week 1 — Foundation — COMPLETE

## Build Status

All Week 1 components are implemented and tested.

### Core Files Created

#### 1. Package Setup
- ✓ `pyproject.toml` — Package metadata, dependencies, entry point
- ✓ `README.md` — Project documentation with CLI reference

#### 2. Configuration (engram/config/)
- ✓ `settings.py` — Reads/writes `.engram/config.json`, supports dot-notation keys

#### 3. Memory Storage (engram/memory/)
- ✓ `schema.sql` — SQLite schema with WAL mode
- ✓ `store.py` — Thread-safe wrapper for all database operations
  - File events (save, create, delete, rename)
  - Git commits with compact diffs
  - Co-edit pairs graph
  - File scores (recency, frequency, centrality)
  - Work sessions
  - Project registration

#### 4. Daemon Components (engram/daemon/)
- ✓ `watcher.py` — File watcher using watchdog
  - Ignores .git/, node_modules/, __pycache__, *.pyc, etc.
  - Only tracks .py, .js, .ts, .tsx, .jsx, .go, .rs, .java, .rb, .cpp, .c, .h, .cs, .json, .yaml, .yml, .toml, .env, .sql, .md
  - 2-second debounce for rapid saves
  - Stores events immediately in SQLite
  
- ✓ `git_poller.py` — Git commit monitor
  - On init: harvests last 90 days
  - On poll: fetches only new commits (every 60s)
  - Stores compact diff summaries (files, +/- lines)
  - Tracks file changes and authors

- ✓ `session_tracker.py` — Work session grouping
  - Groups file events into 30-min sessions
  - Assigns UUID to each session
  - Builds co-edit graph on session close
  - Increments co-edit pairs for all file combinations

- ✓ `runner.py` — Main daemon orchestrator
  - Starts file watcher, git poller, session tracker as threads
  - Writes PID to `.engram/daemon.pid`
  - Logs to `.engram/daemon.log`
  - Graceful shutdown on SIGTERM/SIGINT
  - WAL mode enabled on SQLite for concurrency

#### 5. CLI Commands (engram/cli/)
- ✓ `main.py` — Typer app root, all commands registered
- ✓ `init_cmd.py` — FULL IMPLEMENTATION
  - Auto-detects git repo and project root
  - Detects primary language
  - Gets active branch name
  - Creates `.engram/` directory
  - Initializes config.json
  - Initializes SQLite with schema
  - Harvests 90 days of git history
  - Stores commits and builds initial co-edit graph
  - Rich formatted output with checkmarks

- ✓ `start_cmd.py` — FULL IMPLEMENTATION
  - Finds `.engram/` config
  - Checks if already running (via PID file)
  - LaunchD support on macOS
  - Subprocess launching on Linux/Unix
  - Verifies daemon started

- ✓ `stop_cmd.py` — FULL IMPLEMENTATION
  - Finds daemon PID
  - Graceful SIGTERM
  - Fallback to SIGKILL if needed
  - CleanCleans up PID file
  - LaunchD unload on macOS

- ✓ `status_cmd.py` — FULL IMPLEMENTATION
  - Shows daemon running status with PID and uptime
  - Recent file events (last 10 with timestamps)
  - Active session info
  - Memory stats: files indexed, co-edit pairs, sessions, commits

- ✓ Stub files for Week 2+:
  - `context_cmd.py` — Debug: get_context() output
  - `mcp_cmd.py` — MCP server config
  - `setup_slm_cmd.py` — SLM installation
  - `doctor_cmd.py` — System diagnostics

### Testing

All components tested:

```bash
# Init test
engram init
  ✓ Detects git repo (commits, language, branch)
  ✓ Creates .engram/ with config.json and memory.db
  ✓ Harvests git history (commits, files, co-edits)

# Start/stop test
engram start
engram status
engram stop
  ✓ Daemon starts and runs
  ✓ File watcher captures create/save/delete/rename
  ✓ Shows live stats with uptime
  ✓ Daemon stops cleanly

# File watching test
echo "def hello(): pass" > main.py
  ✓ Events recorded with timestamp
  ✓ Relative paths correct
  ✓ Debouncing works (no duplicates for rapid saves)

# Session tracking test
Multiple file edits within 30 mins
  ✓ Files grouped in same session
  ✓ Co-edit pairs incremented
  ✓ Session ends on 30-min gap
```

## Architecture

```
Developer edits code
    ↓
FileWatcher (watchdog) captures: save, create, delete, rename
    ↓
Events stored in SQLite immediately (file_events table)
    ↓
SessionTracker groups events into 30-min work sessions
    ↓
On session close: increments co-edit pairs for all file combinations
    ↓
GitPoller polls every 60s for new commits
    ↓
Commits stored with diff summaries (compact, not full diffs)
    ↓
All data in .engram/memory.db (SQLite, WAL mode)
    ↓
[Week 2] Classifier analyzes change type
    ↓
[Week 2] Retrieval serves supporting context via MCP
```

## Key Design Decisions

1. **Thread-safe SQLite** — WAL mode + thread-local connections in Store class
2. **File filtering** — Aggressive ignore list prevents noise from build artifacts, caches, etc.
3. **Debouncing** — 2-second window prevents duplicate events from rapid saves
4. **Compact storage** — Diffs stored as summaries, not full text
5. **Local-first** — Everything in `.engram/`, no cloud sync
6. **Graceful daemonization** — POSIX signal handling, proper cleanup

## What's NOT in Week 1

- MCP server (Week 2)
- Change type classification (Week 2)
- Context retrieval strategies (Week 2)
- SLM backends (Week 3)
- Interactive setup wizard (Week 3)

## Running the System

```bash
# Install
pip install -e .

# Initialize
cd my-project
engram init

# Start daemon
engram start

# Monitor
engram status

# Stop
engram stop
```

## Files & LOC

| Component | Files | Purpose |
|-----------|-------|---------|
| Config | 1 | Read/write .engram/config.json |
| Memory | 2 | SQLite schema + thread-safe wrapper |
| Daemon | 5 | File watching, git polling, session tracking, orchestration |
| CLI | 11 | Commands + main app |
| **Total** | **19** | |

## Next Steps (Week 2)

1. `indexer.py` — Build co-edit graph scores
2. `classifier.py` — Detect change type from diff
3. `retrieval.py` — Per-change-type context strategies
4. `ranker.py` — Score and rank candidate files
5. `packer.py` — Assemble token-budgeted context
6. `mcp/server.py` — FastMCP server with get_context()
7. `context_cmd.py` — Debug CLI

---

**Engram Week 1: FOUNDATION COMPLETE**

All core infrastructure working. Ready for Week 2 intelligence layer.
