# Installs the pinned Julia dependencies into the project-local depot (JULIA_DEPOT_PATH).
using Pkg
Pkg.activate(@__DIR__)
Pkg.add(["JuMP", "HiGHS", "JSON3"])
Pkg.instantiate()
using JuMP, HiGHS, JSON3
println("JULIA_DEPS_OK JuMP=", pkgversion(JuMP), " HiGHS=", pkgversion(HiGHS), " JSON3=", pkgversion(JSON3))
