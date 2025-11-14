@echo off
REM MarketPulse Development Stop Script for Windows

echo ========================================
echo     Stopping MarketPulse Services
echo ========================================
echo.

REM Kill processes on ports 8000 and 3000
echo [INFO] Stopping backend service on port 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| find ":8000" ^| find "LISTENING"') do (
    echo Killing process %%a on port 8000
    taskkill /F /PID %%a 2>nul
)

echo [INFO] Stopping frontend service on port 3000...
for /f "tokens=5" %%a in ('netstat -ano ^| find ":3000" ^| find "LISTENING"') do (
    echo Killing process %%a on port 3000
    taskkill /F /PID %%a 2>nul
)

REM Close command windows
echo [INFO] Closing development windows...
taskkill /F /IM cmd.exe /FI "WINDOWTITLE eq MarketPulse Backend*" 2>nul
taskkill /F /IM cmd.exe /FI "WINDOWTITLE eq MarketPulse Frontend*" 2>nul

echo.
echo [SUCCESS] MarketPulse services stopped
echo.
pause