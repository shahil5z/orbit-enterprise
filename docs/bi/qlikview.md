# QlikView

NOT TESTED: QlikView was not available on this laptop.

Load script (Edit Script). Set `vPath` to the absolute `data\bi` folder:

```
SET vPath = 'C:\path\to\orbit-enterprise\data\bi';
SET DateFormat = 'YYYY-MM-DD';

Region:   LOAD region_id, region_name, currency FROM [$(vPath)\dim_region.csv] (txt, utf8, embedded labels, delimiter is ',', msq);
BU:       LOAD bu_id, business_unit_name FROM [$(vPath)\dim_business_unit.csv] (txt, utf8, embedded labels, delimiter is ',', msq);
KPI:      LOAD key AS metric_name, name AS kpi_name, unit, higher_is_better, formula FROM [$(vPath)\dim_kpi.csv] (txt, utf8, embedded labels, delimiter is ',', msq);
Metrics:  LOAD Date#(period_month, 'YYYY-MM-DD') AS period_month, region_id, bu_id, metric_name, value
          FROM [$(vPath)\fact_metrics_monthly.csv] (txt, utf8, embedded labels, delimiter is ',', msq)
          WHERE Len(region_id) > 0;   // drop company-total rows to avoid double counting
Risk:     LOAD entity_type, region_id AS risk_region_id, bu_id AS risk_bu_id, risk_score, risk_level, explanation
          FROM [$(vPath)\fact_risks.csv] (txt, utf8, embedded labels, delimiter is ',', msq);
```

Notes:
- QlikView associates tables on identical field names. That is why the Risk fields are renamed: it avoids a synthetic key between Metrics and Risk on `region_id` + `bu_id`.
- Revenue expression: `Sum({<metric_name={'revenue'}>} value)`.
- Show `risk_level` as a text column in a straight table.
- Add a text object to every sheet: "Simulated enterprise dataset".
