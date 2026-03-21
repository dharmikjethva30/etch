# Etch — Build Instructions for Claude Code

## What is Etch?

Etch is a passive, local CLI daemon that watches your project and serves
the minimum necessary context to AI coding tools via MCP. Named after the
biological term for a physical memory trace in the brain — exactly what this is.

No UI. No setup friction. No cloud. It just runs.

```
developer edits code
       ↓
etch watches silently (file watcher + git poller)
       ↓
SLM understands change type (bug fix? refactor? new feature?)
       ↓
memory index surfaces supporting context for that change type
       ↓
AI tool calls get_context() via MCP
       ↓
AI gets exactly what it needs — nothing else
```

---

## Core Insight

**We don't compress the past — we surface the present.**

Every other context tool either loads everything (expensive, noisy) or relies
on semantic similarity search (misses behavioral patterns). Etch uses
developer behavior signals: which files get touched together, what recent
diffs say, what the current work session looks like.

Diffs not full files. Recency not similarity. Supporting context not raw code.

---

## CLI Commands to Build

```bash
etch init          # auto-detects git repo, creates .etch/ config, harvests git history
etch start         # starts daemon in background (launchd plist on macOS)
etch stop          # stops daemon gracefully
etch status        # shows tracked files, recent events, active session, memory stats
etch context       # debug: print what get_context() would return right now
etch setup-slm     # auto-detects hardware, installs best local SLM
etch mcp           # prints MCP server JSON config to paste into Claude Code / Cursor
etch doctor        # diagnose issues: daemon running? git found? SLM loaded?
```

---

## Full Project Structure

```
etch/
├── pyproject.toml
├── README.md
├── CLAUDE.md                           ← this file
│
├── etch/
│   ├── __init__.py
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── main.py                     # Typer app root, registers all commands
│   │   ├── init_cmd.py                 # etch init
│   │   ├── start_cmd.py                # etch start (launchd on macOS)
│   │   ├── stop_cmd.py                 # etch stop
│   │   ├── status_cmd.py               # etch status
│   │   ├── context_cmd.py              # etch context (debug/test)
│   │   ├── setup_slm_cmd.py            # etch setup-slm
│   │   ├── mcp_cmd.py                  # etch mcp (print config)
│   │   └── doctor_cmd.py               # etch doctor
│   │
│   ├── daemon/
│   │   ├── __init__.py
│   │   ├── runner.py                   # starts all threads, main daemon loop
│   │   ├── watcher.py                  # FSEvents via watchdog, filters noise
│   │   ├── git_poller.py               # polls git log + diffs every 60s
│   │   └── session_tracker.py          # groups edits into 30-min work sessions
│   │
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── store.py                    # all SQLite reads/writes
│   │   ├── indexer.py                  # co-edit graph + recency score builder
│   │   └── schema.sql                  # DB schema (see below)
│   │
│   ├── intelligence/
│   │   ├── __init__.py
│   │   ├── classifier.py               # detects change type from diff + task
│   │   ├── retrieval.py                # retrieval strategy per change type
│   │   ├── ranker.py                   # scores + ranks candidate files
│   │   ├── packer.py                   # assembles token-budgeted context bundle
│   │   └── slm/
│   │       ├── __init__.py
│   │       ├── base.py                 # abstract SLMBackend interface
│   │       ├── heuristic.py            # rule-based, zero deps (Phase 1 default)
│   │       ├── ollama_slm.py           # Ollama backend (primary)
│   │       ├── mlx_slm.py              # MLX backend (Apple Silicon best perf)
│   │       └── llamacpp_slm.py         # llama-cpp-python fallback
│   │
│   ├── mcp/
│   │   ├── __init__.py
│   │   └── server.py                   # FastMCP server exposing get_context()
│   │
│   └── config/
│       ├── __init__.py
│       ├── settings.py                 # reads/writes .etch/config.json
│       └── hardware.py                 # detects chip, RAM, GPU, Ollama presence
│
└── tests/
    ├── __init__.py
    ├── test_watcher.py
    ├── test_git_poller.py
    ├── test_indexer.py
    ├── test_classifier.py
    └── test_mcp.py
```

