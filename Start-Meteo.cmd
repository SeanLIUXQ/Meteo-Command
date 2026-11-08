@echo off
setlocal
cd /d "%~dp0"
if exist "Meteo-Command.exe" (
  "Meteo-Command.exe" %*
  if errorlevel 1 goto :failed
  exit /b 0
)
where py >nul 2>nul
if errorlevel 1 (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Python 3.10+ is required. Install Python from https://www.python.org/downloads/
    pause
    exit /b 1
  )
  set "METEO_PYTHON=python"
) else (
  set "METEO_PYTHON=py -3"
)
if not exist ".venv\Scripts\python.exe" (
  %METEO_PYTHON% -c "import sys;sys.exit(0 if sys.version_info >= (3,10) else 1)"
  if errorlevel 1 (
    echo Python 3.10+ is required.
    pause
    exit /b 1
  )
  %METEO_PYTHON% -m venv .venv
  if errorlevel 1 goto :failed
)
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" run.py %*
if errorlevel 1 goto :failed
exit /b 0
:failed
echo Startup failed. Check the message above and your network connection.
pause
exit /b 1
