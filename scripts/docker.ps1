# MarketPulse Docker Management Script for Windows
# PowerShell script to manage Docker containers

param(
    [string]$Action = "up",
    [switch]$Production,
    [switch]$Full,
    [switch]$Build,
    [switch]$Logs,
    [switch]$Clean
)

Write-Host "MarketPulse Docker Management" -ForegroundColor Green
Write-Host "===========================" -ForegroundColor Green
Write-Host ""

# Check if Docker is available
function Test-Docker {
    try {
        docker version >$null 2>&1
        docker-compose version >$null 2>&1
        return $true
    }
    catch {
        return $false
    }
}

if (-not (Test-Docker)) {
    Write-Host "❌ Docker or Docker Compose not found. Please install Docker Desktop." -ForegroundColor Red
    exit 1
}

Write-Host "✅ Docker environment detected" -ForegroundColor Green

# Check if we're in the right directory
if (-not (Test-Path "docker-compose.yml")) {
    Write-Host "Error: Please run this script from the MarketPulse root directory" -ForegroundColor Red
    exit 1
}

# Build images
if ($Build) {
    Write-Host "Building Docker images..." -ForegroundColor Yellow
    docker-compose build
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Docker images built successfully" -ForegroundColor Green
    } else {
        Write-Host "❌ Failed to build Docker images" -ForegroundColor Red
        exit 1
    }
    exit 0
}

# Clean Docker resources
if ($Clean) {
    Write-Host "Cleaning Docker resources..." -ForegroundColor Yellow

    Write-Host "Stopping and removing containers..." -ForegroundColor Gray
    docker-compose down -v 2>$null

    Write-Host "Removing images..." -ForegroundColor Gray
    docker rmi marketpulse-api 2>$null
    docker rmi marketpulse-frontend 2>$null

    Write-Host "Cleaning unused Docker resources..." -ForegroundColor Gray
    docker system prune -f

    Write-Host "✅ Docker cleanup completed" -ForegroundColor Green
    exit 0
}

# Show logs
if ($Logs) {
    Write-Host "Showing Docker logs..." -ForegroundColor Yellow
    Write-Host "Press Ctrl+C to exit logs" -ForegroundColor Gray
    docker-compose logs -f
    exit 0
}

# Main actions
switch ($Action.ToLower()) {
    "up" {
        Write-Host "Starting Docker services..." -ForegroundColor Yellow

        if ($Production) {
            Write-Host "Starting production stack..." -ForegroundColor Cyan
            docker-compose --profile production up -d
        } elseif ($Full) {
            Write-Host "Starting full stack (including database and cache)..." -ForegroundColor Cyan
            docker-compose --profile full up -d
        } else {
            Write-Host "Starting development stack..." -ForegroundColor Cyan
            docker-compose up -d
        }

        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ Services started successfully" -ForegroundColor Green
            Write-Host ""
            Write-Host "Services:" -ForegroundColor White
            Write-Host "- Backend API: http://localhost:8000" -ForegroundColor Gray
            Write-Host "- Frontend: http://localhost:3000" -ForegroundColor Gray
            Write-Host "- API Docs: http://localhost:8000/docs" -ForegroundColor Gray

            if ($Production -or $Full) {
                Write-Host "- PostgreSQL: localhost:5433" -ForegroundColor Gray
                Write-Host "- Redis: localhost:6379" -ForegroundColor Gray
            }

            Write-Host ""
            Write-Host "Run '.\scripts\docker.ps1 -Logs' to see logs" -ForegroundColor Cyan
            Write-Host "Run '.\scripts\docker.ps1 -Action down' to stop services" -ForegroundColor Cyan
        } else {
            Write-Host "❌ Failed to start services" -ForegroundColor Red
            exit 1
        }
    }

    "down" {
        Write-Host "Stopping Docker services..." -ForegroundColor Yellow
        docker-compose down

        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ Services stopped successfully" -ForegroundColor Green
        } else {
            Write-Host "❌ Failed to stop services" -ForegroundColor Red
            exit 1
        }
    }

    "restart" {
        Write-Host "Restarting Docker services..." -ForegroundColor Yellow
        docker-compose restart

        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ Services restarted successfully" -ForegroundColor Green
        } else {
            Write-Host "❌ Failed to restart services" -ForegroundColor Red
            exit 1
        }
    }

    "status" {
        Write-Host "Docker service status:" -ForegroundColor Yellow
        docker-compose ps
    }

    default {
        Write-Host "Unknown action: $Action" -ForegroundColor Red
        Write-Host "Available actions: up, down, restart, status" -ForegroundColor Gray
        Write-Host "Or use flags: -Production, -Full, -Build, -Logs, -Clean" -ForegroundColor Gray
        exit 1
    }
}