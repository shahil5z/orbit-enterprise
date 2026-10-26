<#
.SYNOPSIS
  Checks that every portable toolchain ORBIT needs is present under .tools and prints its version.
  Toolchains are not downloaded automatically; see docs/technology-rationale.md for sources and exact versions.
#>
$ErrorActionPreference = "Continue"
. (Join-Path $PSScriptRoot "env.ps1")
$T = Join-Path $env:ORBIT_ROOT ".tools"
$checks = [ordered]@{
  "python (venv)"   = { & "$T\venv\Scripts\python.exe" --version }
  "java"            = { (java -version 2>&1 | Select-Object -First 1).ToString() }
  "javac"           = { javac -version 2>&1 }
  "node"            = { node --version }
  "rustc"           = { rustc --version }
  "g++ (w64devkit)" = { (g++ --version | Select-Object -First 1) }
  "R"               = { (Rscript --version 2>&1).ToString() }
  "julia"           = { julia --version }
  "spark"           = { (Get-Item "$env:SPARK_HOME").Name }
  "postgres"        = { postgres --version }
  "git"             = { git --version }
}
$missing = 0
foreach ($k in $checks.Keys) {
  try { $v = & $checks[$k]; if (-not $v) { throw "no output" }; Write-Host ("OK      {0,-16} {1}" -f $k, $v) }
  catch { $missing++; Write-Host ("MISSING {0,-16}" -f $k) }
}
if (-not (Test-Path (Join-Path $env:ORBIT_ROOT ".env"))) { Write-Host "NOTE    .env missing: copy .env.example to .env" }
exit $missing
