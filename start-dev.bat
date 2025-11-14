@echo off
REM MarketPulse Development Startup Script for Windows
REM This script starts both backend and frontend services

echo ========================================
echo    MarketPulse Development Environment
echo ========================================
echo.

REM Check if venv exists
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found!
    echo Please run: python -m venv venv
    echo Then run: venv\Scripts\activate
    echo Then run: pip install -r requirements.txt
    pause
    exit /b 1
)

REM Check if node_modules exists
if not exist "marketpulse-client\node_modules" (
    echo [INFO] Installing frontend dependencies...
    cd marketpulse-client
    npm install
    cd ..
)

echo [INFO] Starting MarketPulse services...
echo.
echo Backend will run on: http://localhost:8000
echo Frontend will run on: http://localhost:3000
echo.
echo Press Ctrl+C to stop the services
echo.

REM Start backend in first window
start "MarketPulse Backend" cmd /k "title MarketPulse Backend && venv\Scripts\python.exe -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload"

REM Wait 3 seconds for backend to start
timeout /t 3 /nobreak >nul

REM Start frontend in second window
start "MarketPulse Frontend" cmd /k "cd marketpulse-client && title MarketPulse Frontend && npm run dev"

REM Wait 5 seconds for services to initialize
timeout /t 5 /nobreak >nul

echo.
echo ========================================
echo    Services Started!
echo ========================================
echo.
echo Testing services...

REM Test backend
curl -s http://localhost:8000/ >nul 2>&1
if %errorlevel% equ 0 (
    echo [SUCCESS] Backend API is running on http://localhost:8000
    echo          API Docs: http://localhost:8000/docs
) else (
    echo [WARNING] Backend may still be starting...
)

REM Test frontend
curl -s http://localhost:3000/ >nul 2>&1
if %errorlevel% equ 0 (
    echo [SUCCESS] Frontend is running on http://localhost:3000
) else (
    echo [WARNING] Frontend may still be starting...
)

echo.
echo Two command windows have been opened for each service.
echo Close this window or press any key to continue...
pause >nul