-- 001_initial.sql
-- The whole schema at first release: utterances, the memory store, its event
-- log, and the per-request decision trace.

-- Raw dictation events. The corpus loads into here.
CREATE TABLE IF NOT EXISTS utterance (
    id            TEXT PRIMARY KEY,
    ts            REAL NOT NULL,
    app           TEXT NOT NULL,
    surface       TEXT NOT NULL,
    raw_asr       TEXT NOT NULL,
    formatted     TEXT NOT NULL,
    languages     TEXT NOT NULL,
    private       INTEGER NOT NULL DEFAULT 0,
    meta          TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_utt_ts  ON utterance(ts);
CREATE INDEX IF NOT EXISTS idx_utt_app ON utterance(app);

CREATE TABLE IF NOT EXISTS memory (
    id            TEXT PRIMARY KEY,
    kind          TEXT NOT NULL,
    subject       TEXT NOT NULL,
    body          TEXT NOT NULL,
    payload       TEXT NOT NULL DEFAULT '{}',
    status        TEXT NOT NULL,
    confidence    REAL NOT NULL,
    observations  INTEGER NOT NULL DEFAULT 1,
    scope_app     TEXT,
    created_ts    REAL NOT NULL,
    updated_ts    REAL NOT NULL,
    last_used_ts  REAL,
    use_count     INTEGER NOT NULL DEFAULT 0,
    source_utt    TEXT REFERENCES utterance(id),
    origin        TEXT NOT NULL,
    reason        TEXT NOT NULL DEFAULT '',
    superseded_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_mem_kind   ON memory(kind, status);
CREATE INDEX IF NOT EXISTS idx_mem_subject ON memory(subject);

CREATE TABLE IF NOT EXISTS memory_event (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id  TEXT NOT NULL REFERENCES memory(id),
    ts         REAL NOT NULL,
    event      TEXT NOT NULL,
    detail     TEXT NOT NULL DEFAULT '',
    utt_id     TEXT
);
CREATE INDEX IF NOT EXISTS idx_ev_mem ON memory_event(memory_id);

CREATE TABLE IF NOT EXISTS trace (
    id           TEXT PRIMARY KEY,
    ts           REAL NOT NULL,
    surface      TEXT NOT NULL,
    request      TEXT NOT NULL,
    app          TEXT,
    intent       TEXT,
    intent_conf  REAL,
    outcome      TEXT,
    latency_ms   REAL,
    model_calls  INTEGER NOT NULL DEFAULT 0,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd     REAL NOT NULL DEFAULT 0.0
);
CREATE INDEX IF NOT EXISTS idx_trace_ts ON trace(ts);

CREATE TABLE IF NOT EXISTS trace_step (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL REFERENCES trace(id),
    seq      INTEGER NOT NULL,
    stage    TEXT NOT NULL,
    detail   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_step_trace ON trace_step(trace_id);
