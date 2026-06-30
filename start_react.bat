@echo off
title FairLend AI — React Frontend (Port 3001)
cd /d "%~dp0frontend-react"

set PATH=C:\Program Files\nodejs;%PATH%

echo.
echo  ==========================================
echo   FairLend AI — React Frontend
echo   URL: http://localhost:3001
echo   Login: admin@fairlend.ai
echo   Pass:  FairLend@Admin2024
echo  ==========================================
echo.

where node >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Node.js not found at C:\Program Files\nodejs
    echo Download from: https://nodejs.org ^(LTS version^)
    pause
    exit /b 1
)

if not exist node_modules (
    echo Installing dependencies ^(first run - takes 2-3 minutes^)...
    npm install
)

echo Starting React dev server...
start http://localhost:3001
npm run dev
pause
