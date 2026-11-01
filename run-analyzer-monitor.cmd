@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" -X utf8 "host\stream_monitor_viewer.py" %*
if errorlevel 1 pause
endlocal
