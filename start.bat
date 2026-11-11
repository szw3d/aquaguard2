@echo off
title AquaGuard 3.0

cd /d "%~dp0"

echo ==============================
echo       AQUAGUARD 3.0
echo ==============================

echo.
echo Installerar Python-beroenden...

python -m pip install -r requirements.txt

echo.
echo Startar backend...

cd backend

python -m uvicorn main:app --host 127.0.0.1 --port 8080

pause