---

## SQLite Schema

File: `etch/memory/schema.sql`

```sql
CREATE TABLE IF NOT EXISTS file_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          INTEGER NOT NULL,
    file_path   TEXT NOT NULL,
    event_type  TEXT NOT NULL CHECK(event_type IN ('save','create','delete','rename')),
    session_id  TEXT,
    project_id  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS git_commits (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    commit_hash     TEXT NOT NULL,
    ts              INTEGER NOT NULL,
    message         TEXT,
    author          TEXT,
    diff_summary    TEXT,
    files_changed   TEXT,           -- JSON array of file paths
    project_id      TEXT NOT NULL,
    UNIQUE(commit_hash, project_id)
);

CREATE TABLE IF NOT EXISTS co_edit_pairs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    file_a          TEXT NOT NULL,
    file_b          TEXT NOT NULL,
    co_edit_count   INTEGER DEFAULT 1,
    last_seen       INTEGER,
    project_id      TEXT NOT NULL,
    UNIQUE(file_a, file_b, project_id)
);

CREATE TABLE IF NOT EXISTS file_scores (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path           TEXT NOT NULL,
    recency_score       REAL DEFAULT 0.0,
    frequency_score     REAL DEFAULT 0.0,
    centrality_score    REAL DEFAULT 0.0,
    last_updated        INTEGER,
    project_id          TEXT NOT NULL,
    UNIQUE(file_path, project_id)
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id      TEXT PRIMARY KEY,
    started_at      INTEGER,
    ended_at        INTEGER,
    files_touched   TEXT,           -- JSON array
    inferred_task   TEXT,
    change_type     TEXT,
    project_id      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    project_id      TEXT PRIMARY KEY,
    root_path       TEXT NOT NULL,
    name            TEXT,
    created_at      INTEGER,
    last_active     INTEGER
);

CREATE INDEX IF NOT EXISTS idx_file_events_path_ts   ON file_events(file_path, ts DESC);
CREATE INDEX IF NOT EXISTS idx_file_events_session   ON file_events(session_id);
CREATE INDEX IF NOT EXISTS idx_file_events_project   ON file_events(project_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_co_edit_file_a        ON co_edit_pairs(file_a, project_id);
CREATE INDEX IF NOT EXISTS idx_file_scores_project   ON file_scores(project_id, recency_score DESC);
CREATE INDEX IF NOT EXISTS idx_git_commits_project   ON git_commits(project_id, ts DESC);
```

---

## MCP get_context() Interface

```python
@mcp.tool()
def get_context(
    current_file: str,
    task: str = "",
    token_budget: int = 4000
) -> dict:
    """
    Returns minimum necessary context to work on current_file.
    Returns recent diffs and supporting files — never full file contents.
    """
    return {
        "change_type": str,           # bug_fix|refactor|new_feature|config|test|dependency|unknown
        "active_session": {
            "files": list[str],
            "duration_mins": int,
            "inferred_task": str
        },
        "supporting_files": [
            {
                "path": str,
                "reason": str,        # why this file is relevant
                "recent_diff": str,   # last diff, NOT full file
                "recency_score": float
            }
        ],
        "recent_commits": [
            {
                "hash": str,
                "message": str,
                "diff_summary": str,
                "files": list[str]
            }
        ],
        "stable_dependencies": list[str],   # high-centrality, rarely-changing files
        "token_count": int
    }
```

---

## Change Types & Retrieval Strategies

The classifier detects one of these from the diff shape + task string:

| Change Type   | Detection Signals                           | What to Surface                                           |
|---------------|---------------------------------------------|-----------------------------------------------------------|
| `bug_fix`     | "fix", "bug", "error", "broken" in task     | Recent diffs in area, related tests, similar past fixes   |
| `refactor`    | Large rename/move, same logic restructured  | All callers, interface contracts, test coverage           |
| `new_feature` | New file/class/function added               | Similar existing features, patterns, relevant interfaces  |
| `config`      | .env, config files, settings touched        | Everything that reads that config                         |
| `test`        | Test file created/edited                    | Source file being tested, fixtures, test utilities        |
| `dependency`  | package.json / pyproject.toml changed       | All files importing that dependency                       |
| `unknown`     | Fallback                                    | Top files by recency + co-edit score                      |

