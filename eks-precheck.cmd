@echo off
rem Run eks-precheck without activating the virtual environment.
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo [ERROR] .venv not found. Run setup.cmd first.
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -m eks_precheck %*
