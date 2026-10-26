# Activates the project-local toolchains in the current PowerShell session (no system changes).
$Root = Split-Path -Parent $PSScriptRoot
$T = Join-Path $Root ".tools"
$env:ORBIT_ROOT = $Root
$env:RUSTUP_HOME = "$T\rustup"; $env:CARGO_HOME = "$T\cargo"
$env:JULIA_DEPOT_PATH = "$T\julia-depot"
$env:R_LIBS_USER = "$T\R-library"
$env:HADOOP_HOME = "$T\hadoop"
$env:SPARK_HOME = "$T\spark-4.0.4-bin-hadoop3"
$env:COURSIER_CACHE = "$T\coursier-cache"
$env:PYSPARK_PYTHON = "$T\venv\Scripts\python.exe"
$paths = @("$T\node", "$T\cargo\bin", "$T\w64devkit\bin", "$T\R\bin", "$T\julia-1.11.7\bin", "$T\pgsql\bin", "$T\hadoop\bin", "$env:SPARK_HOME\bin", "$T\venv\Scripts")
foreach ($p in $paths) { if ((Test-Path $p) -and (($env:PATH -split ';') -notcontains $p)) { $env:PATH = "$p;$env:PATH" } }
