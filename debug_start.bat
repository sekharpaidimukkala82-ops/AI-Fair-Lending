@echo off
title Debug Backend Startup
cd /d "%~dp0"

echo Killing port 8000...
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":8000 "') do taskkill /PID %%a /F >nul 2>&1
timeout /t 2 /nobreak >nul

echo.
echo === Testing imports one by one ===
echo.

"C:\Users\admn\AppData\Local\Programs\Python\Python312\python.exe" -c "import fastapi; print('fastapi OK')"
"C:\Users\admn\AppData\Local\Programs\Python\Python312\python.exe" -c "import uvicorn; print('uvicorn OK')"
"C:\Users\admn\AppData\Local\Programs\Python\Python312\python.exe" -c "import chromadb; print('chromadb OK')"
"C:\Users\admn\AppData\Local\Programs\Python\Python312\python.exe" -c "import pandas; print('pandas OK')"
"C:\Users\admn\AppData\Local\Programs\Python\Python312\python.exe" -c "import sklearn; print('sklearn OK')"
"C:\Users\admn\AppData\Local\Programs\Python\Python312\python.exe" -c "import shap; print('shap OK')"
"C:\Users\admn\AppData\Local\Programs\Python\Python312\python.exe" -c "import reportlab; print('reportlab OK')"
"C:\Users\admn\AppData\Local\Programs\Python\Python312\python.exe" -c "import google.generativeai; print('google-generativeai OK')"
"C:\Users\admn\AppData\Local\Programs\Python\Python312\python.exe" -c "import dotenv; print('dotenv OK')"
"C:\Users\admn\AppData\Local\Programs\Python\Python312\python.exe" -c "import aiofiles; print('aiofiles OK')"

echo.
echo === Testing backend import ===
"C:\Users\admn\AppData\Local\Programs\Python\Python312\python.exe" -c "from backend.main import app; print('backend.main OK')"

echo.
echo === Starting server ===
"C:\Users\admn\AppData\Local\Programs\Python\Python312\python.exe" run.py

echo.
pause
