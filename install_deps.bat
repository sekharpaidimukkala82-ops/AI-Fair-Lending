@echo off
title Installing Fair Lending Dependencies
cd /d "%~dp0"

echo.
echo  ==========================================
echo   Installing all required packages...
echo   This will take 3-5 minutes.
echo  ==========================================
echo.

python -m pip install --upgrade pip

python -m pip install ^
    fastapi==0.111.0 ^
    uvicorn==0.29.0 ^
    python-multipart==0.0.9 ^
    pandas==2.2.2 ^
    numpy==1.26.4 ^
    scikit-learn==1.4.2 ^
    chromadb ^
    google-generativeai==0.5.4 ^
    shap==0.45.0 ^
    reportlab==4.2.0 ^
    jinja2==3.1.4 ^
    python-dotenv==1.0.1 ^
    pydantic==2.7.1 ^
    aiofiles==23.2.1 ^
    openpyxl==3.1.2 ^
    scipy==1.13.0 ^
    matplotlib==3.9.0 ^
    seaborn==0.13.2 ^
    fastembed

echo.
echo  ==========================================
echo   Installation complete!
echo   Now run start_backend.bat
echo  ==========================================
echo.
pause
