@echo off
setlocal
pushd "%~dp0" || exit /b 1

pwsh -NoProfile -File "%~dp0scripts\conversation.ps1" %*
set "launch_exit_code=%errorlevel%"

popd
if not "%launch_exit_code%"=="0" (
    echo.
    echo tHead could not start or exited with an error. See the details above.
    echo Check that PowerShell 7 and the documented prerequisites are installed.
    pause
)
exit /b %launch_exit_code%
