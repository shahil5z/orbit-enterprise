"""Central KPI governance catalogue. The API serves it at /api/v1/kpis and the UI reads labels,
formulas, units and direction from it, so every screen and BI extract uses one definition per KPI."""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class KPI:
    key: str
    name: str
    definition: str
    formula: str
    source: str
    refresh: str
    dimensions: tuple[str, ...]
    unit: str  # currency | percent | count | hours | score | ratio
    higher_is_better: bool
    meaning: str


_PIPE = "each pipeline run (scripts/orbit.ps1 pipeline)"
_RB = ("month", "region", "business_unit")

CATALOGUE: tuple[KPI, ...] = (
    KPI("revenue", "Revenue", "Net invoiced revenue after discounts.", "sum(quantity * unit_price * (1 - discount_pct))",
        "transactions -> metrics.revenue", _PIPE, _RB + ("segment", "product", "channel"), "currency", True,
        "Top-line demand captured. Compare with prior period and forecast."),
    KPI("gross_margin", "Gross margin", "Revenue minus direct cost of goods.", "sum(revenue) - sum(cost)",
        "transactions -> metrics.gross_margin", _PIPE, _RB, "currency", True, "Value retained before operating expense."),
    KPI("gross_margin_pct", "Gross margin %", "Gross margin as a share of revenue.", "gross_margin / revenue",
        "metrics", _PIPE, _RB, "percent", True, "Pricing power and cost of delivery."),
    KPI("opex", "Operating expense", "Operating cost including marketing.", "sum(operations.opex)",
        "operations -> metrics.opex", _PIPE, _RB, "currency", False, "Cost base. Rising opex without revenue is a warning."),
    KPI("operating_profit", "Operating profit", "Gross margin less operating expense.", "gross_margin - opex",
        "metrics.operating_profit", _PIPE, _RB, "currency", True, "Core profitability."),
    KPI("operating_margin_pct", "Operating margin %", "Operating profit as a share of revenue.",
        "operating_profit / revenue", "metrics", _PIPE, _RB, "percent", True, "Efficiency of converting revenue to profit."),
    KPI("revenue_growth", "Revenue growth", "Change versus the comparison period.",
        "revenue(period) / revenue(comparison period) - 1", "metrics", _PIPE, _RB, "percent", True,
        "Momentum. Negative values flag decline."),
    KPI("txn_count", "Transactions", "Count of invoiced transactions.", "count(transaction_id)", "transactions", _PIPE,
        _RB + ("segment", "product"), "count", True, "Volume of commercial activity."),
    KPI("active_customers", "Active customers", "Distinct customers with at least one transaction.",
        "count(distinct customer_id)", "transactions -> metrics.active_customers", _PIPE, _RB, "count", True,
        "Breadth of the customer base."),
    KPI("marketing_spend", "Marketing spend", "Demand generation spend.", "sum(operations.marketing_spend)",
        "operations -> metrics.marketing_spend", _PIPE, _RB, "currency", False,
        "Main lever in the optimization model."),
    KPI("avg_uptime_pct", "Uptime %", "Average daily service availability.", "avg(operations.uptime_pct)",
        "operations -> metrics.avg_uptime_pct", _PIPE, _RB, "percent", True, "Service reliability. Target 99.5%."),
    KPI("incident_count", "Incidents", "Operational incidents opened.", "count(incident_id)", "incidents", _PIPE,
        _RB + ("severity", "category"), "count", False, "Operational stability."),
    KPI("incident_cost", "Incident cost", "Cost impact of incidents.", "sum(incidents.cost_impact)", "incidents", _PIPE,
        _RB + ("severity", "category"), "currency", False, "Financial cost of instability."),
    KPI("mttr_hours", "Mean time to resolve", "Average hours from open to resolve, resolved incidents only.",
        "avg(resolved_at - opened_at) in hours", "incidents", _PIPE, ("month", "region", "severity", "category"), "hours",
        False, "Responsiveness of operations."),
    KPI("orders_per_head", "Orders per head", "Orders processed per unit of headcount.",
        "sum(orders_processed) / avg(headcount)", "operations", _PIPE, _RB, "ratio", True, "Workload and productivity."),
    KPI("fulfillment_hours", "Fulfillment hours", "Average hours to fulfil an order.", "avg(fulfillment_hours)",
        "operations", _PIPE, _RB, "hours", False, "Speed of delivery. High values indicate a bottleneck."),
    KPI("churn_rate", "Predicted churn rate", "Share of customers predicted to churn by the churn classifier.",
        "count(predicted_label = 1) / count(customers)", "predictions (churn_classifier)", _PIPE,
        ("region", "segment"), "percent", False, "Revenue retention risk."),
    KPI("forecast_mape", "Forecast MAPE", "Mean absolute percentage error of the revenue forecast on the test window.",
        "mean(|actual - forecast| / actual)", "model_runs (revenue_forecast)", _PIPE, ("region",), "percent", False,
        "Trust level of forward-looking numbers."),
    KPI("quality_score", "Data quality score", "Weighted score across completeness, uniqueness, validity, consistency, "
        "referential integrity and schema checks.", "100 * sum(weight * (1 - min(10 * issue_rate, 1)))",
        "data_quality_runs", _PIPE, ("dataset",), "score", True, "Pipeline blocks below 80."),
    KPI("risk_score", "Risk score", "Weighted sum of normalized risk factors (0 to 100).", "100 * sum(weight * normalized)",
        "risks", _PIPE, ("region", "business_unit"), "score", False, "Levels: LOW < 25, MEDIUM < 50, HIGH < 70, CRITICAL >= 70."),
    KPI("var95", "Revenue VaR 95%", "Shortfall of the 5th percentile simulated revenue versus expected, 6 months.",
        "expected - p5", "C++ Monte Carlo (revenue_at_risk.json)", _PIPE, ("region",), "currency", False,
        "Downside exposure in a bad but plausible case."),
    KPI("cvar95", "Revenue CVaR 95%", "Average shortfall in the worst 5% of simulations, 6 months.",
        "expected - mean(revenue | revenue <= p5)", "C++ Monte Carlo", _PIPE, ("region",), "currency", False,
        "Tail exposure for downside planning."),
)

BY_KEY = {k.key: k for k in CATALOGUE}


def catalogue() -> list[dict]:
    return [asdict(k) for k in CATALOGUE]
