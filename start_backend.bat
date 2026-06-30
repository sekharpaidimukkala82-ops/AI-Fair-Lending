@echo off
title FairLend AI — Backend API (Port 8001)
cd /d "%~dp0"

echo.
echo  ============================================================
echo   FairLend AI — Enterprise Platform  ^|  Backend API
echo  ============================================================
echo   API         : http://localhost:8001
echo   Docs        : http://localhost:8001/docs
echo   Health      : http://localhost:8001/health
echo   Metrics     : http://localhost:8001/metrics  (Prometheus P4)
echo   WebSocket   : ws://localhost:8001/ws/{file_id}
echo.
echo   Login       : admin@fairlend.ai
echo   Password    : FairLend@Admin2024
echo.
echo   Python      : C:\Users\ADMIN\AppData\Local\Programs\Python\Python312\python.exe
echo   Database    : SQLite (dev)  ^|  Set DATABASE_URL for PostgreSQL
echo   AI Keys     : Set in UI (AI Settings) or backend\.env
echo.
echo   P2 Optional : start_celery.bat  (Celery + Redis task queue)
echo   P4 Optional : Set SENTRY_DSN in .env for error tracking
echo   Docker      : docker compose up --build  (full stack)
echo  ============================================================
echo.

REM Install/update dependencies
echo Checking dependencies...
"C:\Users\ADMIN\AppData\Local\Programs\Python\Python312\python.exe" -m pip install groq openai fastembed --quiet --disable-pip-version-check 2>nul
echo Dependencies OK.
echo.

REM Kill anything already on port 8001
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":8001 "') do (
    echo Freeing port 8001 ^(PID %%a^)...
    taskkill /PID %%a /F >nul 2>&1
)
timeout /t 1 /nobreak >nul

echo Starting backend server...
echo Press Ctrl+C to stop.
echo.

"C:\Users\ADMIN\AppData\Local\Programs\Python\Python312\python.exe" run.py

echo.
echo  ============================================================
echo   Server stopped.
echo  ============================================================
pause
