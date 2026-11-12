@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PY=%CD%\runtime\python\python.exe"
set "PYTHONPATH=%CD%\src"
set "BASE=https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/7ff5d06f498b3f7a3d5b5f1226a71932e95a7e66"
if not exist "%PY%" (
  echo This file must stay in the ZEUS folder.
  pause
  exit /b 2
)
echo Starting ZEUS. This does not open Chrome or Edge.
if not exist "%CD%\src\zeus3\v19" mkdir "%CD%\src\zeus3\v19"
powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/53554f970633cd88a7e78376695d5fb99c720d09/zeus_wait.py' -OutFile '%CD%\zeus_wait.py'; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/53554f970633cd88a7e78376695d5fb99c720d09/zeus_desktop.py' -OutFile '%CD%\zeus_desktop.py'; Invoke-WebRequest -UseBasicParsing -Uri '%BASE%/install_zone.py' -OutFile '%CD%\install_zone.py'; Invoke-WebRequest -UseBasicParsing -Uri '%BASE%/part0.txt' -OutFile '%CD%\part0.txt'; Invoke-WebRequest -UseBasicParsing -Uri '%BASE%/part1.txt' -OutFile '%CD%\part1.txt'; Invoke-WebRequest -UseBasicParsing -Uri '%BASE%/part2.txt' -OutFile '%CD%\part2.txt'; Invoke-WebRequest -UseBasicParsing -Uri '%BASE%/part3.txt' -OutFile '%CD%\part3.txt'; Invoke-WebRequest -UseBasicParsing -Uri '%BASE%/zeus_patch.py' -OutFile '%CD%\zeus_patch.py'; Invoke-WebRequest -UseBasicParsing -Uri '%BASE%/signals_engine.py' -OutFile '%CD%\src\zeus3\v19\signals_engine.py'; Invoke-WebRequest -UseBasicParsing -Uri '%BASE%/signals_page.py' -OutFile '%CD%\src\zeus3\v19\signals_page.py'"
"%PY%" "%CD%\install_zone.py" "%CD%"
if errorlevel 1 goto fail
echo Leave MetaTrader logged in.
echo Closing any stuck ZEUS loader.
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*zeus3.v19.web*' -or $_.ExecutablePath -like '*ZEUS_RC11_WINDOWS_RETRY\runtime\python*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
timeout /t 2 /nobreak >nul
if exist "%CD%\ZEUS_PROGRESS.txt" del "%CD%\ZEUS_PROGRESS.txt"
"%PY%" "%CD%\zeus_probe.py"
if errorlevel 1 goto fail
set /p ZEUS3_MT5_TERMINAL_PATH=<"%CD%\ZEUS_TERMINAL_PATH.txt"
"%PY%" "%CD%\zeus_patch.py"
if errorlevel 1 goto fail
echo Checking the loader.
"%PY%" -c "import zeus3.v19.web; print('Loader import ok')"
if errorlevel 1 goto fail
echo Starting one dashboard loader.
start "ZEUS Server" /D "%CD%" "%PY%" -u -m zeus3.v19.web
"%PY%" "%CD%\zeus_wait.py"
if errorlevel 1 goto fail
echo Opening the ZEUS window.
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
echo Send me this window.
pause
exit /b 1
