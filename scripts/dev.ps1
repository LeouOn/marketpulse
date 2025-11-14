# MarketPulse Development Script for Windows
# PowerShell script to start development servers

param(
    [switch]$BackendOnly,
    [switch]$FrontendOnly,
    [switch]$Docker,
    [switch]$Production
)

Write-Host "MarketPulse Development Environment" -ForegroundColor Green
Write-Host "==================================" -ForegroundColor Green
Write-Host ""

# Function to check if a port is in use
function Test-Port($Port) {
    try {
        $connection = New-Object System.Net.Sockets.TcpClient
        $connection.Connect("localhost", $Port)
        $connection.Close()
        return $true
    }
    catch {
        return $false
    }
}

# Function to stop processes on a port
function Stop-Port($Port) {
    $process = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if ($process) {
        $pid = $process.OwningProcess
        Write-Host "Stopping process on port $Port (PID: $pid)..." -ForegroundColor Yellow
        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }
}

# Check if we're in the right directory
if (-not (Test-Path "requirements.txt") -or -not (Test-Path "marketpulse-client\package.json")) {
    Write-Host "Error: Please run this script from the MarketPulse root directory" -ForegroundColor Red
    exit 1
}

# Docker mode
if ($Docker) {
    Write-Host "Starting with Docker..." -ForegroundColor Yellow

    if ($Production) {
        Write-Host "Starting production services..." -ForegroundColor Cyan
        docker-compose --profile production up
    } else {
        Write-Host "Starting development services..." -ForegroundColor Cyan
        docker-compose up
    }
    exit 0
}

# Check virtual environment
if (Test-Path "venv") {
    Write-Host "Activating virtual environment..." -ForegroundColor Yellow
    & .\venv\Scripts\Activate.ps1
} else {
    Write-Host "Warning: Virtual environment not found. Using system Python." -ForegroundColor Yellow
    Write-Host "Run '.\scripts\setup.ps1' to create virtual environment." -ForegroundColor Yellow
}

# Check if ports are available
if (-not $BackendOnly -and -not $FrontendOnly) {
    if (Test-Port 8000) {
        Write-Host "Port 8000 is already in use. Stopping existing backend..." -ForegroundColor Yellow
        Stop-Port 8000
    }
    if (Test-Port 3000) {
        Write-Host "Port 3000 is already in use. Stopping existing frontend..." -ForegroundColor Yellow
        Stop-Port 3000
    }
}

# Start backend only
if ($BackendOnly) {
    if (Test-Port 8000) {
        Write-Host "Port 8000 is already in use. Stopping existing backend..." -ForegroundColor Yellow
        Stop-Port 8000
    }

    Write-Host "Starting Backend API Server..." -ForegroundColor Cyan
    Write-Host "Backend will be available at: http://localhost:8000" -ForegroundColor White
    Write-Host "API Documentation: http://localhost:8000/docs" -ForegroundColor White
    Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
    Write-Host ""

    python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
    exit 0
}

# Start frontend only
if ($FrontendOnly) {
    if (Test-Port 3000) {
        Write-Host "Port 3000 is already in use. Stopping existing frontend..." -ForegroundColor Yellow
        Stop-Port 3000
    }

    Write-Host "Starting Frontend Development Server..." -ForegroundColor Cyan
    Write-Host "Frontend will be available at: http://localhost:3000" -ForegroundColor White
    Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
    Write-Host ""

    Set-Location marketpulse-client
    npm run dev
    Set-Location ..
    exit 0
}

# Start both backend and frontend
Write-Host "Starting MarketPulse in Development Mode..." -ForegroundColor Cyan
Write-Host ""

# Create jobs for parallel execution
$backendJob = Start-Job -ScriptBlock {
    param($RootPath)
    Set-Location $RootPath
    if (Test-Path "venv") {
        & .\venv\Scripts\Activate.ps1
    }
    Write-Host "Backend starting on http://localhost:8000" -ForegroundColor Green
    python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
} -ArgumentList (Get-Location)

$frontendJob = Start-Job -ScriptBlock {
    param($RootPath)
    Set-Location $RootPath\marketpulse-client
    Write-Host "Frontend starting on http://localhost:3000" -ForegroundColor Green
    npm run dev
} -ArgumentList (Get-Location)

# Wait a moment for services to start
Start-Sleep -Seconds 3

# Check if services started successfully
Write-Host "Checking service status..." -ForegroundColor Yellow

$backendRunning = Test-Port 8000
$frontendRunning = Test-Port 3000

if ($backendRunning) {
    Write-Host "✅ Backend API is running at http://localhost:8000" -ForegroundColor Green
    Write-Host "   API Docs: http://localhost:8000/docs" -ForegroundColor Gray
} else {
    Write-Host "❌ Backend API failed to start" -ForegroundColor Red
}

if ($frontendRunning) {
    Write-Host "✅ Frontend is running at http://localhost:3000" -ForegroundColor Green
} else {
    Write-Host "❌ Frontend failed to start" -ForegroundColor Red
}

Write-Host ""
Write-Host "Press Ctrl+C to stop all services" -ForegroundColor Yellow
Write-Host "Or run '.\scripts\stop.ps1' to stop from another terminal" -ForegroundColor Gray

# Wait for Ctrl+C
try {
    while ($true) {
        Start-Sleep -Seconds 1

        # Check if jobs are still running
        $backendState = Get-Job -Id $backendJob.JobId -State
        $frontendState = Get-Job -Id $frontendJob.JobId -State

        if ($backendState -eq "Failed" -or $frontendState -eq "Failed") {
            Write-Host "One or more services failed. Check logs above." -ForegroundColor Red
            break
        }

        if ($backendState -eq "Completed" -or $frontendState -eq "Completed") {
            Write-Host "One or more services completed unexpectedly." -ForegroundColor Yellow
            break
        }
    }
}
finally {
    Write-Host "Stopping all services..." -ForegroundColor Yellow
    Remove-Job -Id $backendJob.JobId -Force -ErrorAction SilentlyContinue
    Remove-Job -Id $frontendJob.JobId -Force -ErrorAction SilentlyContinue

    # Clean up any remaining processes
    Stop-Port 8000
    Stop-Port 3000

    Write-Host "All services stopped." -ForegroundColor Green
}