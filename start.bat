@echo off
title QUANT Stock Backtest System
cd /d "%~dp0"

echo ============================================
echo    QUANT Stock Backtest System
echo ============================================
echo.

set PY=
where python >nul 2>nul && set PY=python
if not defined PY where py >nul 2>nul && set PY=py

if not defined PY (
    echo [ERROR] Python not found.
    echo.
    echo Please install Python from:
    echo    https://www.python.org/downloads/
    echo Remember to check "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
)

echo Using Python: %PY%
echo Starting server...
echo.
echo Browser will open in 3 seconds.
echo Close this window to stop the server.
echo.

start "" /b cmd /c "timeout /t 3 /nobreak >nul & start http://localhost:8765"

%PY% server.py

echo.
echo ============================================
echo    Server stopped.
echo ============================================
pause
