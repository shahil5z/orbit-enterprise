-- 003: query-path indexes
CREATE INDEX IF NOT EXISTS ix_transactions_date ON transactions (txn_date);
CREATE INDEX IF NOT EXISTS ix_transactions_customer ON transactions (customer_id);
CREATE INDEX IF NOT EXISTS ix_transactions_region_bu_date ON transactions (region_id, bu_id, txn_date);
CREATE INDEX IF NOT EXISTS ix_customers_region ON customers (region_id);
CREATE INDEX IF NOT EXISTS ix_operations_region_bu_date ON operations (region_id, bu_id, op_date);
CREATE INDEX IF NOT EXISTS ix_incidents_region_opened ON incidents (region_id, opened_at);
CREATE INDEX IF NOT EXISTS ix_metrics_name_month ON metrics (metric_name, period_month);
CREATE INDEX IF NOT EXISTS ix_forecasts_region_month ON forecasts (region_id, target_month);
CREATE INDEX IF NOT EXISTS ix_predictions_model_label ON predictions (model_version, predicted_label);
CREATE INDEX IF NOT EXISTS ix_predictions_entity ON predictions (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS ix_risks_run_level ON risks (run_id, risk_level);
CREATE INDEX IF NOT EXISTS ix_recommendations_run ON recommendations (run_id, priority);
CREATE INDEX IF NOT EXISTS ix_pipeline_runs_started ON pipeline_runs (started_at DESC);
