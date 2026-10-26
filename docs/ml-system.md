# ML system

All metrics are MEASURED on holdout data from the simulated datasets.
- Revenue forecast (per region): test MAPE 9.00% vs seasonal naive 15.33%. Intervals use the residual log standard deviation.
- Churn classifier: ROC AUC 0.909, PR AUC 0.721, precision 0.781, recall 0.532, F1 0.633.
- Operations anomaly (Isolation Forest): precision 0.619, recall 0.963, F1 0.754, ROC AUC 0.999.
- Customer segmentation: KMeans with k=4.
- Rust batch scoring on 32,880 rows: max difference vs Python 5.5e-7. Median wall time 0.095 s vs 2.27 s for Python, about 24x on the latest benchmark (30x on an earlier one). This counts process start and CSV I/O.
- R 4.6.1: ANOVA p = 4.2e-51 and regression R^2 = 0.928. The R^2 is high because the simulated data is built that way.

Artifacts are versioned in ml/artifacts and registered in model_runs.
