-- 002_retrieval_indexes.sql
-- Retrieval indexes for the memory hot path.

CREATE INDEX IF NOT EXISTS idx_mem_kind_created
    ON memory(kind, status, created_ts);

CREATE INDEX IF NOT EXISTS idx_mem_scope_app
    ON memory(scope_app, kind, status);

CREATE INDEX IF NOT EXISTS idx_mem_source
    ON memory(source_utt);

CREATE INDEX IF NOT EXISTS idx_trace_surface_ts
    ON trace(surface, ts);
