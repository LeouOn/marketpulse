# MarketPulse local stack for Windows.
# Starts: Postgres+Redis (if Docker is up) OR SQLite fallback, then API + Next.js.
#
#   .\scripts\dev.ps1
#   .\scripts\dev.ps1 -BackendOnly
#   .\scripts\dev.ps1 -FrontendOnly
#   .\scripts\dev.ps1 -Docker          # full compose (api+frontend+db in containers)

param(
    [switch]$BackendOnly,
    [switch]$FrontendOnly,
    [switch]$Docker,
    [switch]$Production
)

$ErrorActionPreference = "Continue"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

function Test-Port([int]$Port) {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $c.Connect("127.0.0.1", $Port)
        $c.Close()
        return $true
    } catch {
        return $false
    }
}

function Stop-Port([int]$Port) {
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        Write-Host "  stopping PID $($c.OwningProcess) on port $Port"
        Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
    }
}

function Wait-Http([string]$Url, [int]$Seconds = 40) {
    for ($i = 0; $i -lt $Seconds; $i++) {
        try {
            $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 400) { return $true }
        } catch { }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Test-Docker {
    try {
        docker info 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

if (-not (Test-Path "requirements.txt") -or -not (Test-Path "marketpulse-client\package.json")) {
    Write-Host "Run this from the MarketPulse repo root." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "MarketPulse dev stack" -ForegroundColor Green
Write-Host "=====================" -ForegroundColor Green
Write-Host ""

if ($Docker) {
    if ($Production) {
        docker compose --profile production up
    } else {
        docker compose up
    }
    exit $LASTEXITCODE
}

$python = "python"
if (Test-Path "venv\Scripts\python.exe") {
    $python = (Resolve-Path "venv\Scripts\python.exe").Path
    Write-Host "[ok] python: venv" -ForegroundColor Green
} else {
    Write-Host "[ok] python: system ($python)" -ForegroundColor Yellow
}

# Infra: docker postgres/redis, else sqlite so uvicorn does not hang.
$dbUrl = $null
if (-not $FrontendOnly) {
    if (Test-Docker) {
        Write-Host "[start] docker compose postgres + redis" -ForegroundColor Cyan
        docker compose up -d postgres redis
        $ready = $false
        for ($i = 0; $i -lt 40; $i++) {
            if (Test-Port 5433) { $ready = $true; break }
            Start-Sleep -Seconds 1
        }
        if ($ready) {
            Write-Host "[ok] Postgres on :5433  Redis on :6379" -ForegroundColor Green
        } else {
            Write-Host "[warn] Docker up but Postgres not listening on 5433; using SQLite" -ForegroundColor Yellow
            $dbUrl = "sqlite:///./marketpulse.db"
        }
    } else {
        Write-Host "[warn] Docker not running - API will use SQLite (marketpulse.db)" -ForegroundColor Yellow
        $dbUrl = "sqlite:///./marketpulse.db"
    }
}

if (-not $FrontendOnly) {
    if (Test-Port 8000) { Stop-Port 8000; Start-Sleep -Seconds 1 }
}
if (-not $BackendOnly) {
    if (Test-Port 3000) { Stop-Port 3000; Start-Sleep -Seconds 1 }
}

if ($BackendOnly) {
    if ($dbUrl) { $env:DATABASE_URL = $dbUrl }
    Write-Host "Backend  http://localhost:8000   (Ctrl+C to stop)" -ForegroundColor Cyan
    & $python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload
    exit $LASTEXITCODE
}

if ($FrontendOnly) {
    Write-Host "Frontend http://localhost:3000   (Ctrl+C to stop)" -ForegroundColor Cyan
    Set-Location (Join-Path $Root "marketpulse-client")
    npm run dev
    exit $LASTEXITCODE
}

# Two extra windows so logs stay visible; this script waits then prints URLs.
$dbLine = ""
if ($dbUrl) { $dbLine = "`$env:DATABASE_URL = '$dbUrl'; " }

$backendCmd = "${dbLine}& '$python' -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload"
$frontendDir = Join-Path $Root "marketpulse-client"

Write-Host "[start] backend window" -ForegroundColor Cyan
Start-Process -FilePath "powershell.exe" -WorkingDirectory $Root -ArgumentList @("-NoExit", "-NoProfile", "-Command", $backendCmd)

if (-not (Test-Path "marketpulse-client\node_modules")) {
    Write-Host "[install] npm install" -ForegroundColor Yellow
    Push-Location "marketpulse-client"
    npm install
    Pop-Location
}

Write-Host "[start] frontend window" -ForegroundColor Cyan
Start-Process -FilePath "powershell.exe" -WorkingDirectory $frontendDir -ArgumentList @("-NoExit", "-NoProfile", "-Command", "npm run dev")

Write-Host "[wait] backend /docs ..." -ForegroundColor Yellow
$be = Wait-Http "http://127.0.0.1:8000/docs" 45
if ($be) { Write-Host "[ok] API  http://localhost:8000  (docs: /docs)" -ForegroundColor Green }
else { Write-Host "[warn] API did not answer /docs in 45s — check the backend window" -ForegroundColor Yellow }

Write-Host "[wait] frontend / ..." -ForegroundColor Yellow
$fe = Wait-Http "http://localhost:3000/" 45
if ($fe) { Write-Host "[ok] UI   http://localhost:3000" -ForegroundColor Green }
else { Write-Host "[wait] UI still starting — open http://localhost:3000 shortly" -ForegroundColor Yellow }

Write-Host ""
Write-Host "Dashboard:  http://localhost:3000"
Write-Host "API:        http://localhost:8000/docs"
Write-Host "Stop:       .\stop-dev.bat   (or close the two windows)"
Write-Host ""
