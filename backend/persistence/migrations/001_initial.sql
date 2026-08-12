CREATE TABLE IF NOT EXISTS deallens_cases (
    case_id UUID PRIMARY KEY,
    parent_case_id UUID NULL REFERENCES deallens_cases(case_id),
    company_name TEXT NOT NULL,
    website TEXT NULL,
    industry TEXT NOT NULL,
    funding_stage TEXT NOT NULL,
    funding_requested DOUBLE PRECISION NULL,
    github_url TEXT NULL,
    monthly_revenue DOUBLE PRECISION NULL,
    monthly_burn DOUBLE PRECISION NULL,
    cash_available DOUBLE PRECISION NULL,
    customers INTEGER NULL,
    previous_monthly_revenue DOUBLE PRECISION NULL,
    largest_customer_revenue DOUBLE PRECISION NULL,
    pitch_deck_filename TEXT NULL,
    pitch_deck_extracted BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL,
    current_stage TEXT NOT NULL,
    agent_status JSONB NOT NULL DEFAULT '{}'::jsonb,
    completed_stages JSONB NOT NULL DEFAULT '[]'::jsonb,
    completion_percentage INTEGER NOT NULL DEFAULT 0,
    evidence_count INTEGER NOT NULL DEFAULT 0,
    error_code TEXT NULL,
    error_message TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ NULL
);
CREATE INDEX IF NOT EXISTS deallens_cases_created_idx ON deallens_cases(created_at DESC);
CREATE INDEX IF NOT EXISTS deallens_cases_status_idx ON deallens_cases(status);

CREATE TABLE IF NOT EXISTS deallens_reports (
    report_id UUID PRIMARY KEY,
    case_id UUID NOT NULL UNIQUE REFERENCES deallens_cases(case_id) ON DELETE CASCADE,
    overall_score INTEGER NOT NULL,
    market_score INTEGER NOT NULL,
    technical_score INTEGER NOT NULL,
    traction_score INTEGER NOT NULL,
    financial_score INTEGER NOT NULL,
    team_score INTEGER NOT NULL,
    risk_level TEXT NOT NULL,
    confidence_level TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    recommendation_reason TEXT NOT NULL DEFAULT '',
    investment_thesis TEXT NOT NULL,
    report_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS deallens_score_breakdowns (
    id UUID PRIMARY KEY,
    report_id UUID NOT NULL REFERENCES deallens_reports(report_id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    score INTEGER NOT NULL,
    confidence TEXT NOT NULL,
    factors JSONB NOT NULL,
    deductions JSONB NOT NULL,
    evidence_notes JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS deallens_evidence (
    id UUID PRIMARY KEY,
    report_id UUID NOT NULL REFERENCES deallens_reports(report_id) ON DELETE CASCADE,
    statement TEXT NOT NULL, status TEXT NOT NULL, source_type TEXT NULL, source_name TEXT NULL,
    source_url TEXT NULL, confidence INTEGER NOT NULL, observed_at TIMESTAMPTZ NULL, notes TEXT NULL
);
CREATE TABLE IF NOT EXISTS deallens_report_lists (
    id UUID PRIMARY KEY,
    report_id UUID NOT NULL REFERENCES deallens_reports(report_id) ON DELETE CASCADE,
    list_type TEXT NOT NULL, content TEXT NOT NULL, ordering INTEGER NOT NULL
);
