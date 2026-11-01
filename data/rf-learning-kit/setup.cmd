@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  where py >nul 2>nul
  if errorlevel 1 (
    python -m venv .venv
  ) else (
    py -3 -m venv .venv
  )
  if errorlevel 1 goto :failed
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :failed
echo Ready. Double-click run-demo.cmd.
pause
exit /b 0
:failed
echo Setup failed. Please keep this message and read README.md.
pause
exit /b 1
