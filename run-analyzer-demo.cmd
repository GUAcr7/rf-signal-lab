@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" "host\analyzer_viewer.py" --source demo
if errorlevel 1 pause
endlocal
