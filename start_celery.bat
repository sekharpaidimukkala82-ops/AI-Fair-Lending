@echo off
title FairLend AI — Celery Worker
cd /d "%~dp0"

echo.
echo  ==========================================
echo   FairLend AI — Celery Task Worker
echo   Requires: Redis running on localhost:6379
echo.
echo   Queues: default, processing, ml, reports
echo   Get Redis: https://redis.io/download
echo   OR run with Docker: docker run -p 6379:6379 redis
echo  ==========================================
echo.

REM Check if Redis is reachable
"C:\Users\admn\AppData\Local\Programs\Python\Python312\python.exe" -c "import socket; s=socket.socket(); s.connect(('localhost',6379)); s.close(); print('Redis OK')" 2>nul
if %errorlevel% neq 0 (
    echo  WARNING: Redis not detected on localhost:6379
    echo  Celery will fail to start without Redis.
    echo  Start Redis first, then re-run this bat.
    echo.
    pause
    exit /b 1
)

echo  Redis detected. Starting Celery worker...
echo  Press Ctrl+C to stop.
echo.

"C:\Users\admn\AppData\Local\Programs\Python\Python312\python.exe" -m celery -A backend.workers.celery_app worker --loglevel=info -Q default,processing,ml,reports --concurrency=2

echo.
echo  Celery worker stopped.
pause
