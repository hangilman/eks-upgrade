@echo off
rem eks-precheck setup for Windows (no PowerShell script execution needed)
setlocal
cd /d "%~dp0"

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo [ERROR] Python not found. Install it first:  winget install -e --id Python.Python.3.12
  echo         Then open a NEW terminal and run setup.cmd again.
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/2] Creating virtual environment: .venv
  %PY% -m venv .venv || goto :fail
) else (
  echo [1/2] Virtual environment already exists: .venv
)

echo [2/2] Installing eks-precheck
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -e . || goto :fail

echo.
echo Setup complete. Next steps:
echo   .\eks-precheck.cmd init
echo   notepad env.yaml
echo   .\eks-precheck.cmd run env.yaml
exit /b 0

:fail
echo [ERROR] Setup failed. Check Python 3.10+ and network/proxy settings.
exit /b 1
