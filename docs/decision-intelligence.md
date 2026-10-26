# Decision intelligence

Risk score per region is a weighted sum of factors (weight, reference, description). MEASURED:
- R01 51.0 HIGH
- R02 51.14 HIGH
- R03 40.27 MEDIUM
- R04 58.39 HIGH
- R05 35.53 MEDIUM
- R06 40.6 MEDIUM

Confidence is 0.854 for every region.

C++ Monte Carlo, 200k simulations, 0.67 s: expected revenue 714.76M, P5 665.17M, P95 767.22M, VaR95 49.59M, CVaR95 60.95M.

The decision engine produced 7 recommendations. Each one carries evidence references to data/outputs files. No LLM is used.
