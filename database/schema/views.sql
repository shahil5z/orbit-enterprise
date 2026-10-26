-- Analytical views (re-created on every migrate)
CREATE OR REPLACE VIEW v_latest_run AS
    SELECT run_id FROM pipeline_runs WHERE stage = 'DECISION' AND status LIKE 'SUCCESS%'
    ORDER BY started_at DESC LIMIT 1;

CREATE OR REPLACE VIEW v_region_monthly_revenue AS
    SELECT region_id, date_trunc('month', txn_date)::date AS month, SUM(revenue) AS revenue,
           SUM(revenue - cost) AS gross_margin, COUNT(*) AS txn_count
    FROM transactions GROUP BY region_id, date_trunc('month', txn_date);
