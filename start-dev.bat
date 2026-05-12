@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

echo.
echo  ============================================================
echo   MarketPulse Development Start
echo  ============================================================
echo.

set "BACKEND_PORT=8000"
set "FRONTEND_PORT=3000"
set "LMSTUDIO_PORT=1234"
set "PYTHON=python"
set "BACKEND_OK=0"
set "FRONTEND_OK=0"

REM --- Check for venv or system python ---
if exist "venv\Scripts\python.exe" (
    set "PYTHON=venv\Scripts\python.exe"
    echo  [OK] Using venv Python
) else (
    where python >nul 2>&1
    if !errorlevel! neq 0 (
        echo  [ERROR] Python not found. Install Python or create venv.
        pause
        exit /b 1
    )
    echo  [OK] Using system Python
)

REM --- Check LM Studio ---
netstat -ano 2>nul | find ":%LMSTUDIO_PORT% " | find "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo  [OK] LM Studio running on port %LMSTUDIO_PORT%
) else (
    echo  [WARN] LM Studio not detected on port %LMSTUDIO_PORT% - LLM features will be limited
)

REM --- Check if backend port already in use ---
netstat -ano 2>nul | find ":%BACKEND_PORT% " | find "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo  [SKIP] Backend already running on port %BACKEND_PORT%
    set "BACKEND_OK=1"
) else (
    echo  [START] Backend on http://localhost:%BACKEND_PORT%
    start "MarketPulse-Backend" /min cmd /c "%PYTHON% -m uvicorn src.api.main:app --host 0.0.0.0 --port %BACKEND_PORT% --reload"
)

REM --- Check if frontend port already in use ---
netstat -ano 2>nul | find ":%FRONTEND_PORT% " | find "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo  [SKIP] Frontend already running on port %FRONTEND_PORT%
    set "FRONTEND_OK=1"
) else (
    REM Install deps if needed
    if not exist "marketpulse-client\node_modules" (
        echo  [INSTALL] Frontend dependencies...
        pushd marketpulse-client
        call npm install
        popd
    )
    echo  [START] Frontend on http://localhost:%FRONTEND_PORT%
    pushd marketpulse-client
    start "MarketPulse-Frontend" /min cmd /c "npm run dev"
    popd
)

REM --- Wait and health check ---
echo.
echo  Waiting for services to start...
timeout /t 6 /nobreak >nul

if %BACKEND_OK% equ 0 (
    curl -s -o nul -w "%%{http_code}" http://localhost:%BACKEND_PORT%/docs 2>nul | find "200" >nul 2>&1
    if !errorlevel! equ 0 (
        echo  [OK] Backend:  http://localhost:%BACKEND_PORT%  ^(API docs: /docs^)
    ) else (
        echo  [WAIT] Backend still starting - check http://localhost:%BACKEND_PORT%/docs
    )
)

if %FRONTEND_OK% equ 0 (
    curl -s -o nul -w "%%{http_code}" http://localhost:%FRONTEND_PORT%/ 2>nul | find "200" >nul 2>&1
    if !errorlevel! equ 0 (
        echo  [OK] Frontend: http://localhost:%FRONTEND_PORT%
    ) else (
        echo  [WAIT] Frontend still starting - check http://localhost:%FRONTEND_PORT%
    )
)

echo.
echo  ------------------------------------------------------------
echo  Backend:  http://localhost:%BACKEND_PORT%  (/docs for Swagger)
echo  Frontend: http://localhost:%FRONTEND_PORT%
echo  LM Studio: http://localhost:%LMSTUDIO_PORT%
echo.
echo  Run stop-dev.bat to shut down all services.
echo  ------------------------------------------------------------
echo.
