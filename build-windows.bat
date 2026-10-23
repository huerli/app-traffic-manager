@echo off
setlocal
cd /d "%~dp0"
py -3 -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>&1
if not errorlevel 1 (
    set "FLOW_PYTHON=py -3"
) else (
    python -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>&1
    if errorlevel 1 (
        echo Install Python 3.10 or later and add it to PATH.
        goto :failed
    )
    set "FLOW_PYTHON=python"
)
%FLOW_PYTHON% script\build-desktop.py --platform windows %*
if errorlevel 1 goto :failed
echo Build completed.
if "%~1"=="" pause
exit /b 0
:failed
echo Build failed. Check the error above.
pause
exit /b 1
