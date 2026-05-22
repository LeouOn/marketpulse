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

REM --- Stop existing services first ---
echo  [STOP] Checking for existing services...
for %%P in (8000 3000) do (
    for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| find ":%%P " ^| find "LISTENING" 2^>nul') do (
        echo  [STOP] Killing PID %%a on port %%P
        taskkill /F /PID %%a >nul 2>&1
    )
)
taskkill /F /FI "WINDOWTITLE eq MarketPulse-Backend*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq MarketPulse-Frontend*" >nul 2>&1
timeout /t 2 /nobreak >nul

REM --- Check and install Python requirements ---
echo  [CHECK] Verifying Python packages...
%PYTHON% -c "import pkg_resources; missing=[]; reqs=open('requirements.txt').read().strip().split('\n'); [missing.append(r.split('>=')[0].split('[')[0].strip()) for r in reqs if r.strip() and not r.startswith('#')]; [missing.remove(pkg.key.replace('_','-')) for pkg in pkg_resources.working_set if pkg.key.replace('_','-') in missing]; exit(len(missing))" >nul 2>&1
if %errorlevel% neq 0 (
    echo  [INSTALL] Installing/updating Python packages...
    %PYTHON% -m pip install -r requirements.txt --quiet
    if !errorlevel! equ 0 (
        echo  [OK] All packages installed
    ) else (
        echo  [WARN] Some packages failed to install
    )
) else (
    echo  [OK] All Python packages present
)

REM --- Check LM Studio ---
netstat -ano 2>nul | find ":%LMSTUDIO_PORT% " | find "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo  [OK] LM Studio running on port %LMSTUDIO_PORT%
) else (
    echo  [WARN] LM Studio not detected on port %LMSTUDIO_PORT% - LLM features will be limited
)

REM --- Start backend ---
echo  [START] Backend on http://localhost:%BACKEND_PORT%
start "MarketPulse-Backend" /min cmd /c "%PYTHON% -m uvicorn src.api.main:app --host 0.0.0.0 --port %BACKEND_PORT% --reload"

REM --- Wait for backend to be ready ---
echo  [WAIT] Waiting for backend to start...
set "BACKEND_READY=0"
for /L %%i in (1,1,30) do (
    if !BACKEND_READY! equ 0 (
        curl -s -o nul -w "%%{http_code}" http://localhost:%BACKEND_PORT%/docs 2>nul | find "200" >nul 2>&1
        if !errorlevel! equ 0 (
            set "BACKEND_READY=1"
            echo  [OK] Backend is ready
        ) else (
            timeout /t 1 /nobreak >nul
        )
    )
)
if %BACKEND_READY% equ 0 (
    echo  [WARN] Backend did not start within 30s - check the backend window for errors
)

REM --- Start frontend ---
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

REM --- Wait for frontend ---
echo  [WAIT] Waiting for frontend to start...
timeout /t 5 /nobreak >nul

curl -s -o nul -w "%%{http_code}" http://localhost:%FRONTEND_PORT%/ 2>nul | find "200" >nul 2>&1
if !errorlevel! equ 0 (
    echo  [OK] Frontend: http://localhost:%FRONTEND_PORT%
) else (
    echo  [WAIT] Frontend still starting - check http://localhost:%FRONTEND_PORT%
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
