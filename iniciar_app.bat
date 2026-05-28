@echo off
setlocal

cd /d "%~dp0"

if exist "..\.venv\Scripts\python.exe" (
    set "PYTHON=..\.venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

set "URL=http://127.0.0.1:5000/login"

start "" "%URL%"
"%PYTHON%" app.py

endlocal
