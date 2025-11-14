# MarketPulse Setup Script for Windows
# PowerShell script to set up the development environment

param(
    [switch]$SkipPython,
    [switch]$SkipNode,
    [switch]$Force
)

Write-Host "MarketPulse Setup Script" -ForegroundColor Green
Write-Host "=========================" -ForegroundColor Green
Write-Host ""

# Check if we're in the right directory
if (-not (Test-Path "requirements-lite.txt") -or -not (Test-Path "marketpulse-client\package.json")) {
    Write-Host "Error: Please run this script from the MarketPulse root directory" -ForegroundColor Red
    exit 1
}

# Function to check if a command exists
function Test-Command($Command) {
    try {
        Get-Command $Command -ErrorAction Stop | Out-Null
        return $true
    }
    catch {
        return $false
    }
}

# Check Python installation
if (-not $SkipPython) {
    Write-Host "Checking Python installation..." -ForegroundColor Yellow
    if (Test-Command "python") {
        $pythonVersion = python --version 2>&1
        Write-Host "✅ Python found: $pythonVersion" -ForegroundColor Green
    } else {
        Write-Host "❌ Python not found. Please install Python 3.8+ from https://python.org" -ForegroundColor Red
        exit 1
    }
}

# Check Node.js installation
if (-not $SkipNode) {
    Write-Host "Checking Node.js installation..." -ForegroundColor Yellow
    if (Test-Command "npm") {
        $nodeVersion = node --version
        Write-Host "✅ Node.js found: $nodeVersion" -ForegroundColor Green
    } else {
        Write-Host "❌ Node.js not found. Please install Node.js from https://nodejs.org" -ForegroundColor Red
        exit 1
    }
}

# Create virtual environment if it doesn't exist
if (-not (Test-Path "venv")) {
    Write-Host "Creating Python virtual environment..." -ForegroundColor Yellow
    python -m venv venv
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Virtual environment created" -ForegroundColor Green
    } else {
        Write-Host "❌ Failed to create virtual environment" -ForegroundColor Red
        exit 1
    }
}

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& .\venv\Scripts\Activate.ps1

# Upgrade pip
Write-Host "Upgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip

# Install Python dependencies
Write-Host "Installing Python dependencies..." -ForegroundColor Yellow
if (Test-Path "requirements.txt") {
    pip install -r requirements.txt
} else {
    pip install -r requirements-lite.txt
}

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Python dependencies installed" -ForegroundColor Green
} else {
    Write-Host "❌ Failed to install Python dependencies" -ForegroundColor Red
    exit 1
}

# Install Node.js dependencies
Write-Host "Installing Node.js dependencies..." -ForegroundColor Yellow
Set-Location marketpulse-client
npm install

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Node.js dependencies installed" -ForegroundColor Green
} else {
    Write-Host "❌ Failed to install Node.js dependencies" -ForegroundColor Red
    Set-Location ..
    exit 1
}

Set-Location ..

# Create necessary directories
Write-Host "Creating necessary directories..." -ForegroundColor Yellow
$directories = @("logs", "data", "config", "scripts")
foreach ($dir in $directories) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "✅ Created $dir directory" -ForegroundColor Green
    }
}

# Create environment file if it doesn't exist
if (-not (Test-Path ".env")) {
    Write-Host "Creating .env file..." -ForegroundColor Yellow
    @"
# MarketPulse Environment Configuration
DATABASE_URL=sqlite:///./marketpulse.db
LOG_LEVEL=INFO
PYTHONPATH=.

# Yahoo Finance (automatically used)
YFINANCE_CACHE_TIMEOUT=300

# Optional: External API Keys
# ALPHA_VANTAGE_API_KEY=your_key_here
# NEWS_API_KEY=your_key_here

# Development Settings
DEBUG=True
RELOAD=True
"@ | Out-File -FilePath ".env" -Encoding UTF8
    Write-Host "✅ .env file created" -ForegroundColor Green
}

Write-Host ""
Write-Host "🎉 Setup completed successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Run '.\scripts\dev.ps1' to start development servers" -ForegroundColor White
Write-Host "2. Or run 'make dev' if you have Make installed" -ForegroundColor White
Write-Host "3. Or run 'docker-compose up' for Docker setup" -ForegroundColor White
Write-Host ""
Write-Host "Access the application at:" -ForegroundColor Cyan
Write-Host "- Frontend: http://localhost:3000" -ForegroundColor White
Write-Host "- Backend API: http://localhost:8000" -ForegroundColor White
Write-Host "- API Docs: http://localhost:8000/docs" -ForegroundColor White