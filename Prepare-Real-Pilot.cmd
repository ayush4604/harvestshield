@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" scripts\import_public_history.py
if errorlevel 1 goto failure
".venv\Scripts\python.exe" -m backend.cli train --mode real
if errorlevel 1 goto failure
".venv\Scripts\python.exe" -m backend.cli backtest --mode real
if errorlevel 1 goto failure
echo Historical pilot ready. Use Real dataset and Historical replay in the dashboard.
pause
exit /b 0
:failure
echo Preparation failed. See the message above; existing records are retained.
pause
exit /b 1
