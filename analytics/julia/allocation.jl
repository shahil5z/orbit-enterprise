# ORBIT budget and workforce allocation (JuMP + HiGHS, mixed-integer linear program).
#
# Input JSON (written by optimization/workflow.py from forecasts, risk scores and current spend):
#   budget, total_hires, risk_cap_factor, min_region_share, units[] with
#   unit_id, region_id, bu_id, base_spend, return_tier1, return_tier2, risk_score, hire_value, max_hires
# Decision variables per unit: x1 (spend up to base level), x2 (spend above base, lower return), h (integer hires)
# Objective: maximise expected incremental gross margin = sum(r1*x1 + r2*x2 + hire_value*h)
# Constraints: total budget, spend bounds [0.6, 1.6] x base, risk-weighted spend cap, per-region minimum
#              coverage, total hires, per-unit hire caps.
# Baseline: every unit keeps its current spend share of the budget and hires are spread pro rata.
using JuMP, HiGHS, JSON3

function solve(input_path::String, output_path::String)
    cfg = JSON3.read(read(input_path, String))
    units = cfg.units
    n = length(units)
    n == 0 && error("no units in input")
    budget = Float64(cfg.budget)
    base = [Float64(u.base_spend) for u in units]
    r1 = [Float64(u.return_tier1) for u in units]
    r2 = [Float64(u.return_tier2) for u in units]
    risk = [Float64(u.risk_score) for u in units]
    hv = [Float64(u.hire_value) for u in units]
    maxh = [Int(u.max_hires) for u in units]
    regions = unique([String(u.region_id) for u in units])
    base_total = sum(base)
    scaled_base = base .* (budget / base_total)

    m = Model(HiGHS.Optimizer)
    set_silent(m)
    set_attribute(m, "random_seed", 7)
    @variable(m, 0 <= x1[i = 1:n] <= base[i])
    @variable(m, 0 <= x2[i = 1:n] <= 0.6 * base[i])
    @variable(m, 0 <= h[i = 1:n] <= maxh[i], Int)
    @constraint(m, budget_c, sum(x1[i] + x2[i] for i in 1:n) == budget)
    @constraint(m, floor_c[i = 1:n], x1[i] + x2[i] >= 0.6 * base[i])
    avg_risk = sum(risk .* scaled_base) / budget
    @constraint(m, risk_c, sum(risk[i] * (x1[i] + x2[i]) for i in 1:n) <= cfg.risk_cap_factor * avg_risk * budget)
    region_c = Dict{String, Any}()
    for r in regions
        idx = [i for i in 1:n if String(units[i].region_id) == r]
        region_c[r] = @constraint(m, sum(x1[i] + x2[i] for i in idx) >= cfg.min_region_share * sum(scaled_base[i] for i in idx))
    end
    @constraint(m, hires_c, sum(h) == cfg.total_hires)
    @objective(m, Max, sum(r1[i] * x1[i] + r2[i] * x2[i] + hv[i] * h[i] for i in 1:n))
    t0 = time()
    optimize!(m)
    elapsed = time() - t0
    status = string(termination_status(m))

    # baseline objective with identical return curves
    value_spend(i, s) = r1[i] * min(s, base[i]) + r2[i] * max(0.0, min(s - base[i], 0.6 * base[i]))
    base_hires_f = cfg.total_hires .* (maxh ./ sum(maxh))
    base_hires = floor.(Int, base_hires_f)
    rem = cfg.total_hires - sum(base_hires)
    order = sortperm(base_hires_f .- base_hires, rev = true)
    for k in 1:rem
        base_hires[order[k]] += 1
    end
    baseline_obj = sum(value_spend(i, scaled_base[i]) + hv[i] * base_hires[i] for i in 1:n)
    baseline_risk = sum(risk .* scaled_base)

    result = Dict{String, Any}(
        "engine" => "Julia $(VERSION) JuMP $(pkgversion(JuMP)) HiGHS $(pkgversion(HiGHS))",
        "status" => status, "solve_seconds" => elapsed, "budget" => budget, "total_hires" => cfg.total_hires,
        "baseline" => Dict("objective" => baseline_obj, "risk_weighted_spend" => baseline_risk))
    if termination_status(m) == MOI.OPTIMAL
        spend = value.(x1) .+ value.(x2)
        hires = round.(Int, value.(h))
        result["objective"] = objective_value(m)
        result["mip_gap"] = relative_gap(m)
        result["risk_weighted_spend"] = sum(risk .* spend)
        result["improvement_abs"] = objective_value(m) - baseline_obj
        result["improvement_pct"] = (objective_value(m) - baseline_obj) / baseline_obj
        result["allocations"] = [Dict("unit_id" => String(units[i].unit_id), "region_id" => String(units[i].region_id),
            "bu_id" => String(units[i].bu_id), "base_spend" => base[i], "baseline_spend" => scaled_base[i],
            "optimized_spend" => spend[i], "spend_change_pct" => spend[i] / scaled_base[i] - 1,
            "baseline_hires" => base_hires[i], "optimized_hires" => hires[i]) for i in 1:n]
        result["constraints"] = Dict(
            "budget" => Dict("rhs" => budget, "lhs" => sum(spend), "binding" => true),
            "risk_cap" => Dict("rhs" => cfg.risk_cap_factor * avg_risk * budget, "lhs" => sum(risk .* spend),
                               "binding" => abs(sum(risk .* spend) - cfg.risk_cap_factor * avg_risk * budget) < 1e-3 * budget),
            "hires" => Dict("rhs" => cfg.total_hires, "lhs" => sum(hires)),
            "region_minimums" => Dict(r => Dict("rhs" => normalized_rhs(c),
                "lhs" => sum(spend[i] for i in 1:n if String(units[i].region_id) == r)) for (r, c) in region_c))
    end
    open(output_path, "w") do io
        JSON3.pretty(io, result)
    end
    println("JULIA_OPT_STATUS ", status)
end

length(ARGS) < 2 && error("usage: julia allocation.jl <input.json> <output.json>")
solve(ARGS[1], ARGS[2])
