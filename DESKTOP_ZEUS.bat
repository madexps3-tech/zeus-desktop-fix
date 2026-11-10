@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PY=%CD%\runtime\python\python.exe"
set "PYTHONPATH=%CD%\src"
set "BASE=https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/51969689c2ff70ea1623dfa526fb865c8a43fcce"
if not exist "%PY%" (
  echo Put DESKTOP_ZEUS.bat in the ZEUS folder, next to START_ZEUS3_V19_RC.bat
  pause
  exit /b 2
)
echo Starting ZEUS. This does not open Chrome or Edge.
echo Leave MetaTrader logged in. Close any old ZEUS Server window first.
powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing -Uri '%BASE%/zeus_probe.py' -OutFile '%CD%\zeus_probe.py'; Invoke-WebRequest -UseBasicParsing -Uri '%BASE%/zeus_patch.py' -OutFile '%CD%\zeus_patch.py'; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/main/zeus_wait.py' -OutFile '%CD%\zeus_wait.py'; Invoke-WebRequest -UseBasicParsing -Uri '%BASE%/zeus_desktop.py' -OutFile '%CD%\zeus_desktop.py'"
if exist "%CD%\ZEUS_PROGRESS.txt" del "%CD%\ZEUS_PROGRESS.txt"
"%PY%" "%CD%\zeus_probe.py"
if errorlevel 1 goto fail
set /p ZEUS3_MT5_TERMINAL_PATH=<"%CD%\ZEUS_TERMINAL_PATH.txt"
"%PY%" "%CD%\zeus_patch.py"
if errorlevel 1 goto fail
echo Checking the loader.
"%PY%" -c "import zeus3.v19.web; print('Loader import ok')"
if errorlevel 1 goto fail
echo Starting the dashboard loader. Its text will appear below.
start "ZEUS Server" /B /D "%CD%" "%PY%" -u -m zeus3.v19.web
"%PY%" "%CD%\zeus_wait.py"
if errorlevel 1 goto fail
"%PY%" -c "import webview" >nul 2>&1
if errorlevel 1 (
  echo Installing the window toolkit.
  powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%CD%\get-pip.py'"
  "%PY%" "%CD%\get-pip.py" --no-warn-script-location
  "%PY%" -m pip install pywebview
)
"%PY%" "%CD%\zeus_desktop.py"
echo You can close this window. Leave it open while the dashboard is open.
pause
exit /b 0
:fail
echo.
echo Send me this window.
pause
exit /b 1
