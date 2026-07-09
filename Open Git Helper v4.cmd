@echo off
setlocal

echo Starting...
echo Script folder = %~dp0

cd /d "%~dp0"

set "GIT_HELPER_TARGET_DIR=%~dp0"

python "%~dp0git_helper_v4.py"

echo.
echo Exit code = %errorlevel%
pause