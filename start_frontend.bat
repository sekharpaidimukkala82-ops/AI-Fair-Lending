@echo off
title FairLend AI — React Frontend (Port 3001)
cd /d "%~dp0frontend-react"

REM Add Node.js to PATH
set PATH=C:\Program Files\nodejs;%PATH%

echo.
echo  ============================================================
echo   FairLend AI — Enterprise React Frontend
echo  ============================================================
echo   URL         : http://localhost:3001
echo   Login       : admin@fairlend.ai
echo   Password    : FairLend@Admin2024
echo.
echo   Pages       : Home, Upload, AI Assistant, Search
echo                 Fairness, Advanced Fairness (P3)
echo                 Cases (P3), Compliance (P3)
echo                 ML Engine, Reports, Monitoring, AI Settings
echo.
echo   Requires    : Backend running on port 8001
echo                 Run start_backend.bat first
echo  ============================================================
echo.

REM Check Node.js
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Node.js not found!
    echo Download from: https://nodejs.org  ^(LTS version^)
    echo.
    pause
    exit /b 1
)

echo Node.js:
node --version
echo.

REM Install dependencies on first run
if not exist node_modules (
    echo Installing npm dependencies ^(first run — takes 2-3 minutes^)...
    echo.
    npm install
    if %errorlevel% neq 0 (
        echo.
        echo ERROR: npm install failed. Check internet connection.
        pause
        exit /b 1
    )
    echo.
    echo Dependencies installed successfully!
    echo.
)

echo Starting React dev server...
echo.
start "" "http://localhost:3001"
npm run dev

:done
pause
