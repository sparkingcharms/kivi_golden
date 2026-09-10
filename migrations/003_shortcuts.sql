-- 003_shortcuts.sql
--
-- Shortcuts are a phrase the person invented, bound to an instruction: say
-- "professorize this" and Kivi applies a definition you wrote in your own
-- words. They are stored as a fourth memory kind rather than in their own
-- table, so scope, promotion, conflict handling, provenance and the event log
-- all apply to them unchanged.
--
-- What they do need is a lookup by trigger phrase. A shortcut is matched
-- before intent classification runs, on every Hey Kivi request, so this is the
-- hottest read in the system.

CREATE INDEX IF NOT EXISTS idx_mem_trigger
    ON memory(kind, status, subject);

-- Two shortcuts whose phrases sound alike are a real product problem: the
-- person says "short version", Kivi fires "shorter version", and the wrong
-- rewrite lands. Collisions are recorded when detected so the interface can
-- surface them and the person can rename one.
CREATE TABLE IF NOT EXISTS shortcut_collision (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         REAL NOT NULL,
    said       TEXT NOT NULL,           -- what was heard
    chosen     TEXT REFERENCES memory(id),
    against    TEXT REFERENCES memory(id),
    margin     REAL NOT NULL,           -- how close the two were
    resolved   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_collision_pair
    ON shortcut_collision(chosen, against);