---

## SLM Auto-Discovery Logic

`etch setup-slm` detects hardware and installs the best option:

```
Priority order:
1. If Ollama is running:
   - RAM >= 16GB → pull qwen3:1.7b
   - RAM >= 8GB  → pull qwen3:0.6b
   - Else        → use heuristic backend

2. Elif Apple Silicon (arm64):
   - pip install mlx-lm
   - Download Qwen3-1.7B MLX weights

3. Elif CUDA available:
   - pip install llama-cpp-python[cuda]
   - Download Phi-4-mini GGUF Q4

4. Else (CPU fallback):
   - pip install llama-cpp-python
   - Download SmolLM2-1.7B GGUF Q4

5. Heuristic always available as fallback (zero deps)
```

SLM backend is stored in `.etch/config.json` → `slm.backend` field.
Daemon loads the configured backend at startup.

---

## pyproject.toml

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "etch"
version = "0.1.0"
description = "Passive memory layer for AI coding tools"
requires-python = ">=3.11"
dependencies = [
    "typer>=0.12",
    "watchdog>=4.0",
    "gitpython>=3.1",
    "fastmcp>=2.0",
    "sqlite-utils>=3.35",
    "rich>=13.0",
    "httpx>=0.27",
    "platformdirs>=4.0",
    "psutil>=5.9",
]

[project.optional-dependencies]
mlx     = ["mlx-lm>=0.16"]
llamacpp = ["llama-cpp-python>=0.2"]
dev     = ["pytest>=8.0", "pytest-asyncio>=0.23"]

[project.scripts]
etch = "etch.cli.main:app"
```

---

## Config File Format (.etch/config.json)

```json
{
  "project_id": "uuid-here",
  "project_root": "/path/to/project",
  "project_name": "my-app",
  "created_at": 1700000000,
  "watcher": {
    "ignore_patterns": [
      ".git", "node_modules", "__pycache__", ".venv",
      "*.pyc", "*.log", "*.lock", ".DS_Store",
      "dist", "build", ".next", "coverage"
    ],
    "session_gap_minutes": 30
  },
  "git": {
    "poll_interval_seconds": 60,
    "history_days": 90
  },
  "slm": {
    "backend": "ollama",
    "model": "qwen3:0.6b",
    "fallback": "heuristic"
  },
  "mcp": {
    "host": "127.0.0.1",
    "port": 7777
  },
  "daemon": {
    "pid_file": ".etch/daemon.pid",
    "log_file": ".etch/daemon.log"
  }
}
```

---

## Key Implementation Notes

### File Watcher (watcher.py)
- Use `watchdog` with `Observer` using FSEvents on macOS
- Filter out ALL noise: .git/, node_modules/, __pycache__, .venv, *.pyc, *.log
- Debounce rapid saves (same file within 2 seconds = one event)
- Only track: .py, .js, .ts, .tsx, .jsx, .go, .rs, .java, .rb, .cpp, .c, .h, .cs, .json, .yaml, .yml, .toml, .env, .sql, .md
- Write events to SQLite immediately, session_tracker groups them

### Git Poller (git_poller.py)
- Use `gitpython` to walk commits
- On init: harvest last 90 days
- On poll (every 60s): only fetch new commits since last known hash
- Store compact diff summaries — NOT full diffs. Extract: files changed, lines added/removed, key function/class names touched
- Parse commit message for intent keywords

### Session Tracker (session_tracker.py)
- Group file_events into sessions: gap > 30 min = new session
- Session gets a UUID
- When session closes (30 min gap or daemon stop), write session record
- Sessions feed the co-edit index

### Co-edit Indexer (indexer.py)
- After each session closes: for every pair of files in that session, increment co_edit_count
- Recency score: `score = score * 0.95 + (1 if touched_in_last_hour else 0)`
  — decays over time, recent activity boosts it
- Rebuild file_scores every 15 minutes

### Daemon (runner.py)
- Three threads: FileWatcherThread, GitPollerThread, IndexerThread
- One process: MCPServerProcess (FastMCP)
- Graceful shutdown on SIGTERM
- Write PID to .etch/daemon.pid on start
- Log to .etch/daemon.log

### launchd Integration (start_cmd.py)
- Generate a launchd plist at ~/Library/LaunchAgents/ai.etch.<project_id>.plist
- `launchctl load` on start, `launchctl unload` on stop
- WorkingDirectory = project root
- StandardOutPath / StandardErrorPath = .etch/daemon.log

### MCP Server (mcp/server.py)
- FastMCP on localhost:7777 (configurable)
- Single tool: `get_context`
- On call: query store → classify → retrieve → rank → pack → return
- Target latency: < 150ms total

### etch init output should look like:
```
Detecting project...
  ✓ Git repo: my-app (847 commits, 38 contributors)
  ✓ Language: Python
  ✓ Active branch: feature/billing-refactor

