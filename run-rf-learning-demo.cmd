@echo off
setlocal
call "%~dp0deliverables\rf-learning-kit-20261022T130520Z\run-demo.cmd" %*
exit /b %errorlevel%
