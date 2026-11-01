@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto missing_python
if not "%~1"=="" goto command_line
:menu
echo.
echo RF SIGNAL LAB - Board Control
echo 1. Check both boards
echo 2. Start or reuse RX display
echo 3. Stop RX display
echo 4. Select idle TX digital zero source
echo 5. Restore checked TX waveforms to RAM
echo 6. Request new background calibration (then reference tone)
echo Q. Quit
choice /C 123456Q /N /M "Select: "
if errorlevel 7 goto done
if errorlevel 6 goto calibration
if errorlevel 5 goto prepare
if errorlevel 4 goto source_off
if errorlevel 3 goto stop_rx
if errorlevel 2 goto start_rx
set "board_action=status"
goto invoke
:start_rx
set "board_action=start"
goto invoke
:stop_rx
set "board_action=stop"
goto invoke
:source_off
set "board_action=source-off"
goto invoke
:prepare
set "board_action=prepare-source"
goto invoke
:calibration
set "board_action=calibrate"
:invoke
".venv\Scripts\python.exe" "host\board_control.py" %board_action%
if errorlevel 1 echo Operation unconfirmed. Check the report before continuing.
pause
goto menu
:command_line
".venv\Scripts\python.exe" "host\board_control.py" %*
exit /b %errorlevel%
:missing_python
echo Project Python environment not found.
pause
exit /b 1
:done
endlocal
