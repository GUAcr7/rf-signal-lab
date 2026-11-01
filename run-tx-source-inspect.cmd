@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" "host\tx_source.py" inspect %*
if errorlevel 1 pause
endlocal
