@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

echo.
echo  Stopping MarketPulse services...
echo.

set "FOUND=0"

for %%P in (8000 3000) do (
    for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| find ":%%P " ^| find "LISTENING" 2^>nul') do (
        echo  [STOP] Killing PID %%a on port %%P
        taskkill /F /PID %%a >nul 2>&1
        set "FOUND=1"
    )
)

REM Also kill by window title (handles uvicorn child processes)
taskkill /F /FI "WINDOWTITLE eq MarketPulse-Backend*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq MarketPulse-Frontend*" >nul 2>&1

if "!FOUND!"=="0" (
    echo  No running services found.
) else (
    echo.
    echo  Services stopped.
)
echo.
