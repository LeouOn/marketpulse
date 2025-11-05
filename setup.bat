REM MarketPulse Windows Setup Script
REM Sets up the development environment for MarketPulse on Windows

@echo off
echo 🚀 Setting up MarketPulse development environment...
echo ==================================================

REM Check if Docker is installed
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Docker is not installed. Please install Docker Desktop first.
    pause
    exit /b 1
)

docker-compose --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Docker Compose is not installed. Please install Docker Desktop with Compose support.
    pause
    exit /b 1
)

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python is not installed. Please install Python 3.8+ first.
    pause
    exit /b 1
)

REM Check Python version
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set "py_version=%%i"
echo Python version: %py_version%

REM Extract major and minor versions
set "major=%py_version:~0,1%"
for /f "tokens=2 delims=." %%a in ("%py_version%") do set "minor=%%a"

REM Version comparison: require major=3 and minor>=8
if not "%major%"=="3" (
    echo ❌ Python major version %major% not supported. MarketPulse requires Python 3.8+.
    echo Please install Python 3.8 or higher.
    pause
    exit /b 1
)
if %minor% LSS 8 (
    echo ❌ Python version 3.%minor% detected. MarketPulse requires Python 3.8 or higher.
    echo Please upgrade Python or use pyenv/conda to manage versions.
    pause
    exit /b 1
)
echo ✅ Python %py_version% detected (compatible)

REM Create virtual environment
echo 📦 Creating Python virtual environment...
if not exist venv (
    python -m venv venv
    echo ✅ Virtual environment created
) else (
    echo ℹ️ Virtual environment already exists
)

REM Activate virtual environment
echo 🔧 Activating virtual environment...
call venv\Scripts\activate.bat

REM Upgrade pip
echo ⬆️ Upgrading pip...
python -m pip install --upgrade pip

REM Install Python dependencies
echo 📦 Installing Python dependencies...
pip install -r requirements.txt

REM Create environment file
echo ⚙️ Creating environment configuration...
if not exist .env (
    echo # MarketPulse Environment Configuration > .env
    echo # Copy your API keys from config\credentials.example.yaml to this file >> .env
    echo. >> .env
    echo # Database (auto-configured by Docker) >> .env
    echo DATABASE_URL=postgresql://marketpulse:marketpulse_password@localhost:5432/marketpulse >> .env
    echo. >> .env
    echo # API Keys (replace with your actual keys) >> .env
    echo ALPACA_KEY_ID=your_alpaca_key_here >> .env
    echo ALPACA_SECRET_KEY=your_alpaca_secret_here >> .env
    echo ALPACA_BASE_URL=https://paper-api.alpaca.markets >> .env
    echo. >> .env
    echo RITHMIC_USERNAME=your_rithmic_username >> .env
    echo RITHMIC_PASSWORD=your_rithmic_password >> .env
    echo. >> .env
    echo COINBASE_API_KEY=your_coinbase_api_key >> .env
    echo COINBASE_API_SECRET=your_coinbase_secret >> .env
    echo COINBASE_PASSPHRASE=your_coinbase_passphrase >> .env
    echo. >> .env
    echo OPENROUTER_API_KEY=your_openrouter_api_key >> .env
    echo. >> .env
    echo # Logging >> .env
    echo LOG_LEVEL=INFO >> .env
    echo ✅ Environment file created (.env)
) else (
    echo ℹ️ Environment file already exists
)

REM Create __init__.py files for existing package structure
echo 📁 Creating Python package structure...
if not exist src\__init__.py (
    echo. > src\__init__.py
)
if not exist src\core\__init__.py (
    echo. > src\core\__init__.py
)
if not exist src\api\__init__.py (
    echo. > src\api\__init__.py
)
if not exist src\data\__init__.py (
    echo. > src\data\__init__.py
)
if not exist src\llm\__init__.py (
    echo. > src\llm\__init__.py
)

echo ✅ Package structure created

REM Start database
echo 🐘 Starting PostgreSQL database...
docker-compose up -d postgres

REM Wait for database to be ready
echo ⏳ Waiting for database to be ready...
timeout /t 10 /nobreak >nul

echo ✅ Database should be ready!

echo.
echo 🎉 MarketPulse setup completed successfully!
echo.
echo 📋 Next steps:
echo 1. Copy config\credentials.example.yaml to config\credentials.yaml
echo 2. Add your actual API keys to config\credentials.yaml
echo 3. Test the setup: python marketpulse.py --mode collect
echo.
echo 🔗 Quick commands:
echo • Single collection: python marketpulse.py --mode collect
echo • Continuous monitoring: python marketpulse.py --mode monitor
echo • View database: docker exec -it marketpulse-db psql -U marketpulse -d marketpulse
echo • Stop database: docker-compose down
echo.
echo Happy trading! 📈
pause