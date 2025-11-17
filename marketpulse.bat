@echo off
REM ========================================
REM   MarketPulse Control Script
REM   Usage: marketpulse.bat [command]
REM   Commands: start, stop, restart, status, help
REM ========================================

setlocal enabledelayedexpansion

REM Get command argument
set "COMMAND=%1"
if "%COMMAND%"=="" set "COMMAND=help"

REM Define colors (for Windows 10+)
set "COLOR_GREEN=[92m"
set "COLOR_RED=[91m"
set "COLOR_YELLOW=[93m"
set "COLOR_BLUE=[94m"
set "COLOR_RESET=[0m"

REM Process command
if /i "%COMMAND%"=="start" goto START
if /i "%COMMAND%"=="stop" goto STOP
if /i "%COMMAND%"=="restart" goto RESTART
if /i "%COMMAND%"=="status" goto STATUS
if /i "%COMMAND%"=="help" goto HELP
if /i "%COMMAND%"=="-h" goto HELP
if /i "%COMMAND%"=="--help" goto HELP

echo [ERROR] Unknown command: %COMMAND%
echo Run 'marketpulse.bat help' for usage information
exit /b 1

REM ========================================
REM   HELP COMMAND
REM ========================================
:HELP
echo.
echo %COLOR_BLUE%========================================%COLOR_RESET%
echo %COLOR_BLUE%   MarketPulse Control Script%COLOR_RESET%
echo %COLOR_BLUE%========================================%COLOR_RESET%
echo.
echo %COLOR_GREEN%USAGE:%COLOR_RESET%
echo   marketpulse.bat [command]
echo.
echo %COLOR_GREEN%COMMANDS:%COLOR_RESET%
echo   start       - Start backend and frontend services
echo   stop        - Stop all MarketPulse services
echo   restart     - Restart all services
echo   status      - Check if services are running
echo   help        - Show this help message
echo.
echo %COLOR_GREEN%EXAMPLES:%COLOR_RESET%
echo   marketpulse.bat start
echo   marketpulse.bat stop
echo   marketpulse.bat status
echo.
echo %COLOR_GREEN%SERVICES:%COLOR_RESET%
echo   Backend API:  http://localhost:8000
echo   API Docs:     http://localhost:8000/docs
echo   Frontend:     http://localhost:3000
echo.
exit /b 0

REM ========================================
REM   STATUS COMMAND
REM ========================================
:STATUS
echo.
echo %COLOR_BLUE%========================================%COLOR_RESET%
echo %COLOR_BLUE%   MarketPulse Service Status%COLOR_RESET%
echo %COLOR_BLUE%========================================%COLOR_RESET%
echo.

REM Check backend (port 8000)
netstat -ano | find ":8000" | find "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo %COLOR_GREEN%[RUNNING]%COLOR_RESET% Backend API on http://localhost:8000
    for /f "tokens=5" %%a in ('netstat -ano ^| find ":8000" ^| find "LISTENING"') do (
        echo          Process ID: %%a
    )
) else (
    echo %COLOR_RED%[STOPPED]%COLOR_RESET% Backend API
)

REM Check frontend (port 3000)
netstat -ano | find ":3000" | find "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo %COLOR_GREEN%[RUNNING]%COLOR_RESET% Frontend on http://localhost:3000
    for /f "tokens=5" %%a in ('netstat -ano ^| find ":3000" ^| find "LISTENING"') do (
        echo          Process ID: %%a
    )
) else (
    echo %COLOR_RED%[STOPPED]%COLOR_RESET% Frontend
)

echo.
exit /b 0

REM ========================================
REM   STOP COMMAND
REM ========================================
:STOP
echo.
echo %COLOR_BLUE%========================================%COLOR_RESET%
echo %COLOR_BLUE%   Stopping MarketPulse Services%COLOR_RESET%
echo %COLOR_BLUE%========================================%COLOR_RESET%
echo.

REM Kill processes on port 8000
echo [INFO] Stopping backend service on port 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| find ":8000" ^| find "LISTENING"') do (
    echo        Killing process %%a
    taskkill /F /PID %%a 2>nul
    if !errorlevel! equ 0 (
        echo        %COLOR_GREEN%[SUCCESS]%COLOR_RESET% Backend stopped
    )
)

REM Kill processes on port 3000
echo [INFO] Stopping frontend service on port 3000...
for /f "tokens=5" %%a in ('netstat -ano ^| find ":3000" ^| find "LISTENING"') do (
    echo        Killing process %%a
    taskkill /F /PID %%a 2>nul
    if !errorlevel! equ 0 (
        echo        %COLOR_GREEN%[SUCCESS]%COLOR_RESET% Frontend stopped
    )
)

