@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
echo.
echo  MarketPulse — starting full local stack
echo  (Postgres+Redis if Docker is up, else SQLite; then API + Next.js)
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\dev.ps1" %*
if errorlevel 1 (
  echo.
  echo  [ERROR] scripts\dev.ps1 failed.
  pause
)
