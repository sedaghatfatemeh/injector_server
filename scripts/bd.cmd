@echo off
setlocal
pushd "%~dp0.." || exit /b 1
if exist ".local\beads\bd.exe" (
    ".local\beads\bd.exe" %*
) else (
    where bd.exe >nul 2>nul
    if errorlevel 1 (
        echo Beads is not installed. See docs/development-workflow.md. 1>&2
        popd
        exit /b 1
    )
    bd.exe %*
)
set "beadsExitCode=%errorlevel%"
popd
exit /b %beadsExitCode%