Creating .etch/
  ✓ config.json
  ✓ memory.db (SQLite, WAL mode)

Harvesting git history (last 90 days)...
  ✓ 124 commits processed
  ✓ 38 active files indexed
  ✓ 892 co-edit pairs discovered

SLM: Ollama detected → using qwen3:0.6b
  ✓ Model available

Ready. Run: etch start
Then:      etch mcp  (to get Claude/Cursor config)
```

---

## Build Order (Week 1 — Foundation)

Build in this exact order. Each step should work before moving to next:

1. `pyproject.toml` — package setup, entry point
2. `etch/cli/main.py` — Typer app skeleton, register all commands as stubs
3. `etch/config/settings.py` — read/write .etch/config.json
4. `etch/memory/schema.sql` + `etch/memory/store.py` — SQLite wrapper
5. `etch/cli/init_cmd.py` — full implementation (git detection, history harvest, db init)
6. `etch/daemon/watcher.py` — file watcher
7. `etch/daemon/git_poller.py` — git poller
8. `etch/daemon/session_tracker.py` — session grouping
9. `etch/daemon/runner.py` — starts all threads
10. `etch/cli/start_cmd.py` + `stop_cmd.py` — launchd integration
11. `etch/cli/status_cmd.py` — show live stats from SQLite
12. Smoke test: `pip install -e . && etch init && etch start && etch status`

## Build Order (Week 2 — Intelligence + MCP)

13. `etch/memory/indexer.py` — co-edit graph, score builder
14. `etch/intelligence/classifier.py` — heuristic change type detection
15. `etch/intelligence/retrieval.py` — per-change-type strategies
16. `etch/intelligence/ranker.py` — score and rank candidates
17. `etch/intelligence/packer.py` — token-budget-aware bundle assembly
18. `etch/mcp/server.py` — FastMCP get_context() tool
19. `etch/cli/context_cmd.py` — debug CLI for get_context()
20. `etch/cli/mcp_cmd.py` — print MCP config JSON

## Build Order (Week 3 — SLM)

21. `etch/config/hardware.py` — detect chip/RAM/Ollama
22. `etch/intelligence/slm/base.py` — abstract interface
23. `etch/intelligence/slm/heuristic.py` — rules wrapped in interface
24. `etch/intelligence/slm/ollama_slm.py` — Ollama backend
25. `etch/intelligence/slm/mlx_slm.py` — MLX backend
26. `etch/intelligence/slm/llamacpp_slm.py` — llama-cpp fallback
27. `etch/cli/setup_slm_cmd.py` — interactive setup
28. `etch/cli/doctor_cmd.py` — full diagnostics

---

## Success Metrics

| Metric                   | Baseline         | Target            |
|--------------------------|------------------|-------------------|
| Files loaded per task    | 8–15 files       | 2–4 files         |
| Avg tokens per context   | 12,000–20,000    | 2,000–5,000       |
| User explains context    | Always           | Never             |
| get_context() latency    | —                | < 150ms           |

---

## What We Are NOT Building in Phase 1

- No UI
- No cloud sync
- No team sharing
- No fine-tuning pipeline
- No terminal/command watching
- No semantic/embedding search

Start with `pyproject.toml` and work down the Week 1 build order.
Make it work on a real Python project before moving to Week 2.
