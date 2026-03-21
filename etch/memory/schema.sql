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
    files_changed   TEXT,
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
    files_touched   TEXT,
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
