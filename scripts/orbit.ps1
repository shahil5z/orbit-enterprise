<#
.SYNOPSIS
  ORBIT // ENTERPRISE developer commands. Everything runs from project-local toolchains in .tools.
.EXAMPLE
  .\scripts\orbit.ps1 setup
  .\scripts\orbit.ps1 pipeline
  .\scripts\orbit.ps1 stage optimize
#>
param(
  [Parameter(Position = 0)]
  [ValidateSet("help", "versions", "install", "setup", "db-start", "db-stop", "migrate", "seed", "pipeline", "stage",
               "train", "test", "dev", "api", "java", "java-test", "web-install", "web-dev", "web-build", "web-preview", "web-test", "e2e", "screenshots", "bi-export", "web-check", "publish-hosted")]
  [string]$Command = "help",
  [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
  [string[]]$Rest
)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "env.ps1")
$Root = $env:ORBIT_ROOT
$T = Join-Path $Root ".tools"
Set-Location $Root

function Invoke-Checked([string]$exe, [string[]]$argv) {
  & $exe @argv
  if ($LASTEXITCODE -ne 0) { throw "$exe exited with code $LASTEXITCODE" }
}

function Get-NpmCli {
  # npm.cmd breaks on the "&" in this path, so npm-cli.js is run with node directly
  Join-Path (Split-Path (Get-Command node).Source) "node_modules\npm\bin\npm-cli.js"
}

function Start-Db {
  $data = Join-Path $T "pgdata"
  & pg_ctl -D $data status *> $null
  if ($LASTEXITCODE -eq 0) { Write-Host "PostgreSQL already running"; return }
  Invoke-Checked "pg_ctl" @("-D", $data, "-o", "-p 55432 -c listen_addresses=localhost", "-l", (Join-Path $T "pg.log"), "-w", "start")
}

function Get-JavaClasses {
  $out = Join-Path $Root "services\java\build\classes"
  $srcs = Get-ChildItem (Join-Path $Root "services\java\src") -Recurse -Filter *.java | ForEach-Object { $_.FullName }
  Invoke-Checked "javac" (@("-d", $out) + $srcs)
  return $out
}

