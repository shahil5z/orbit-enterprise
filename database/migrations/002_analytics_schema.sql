-- 002: analytical, ML and run-tracking tables
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id              VARCHAR(40) NOT NULL,
    stage               VARCHAR(20) NOT NULL,
    component           TEXT NOT NULL,
    status              VARCHAR(24) NOT NULL CHECK (status IN ('RUNNING', 'SUCCESS', 'SUCCESS_WITH_ERRORS', 'FAILED')),
    started_at          TIMESTAMPTZ NOT NULL,
    ended_at            TIMESTAMPTZ,
    duration_s          NUMERIC(12,3),
    records_processed   BIGINT NOT NULL DEFAULT 0,
    error_count         INTEGER NOT NULL DEFAULT 0,
    details             JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, stage)
);
CREATE TABLE IF NOT EXISTS metrics (
    metric_id       BIGSERIAL PRIMARY KEY,
    metric_name     TEXT NOT NULL,
    period_month    DATE NOT NULL,
    region_id       VARCHAR(8) REFERENCES regions(region_id),
    bu_id           VARCHAR(8) REFERENCES business_units(bu_id),
    value           DOUBLE PRECISION,
    run_id          VARCHAR(40) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (metric_name, period_month, region_id, bu_id)
);
CREATE TABLE IF NOT EXISTS data_quality_runs (
    dq_run_id       BIGSERIAL PRIMARY KEY,
    run_id          VARCHAR(40) NOT NULL,
    dataset         TEXT NOT NULL,
    rows_checked    BIGINT NOT NULL,
    quality_score   NUMERIC(6,2) NOT NULL CHECK (quality_score BETWEEN 0 AND 100),
    issue_count     BIGINT NOT NULL,
    issues          JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS model_runs (
    model_version   VARCHAR(80) PRIMARY KEY,
    model_name      TEXT NOT NULL,
    task            TEXT NOT NULL,
    algorithm       TEXT NOT NULL,
    run_id          VARCHAR(40) NOT NULL,
    metrics         JSONB NOT NULL,
    params          JSONB NOT NULL,
    artifact_path   TEXT NOT NULL,
    trained_at      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS forecasts (
    forecast_id     BIGSERIAL PRIMARY KEY,
    model_version   VARCHAR(80) NOT NULL REFERENCES model_runs(model_version),
    region_id       VARCHAR(8) NOT NULL REFERENCES regions(region_id),
    target_month    DATE NOT NULL,
    horizon         SMALLINT NOT NULL CHECK (horizon > 0),
    forecast        NUMERIC(16,2) NOT NULL,
    lower_80        NUMERIC(16,2) NOT NULL,
    upper_80        NUMERIC(16,2) NOT NULL,
    run_id          VARCHAR(40) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (lower_80 <= forecast AND forecast <= upper_80)
);
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id   BIGSERIAL PRIMARY KEY,
    model_version   VARCHAR(80) NOT NULL REFERENCES model_runs(model_version),
    entity_type     TEXT NOT NULL CHECK (entity_type IN ('customer', 'operation')),
    entity_id       VARCHAR(16) NOT NULL,
    score           DOUBLE PRECISION NOT NULL,
    predicted_label SMALLINT NOT NULL,
    actual_label    SMALLINT,
    split           TEXT,
    run_id          VARCHAR(40) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS risks (
    risk_id             BIGSERIAL PRIMARY KEY,
    run_id              VARCHAR(40) NOT NULL,
    entity_type         TEXT NOT NULL CHECK (entity_type IN ('region', 'business_unit')),
    region_id           VARCHAR(8) NOT NULL REFERENCES regions(region_id),
    bu_id               VARCHAR(8) REFERENCES business_units(bu_id),
    risk_score          NUMERIC(6,2) NOT NULL CHECK (risk_score BETWEEN 0 AND 100),
    risk_level          TEXT NOT NULL CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    risk_factors        JSONB NOT NULL,
    confidence          NUMERIC(4,3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    recommended_action  TEXT NOT NULL,
    explanation         TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS optimization_runs (
    optimization_id     VARCHAR(48) PRIMARY KEY,
    run_id              VARCHAR(40) NOT NULL,
    status              TEXT NOT NULL,
    objective           DOUBLE PRECISION,
    baseline_objective  DOUBLE PRECISION NOT NULL,
    improvement_abs     DOUBLE PRECISION,
    improvement_pct     DOUBLE PRECISION,
    parameters          JSONB NOT NULL,
    result              JSONB NOT NULL,
    triggered_by        TEXT NOT NULL CHECK (triggered_by IN ('pipeline', 'api')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS recommendations (
    decision_id     VARCHAR(64) PRIMARY KEY,
    run_id          VARCHAR(40) NOT NULL,
    scope           TEXT NOT NULL CHECK (scope IN ('company', 'region')),
    entity_id       VARCHAR(16) NOT NULL,
    priority        TEXT NOT NULL CHECK (priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    observation     TEXT NOT NULL,
    cause           TEXT NOT NULL,
    forecast        TEXT NOT NULL,
    risk            TEXT NOT NULL,
    recommendation  TEXT NOT NULL,
    expected_impact TEXT NOT NULL,
    confidence      NUMERIC(4,3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    evidence        JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
