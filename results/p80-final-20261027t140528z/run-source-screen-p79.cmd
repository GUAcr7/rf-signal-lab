@echo off
setlocal
cd /d "%~dp0"
if /I not "%~1"=="--rf-link-reviewed" (
  echo Use run-source-screen.cmd --rf-link-reviewed after the documented setup.
  echo This confirms the original coax and attenuation connection is unchanged.
  exit /b 2
)
".venv\Scripts\python.exe" host\source_screen_rf.py --preflight results\p59-p78-screen-preflight-20261027T121300659488Z\report.json --tx-job-transport usb-network --rf-link-reviewed --seconds 600 --initial-signal bpsk --required-signals bpsk qpsk qam16
if errorlevel 1 pause
endlocal