switch ($Command) {
  "help" { Get-Help $PSCommandPath -Detailed; Write-Host "Commands: versions install setup db-start db-stop migrate seed pipeline stage <name...> train test dev api java java-test web-install web-dev web-build web-preview web-test e2e screenshots bi-export web-check publish-hosted" }
  "versions" {
    python --version; java -version 2>&1 | Select-Object -First 1; node --version; rustc --version; g++ --version | Select-Object -First 1
    Rscript --version; julia --version; postgres --version; git --version
  }
  "install" {
    if (-not (Test-Path "$T\venv\Scripts\python.exe")) { Invoke-Checked "python" @("-m", "venv", "$T\venv") }
    Invoke-Checked "$T\venv\Scripts\python.exe" @("-m", "pip", "install", "-r", "requirements-dev.txt")
    Invoke-Checked "julia" @("--project=analytics/julia", "analytics/julia/install.jl")
    Invoke-Checked "Rscript" @("-e", "if (!requireNamespace('jsonlite', quietly=TRUE)) install.packages('jsonlite', lib=Sys.getenv('R_LIBS_USER'), repos='https://cloud.r-project.org')")
    Push-Location apps\web; Invoke-Checked "npm" @("install", "--no-audit", "--no-fund", "--cache", "$T\npm-cache"); Pop-Location
  }
  "setup" {
    if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env"; Write-Host "Created .env from .env.example; set ORBIT_DB_PASSWORD" }
    New-Item -ItemType Directory -Force -Path "apps\web\public" | Out-Null
    Copy-Item "logo.png" "apps\web\public\logo.png" -Force
    Start-Db
    Invoke-Checked "python" @("-c", "from database.db import migrate; print('applied:', migrate())")
  }
  "db-start" { Start-Db }
  "db-stop" { Invoke-Checked "pg_ctl" @("-D", (Join-Path $T "pgdata"), "stop") }
  "migrate" { Invoke-Checked "python" @("-c", "from database.db import migrate; print('applied:', migrate())") }
  "publish-hosted" { Start-Db; Invoke-Checked "python" @("-m", "database.seeds.publish") }
  "seed" { Start-Db; Invoke-Checked "python" @("-m", "pipelines.orchestrator", "publish") }
  "pipeline" { Start-Db; Invoke-Checked "python" (@("-m", "pipelines.orchestrator", "all") + $Rest) }
  "stage" { if (-not $Rest) { throw "usage: orbit.ps1 stage <ingest|validate|transform|curate|analyze|train|predict|risk|optimize|decision|publish> [...]" }
            Invoke-Checked "python" (@("-m", "pipelines.orchestrator") + $Rest) }
  "train" { Invoke-Checked "python" @("-m", "pipelines.orchestrator", "train", "predict") }
  "test" { Start-Db; Invoke-Checked "python" (@("-m", "pytest", "-p", "no:cacheprovider", "tests") + $Rest) }
  { $_ -in "dev", "api" } { Start-Db; Invoke-Checked "python" @("-m", "uvicorn", "apps.api.orbit_api.main:app", "--host", "127.0.0.1", "--port", "8000") }
  "java" { $cp = Get-JavaClasses; Invoke-Checked "java" @("-Dorbit.root=$Root", "-cp", $cp, "com.orbit.integration.IntegrationServer") }
  "java-test" { $cp = Get-JavaClasses; Invoke-Checked "java" @("-cp", $cp, "com.orbit.integration.SelfTest") }
  "web-install" {
    $env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $T "ms-playwright"
    Push-Location apps\web
    try {
      Invoke-Checked "node" @((Get-NpmCli), "install", "--cache", (Join-Path $T "npm-cache"), "--no-audit", "--no-fund")
      Invoke-Checked "node" @("node_modules\@playwright\test\cli.js", "install", "chromium")
    } finally { Pop-Location }
  }
  "web-dev" { Push-Location apps\web; try { Invoke-Checked "node" @("node_modules\vite\bin\vite.js", "--host", "127.0.0.1") } finally { Pop-Location } }
  "web-build" { Push-Location apps\web; try { Invoke-Checked "node" @("node_modules\typescript\bin\tsc", "--noEmit"); Invoke-Checked "node" @("node_modules\vite\bin\vite.js", "build") } finally { Pop-Location } }
  "web-preview" { Push-Location apps\web; try { Invoke-Checked "node" @("node_modules\vite\bin\vite.js", "preview", "--host", "127.0.0.1", "--port", "4173", "--strictPort") } finally { Pop-Location } }
  "web-test" {
    Push-Location apps\web
    try {
      Invoke-Checked "node" @("node_modules\eslint\bin\eslint.js", "src", "e2e")
      Invoke-Checked "node" @("node_modules\typescript\bin\tsc", "--noEmit")
      Invoke-Checked "node" @("node_modules\vitest\vitest.mjs", "run")
    } finally { Pop-Location }
  }
  "e2e" {
    # needs the API (orbit.ps1 api) and a built preview (web-build, then web-preview) running
    $env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $T "ms-playwright"
    Push-Location apps\web; try { Invoke-Checked "node" (@("node_modules\@playwright\test\cli.js", "test", "--project=desktop", "--project=laptop", "--project=tablet") + $Rest) } finally { Pop-Location }
  }
  "screenshots" {
    $env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $T "ms-playwright"
    $env:ORBIT_SCREENSHOT_DIR = Join-Path $Root "docs\screenshots"
    Push-Location apps\web; try { Invoke-Checked "node" @("node_modules\@playwright\test\cli.js", "test", "--project=screenshots") } finally { Pop-Location }
  }
  "bi-export" { Start-Db; Invoke-Checked "python" (@("-m", "bi.export") + $Rest) }
  "web-check" {
    # node is called directly: .cmd shims (npx) break on the "&" in this project path
    Push-Location apps\web; Invoke-Checked "node" @("node_modules\typescript\bin\tsc", "--noEmit"); Pop-Location
  }
}
