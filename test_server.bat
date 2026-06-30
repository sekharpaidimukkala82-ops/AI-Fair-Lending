@echo off
title Test Server
cd /d "%~dp0"
echo Testing if Python can serve on port 8000...
echo Open http://localhost:8000 in browser after this starts
echo.
"C:\Users\admn\AppData\Local\Programs\Python\Python312\python.exe" test_server.py
pause
