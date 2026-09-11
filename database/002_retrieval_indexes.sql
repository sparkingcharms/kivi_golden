-- 002_retrieval_indexes.sql
--
-- Retrieval filters episodes by app and by a time window before scoring, and
-- `active_rules` reads preferences by kind and status on every Hey Kivi
-- request. At 500 records SQLite scans these fast enough that nothing is
-- visible, but both are the hot path and both grow with use, so they get
-- covering indexes now rather than after the first slow demo.

-- Episodes are always filtered by (kind, status) and then ordered or windowed
-- by creation time.
CREATE INDEX IF NOT EXISTS idx_mem_kind_created
    ON memory(kind, status, created_ts);

-- The app filter in retrieve.search().
CREATE INDEX IF NOT EXISTS idx_mem_scope_app
    ON memory(scope_app, kind, status);

-- "Where did this come from" walks back to the originating utterance.
CREATE INDEX IF NOT EXISTS idx_mem_source
    ON memory(source_utt);

-- Trace listing is ordered by recency and filtered by surface.
CREATE INDEX IF NOT EXISTS idx_trace_surface_ts
    ON trace(surface, ts);
