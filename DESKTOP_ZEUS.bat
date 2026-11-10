@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PY=%CD%\runtime\python\python.exe"
set "PYTHONPATH=%CD%\src"
set "BASE=https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/898f52352299f4a99780c9e4594c63549a6a0e98"
if not exist "%PY%" (
  echo Put DESKTOP_ZEUS.bat in the ZEUS folder, next to START_ZEUS3_V19_RC.bat
  pause
  exit /b 2
)
echo Starting ZEUS. This does not open Chrome or Edge.
echo Leave MetaTrader logged in.
echo Closing any stuck ZEUS loader.
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*zeus3.v19.web*' -or $_.ExecutablePath -like '*ZEUS_RC11_WINDOWS_RETRY\runtime\python*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
timeout /t 2 /nobreak >nul
powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing -Uri '%BASE%/zeus_probe.py' -OutFile '%CD%\zeus_probe.py'; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/7b654e038fc5fe4ff2f90e803438716aabf41d5d/zeus_patch.py' -OutFile '%CD%\zeus_patch.py'; Invoke-WebRequest -UseBasicParsing -Uri '%BASE%/zeus_wait.py' -OutFile '%CD%\zeus_wait.py'; Invoke-WebRequest -UseBasicParsing -Uri '%BASE%/zeus_desktop.py' -OutFile '%CD%\zeus_desktop.py'"
if exist "%CD%\ZEUS_PROGRESS.txt" del "%CD%\ZEUS_PROGRESS.txt"
"%PY%" "%CD%\zeus_probe.py"
if errorlevel 1 goto fail
set /p ZEUS3_MT5_TERMINAL_PATH=<"%CD%\ZEUS_TERMINAL_PATH.txt"
"%PY%" "%CD%\zeus_patch.py"
if errorlevel 1 goto fail
echo Checking the loader.
"%PY%" -c "import zeus3.v19.web; print('Loader import ok')"
if errorlevel 1 goto fail
echo Starting the loader in its own window. Leave that window open.
start "ZEUS Server" /D "%CD%" "%PY%" -u -m zeus3.v19.web
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
echo Dashboard is open. Leave the ZEUS Server window open.
pause
exit /b 0
:fail
echo.
echo Send me this window and the ZEUS Server window.
pause
exit /b 1
