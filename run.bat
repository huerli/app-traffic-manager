@echo off
setlocal
cd /d "%~dp0"

rem Prefer the Windows Python launcher; fall back to python on PATH.
py -3 -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>&1
if not errorlevel 1 (
    set "FLOW_PYTHON=py -3"
) else (
    python -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>&1
    if errorlevel 1 (
        echo Python 3.10 or later is required. Install Python and enable the launcher or add it to PATH.
        goto :failed
    )
    set "FLOW_PYTHON=python"
)

if not exist ".run-venv-win\Scripts\python.exe" (
    %FLOW_PYTHON% -m venv .run-venv-win
    if errorlevel 1 goto :failed
)

".run-venv-win\Scripts\python.exe" -c "import yaml, webview; from importlib.metadata import version; assert version('pywebview') == '6.2.1'" >nul 2>&1
if errorlevel 1 (
    ".run-venv-win\Scripts\python.exe" -m pip install -r requirements-desktop.txt
    if errorlevel 1 goto :failed
)

".run-venv-win\Scripts\python.exe" script\open-manager.py %*
if errorlevel 1 goto :failed
exit /b 0

:failed
echo.
echo Flow could not start. Check the error above.
pause
exit /b 1
