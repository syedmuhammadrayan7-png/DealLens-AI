CREATE TABLE IF NOT EXISTS deallens_schema_migrations (
    version TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS deallens_jobs (
    job_id UUID PRIMARY KEY,
    case_id UUID NOT NULL REFERENCES deallens_cases(case_id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    current_stage TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 2,
    locked_at TIMESTAMPTZ NULL,
    locked_by TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ NULL,
    error_code TEXT NULL,
    error_message TEXT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS deallens_jobs_one_active_per_case ON deallens_jobs(case_id) WHERE status IN ('queued','running','retry_pending');
CREATE INDEX IF NOT EXISTS deallens_jobs_status_idx ON deallens_jobs(status, created_at);
CREATE INDEX IF NOT EXISTS deallens_jobs_case_idx ON deallens_jobs(case_id);
CREATE INDEX IF NOT EXISTS deallens_jobs_locked_idx ON deallens_jobs(locked_at) WHERE status='running';