REM Close command windows
echo [INFO] Closing MarketPulse windows...
taskkill /F /IM cmd.exe /FI "WINDOWTITLE eq MarketPulse Backend*" 2>nul
taskkill /F /IM cmd.exe /FI "WINDOWTITLE eq MarketPulse Frontend*" 2>nul

echo.
echo %COLOR_GREEN%[SUCCESS]%COLOR_RESET% All MarketPulse services stopped
echo.
exit /b 0

REM ========================================
REM   START COMMAND
REM ========================================
:START
echo.
echo %COLOR_BLUE%========================================%COLOR_RESET%
echo %COLOR_BLUE%   MarketPulse Development Environment%COLOR_RESET%
echo %COLOR_BLUE%========================================%COLOR_RESET%
echo.

REM Check if venv exists
if not exist "venv\Scripts\python.exe" (
    echo %COLOR_RED%[ERROR]%COLOR_RESET% Virtual environment not found!
    echo.
    echo Please run the following commands:
    echo   1. python -m venv venv
    echo   2. venv\Scripts\activate
    echo   3. pip install -r requirements.txt
    echo.
    exit /b 1
)

REM Check if services are already running
netstat -ano | find ":8000" | find "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo %COLOR_YELLOW%[WARNING]%COLOR_RESET% Backend is already running on port 8000
    echo.
    choice /C YN /M "Do you want to restart it?"
    if errorlevel 2 exit /b 0
    if errorlevel 1 call :STOP
)

netstat -ano | find ":3000" | find "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo %COLOR_YELLOW%[WARNING]%COLOR_RESET% Frontend is already running on port 3000
    echo.
    choice /C YN /M "Do you want to restart it?"
    if errorlevel 2 exit /b 0
    if errorlevel 1 call :STOP
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
echo %COLOR_YELLOW%[TIP]%COLOR_RESET% Two separate windows will open for backend and frontend
echo %COLOR_YELLOW%[TIP]%COLOR_RESET% Press Ctrl+C in those windows to stop individual services
echo.

REM Start backend in new window
start "MarketPulse Backend" cmd /k "title MarketPulse Backend && venv\Scripts\python.exe -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload"

REM Wait for backend to start
echo [INFO] Waiting for backend to start...
timeout /t 3 /nobreak >nul

REM Start frontend in new window
start "MarketPulse Frontend" cmd /k "cd marketpulse-client && title MarketPulse Frontend && npm run dev"

REM Wait for services to initialize
echo [INFO] Waiting for services to initialize...
timeout /t 5 /nobreak >nul

echo.
echo %COLOR_BLUE%========================================%COLOR_RESET%
echo %COLOR_BLUE%   Testing Services%COLOR_RESET%
echo %COLOR_BLUE%========================================%COLOR_RESET%
echo.

REM Test backend
curl -s http://localhost:8000/ >nul 2>&1
if %errorlevel% equ 0 (
    echo %COLOR_GREEN%[SUCCESS]%COLOR_RESET% Backend API running on http://localhost:8000
    echo          API Docs: http://localhost:8000/docs
) else (
    echo %COLOR_YELLOW%[WARNING]%COLOR_RESET% Backend may still be starting...
    echo          Check the Backend window for errors
)

REM Test frontend
curl -s http://localhost:3000/ >nul 2>&1
if %errorlevel% equ 0 (
    echo %COLOR_GREEN%[SUCCESS]%COLOR_RESET% Frontend running on http://localhost:3000
) else (
    echo %COLOR_YELLOW%[WARNING]%COLOR_RESET% Frontend may still be starting...
    echo          Check the Frontend window for errors
)

echo.
echo %COLOR_GREEN%[READY]%COLOR_RESET% MarketPulse is running!
echo.
echo %COLOR_BLUE%========================================%COLOR_RESET%
echo %COLOR_BLUE%   Quick Commands%COLOR_RESET%
echo %COLOR_BLUE%========================================%COLOR_RESET%
echo   marketpulse.bat status     - Check service status
echo   marketpulse.bat stop       - Stop all services
echo   marketpulse.bat restart    - Restart services
echo.
exit /b 0

REM ========================================
REM   RESTART COMMAND
REM ========================================
:RESTART
echo.
echo %COLOR_BLUE%========================================%COLOR_RESET%
echo %COLOR_BLUE%   Restarting MarketPulse Services%COLOR_RESET%
echo %COLOR_BLUE%========================================%COLOR_RESET%
echo.

call :STOP
timeout /t 2 /nobreak >nul
call :START

exit /b 0
