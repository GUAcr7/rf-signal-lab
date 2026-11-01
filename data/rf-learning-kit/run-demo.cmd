@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" run_demo.py %*
  goto :done
)
if exist "..\..\START-HERE.md" if exist "..\..\.venv\Scripts\python.exe" (
  "..\..\.venv\Scripts\python.exe" run_demo.py %*
  goto :done
)
where py >nul 2>nul
if not errorlevel 1 (
  py -3 run_demo.py %*
  goto :done
)
python run_demo.py %*
:done
if errorlevel 1 pause
endlocal
