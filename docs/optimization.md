# Optimization

Julia 1.11.7 with JuMP and HiGHS allocates spend and hires across regions, subject to budget, a risk cap, a minimum share per region and a hire total.

MEASURED default run: OPTIMAL. Objective 28.78M vs baseline 26.65M (+2.13M, +7.98%). Solve time 0.04 s.

From the API, a run with budget_multiplier 1.1 and total_hires 30 was OPTIMAL with objective 29.93M vs baseline 27.27M.

The response coefficients are planning assumptions, not estimates from data (INFERRED risk).
