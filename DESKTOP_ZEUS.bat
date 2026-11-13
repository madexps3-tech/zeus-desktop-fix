@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
set "PY=%CD%\runtime\python\python.exe"
if not exist "%PY%" (
  echo This copy is not in the ZEUS folder. Looking for it...
  set "ROOT="
  for /f "delims=" %%F in ('dir /s /b "%USERPROFILE%\python.exe" 2^>nul') do (
    echo %%F | findstr /i "runtime\\python\\python.exe" >nul && set "ROOT=%%~dpF"
  )
  if not defined ROOT (
    echo.
    echo Put this file in the folder that contains the runtime folder.
    echo That is the folder you used the last time ZEUS opened.
    pause
    exit /b 2
  )
  cd /d "!ROOT!\..\.."
  set "PY=!CD!\runtime\python\python.exe"
)
set "PYTHONPATH=%CD%\src"
set "BASE=https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/0eb3a5f3d0ee4eeba1b946f932c78642d0496952"
if not exist "%PY%" (
  echo The ZEUS folder was found but its Python is missing.
  echo Folder: %CD%
  pause
  exit /b 2
)
echo Starting ZEUS from %CD%
echo This does not open Chrome or Edge.
if not exist "%CD%\src\zeus3\v19" mkdir "%CD%\src\zeus3\v19"
powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/c4932ba7e694be42395bc0bc161fa4b1a8e39c77/zeus_wait.py' -OutFile '%CD%\zeus_wait.py'; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/55f29dbb1463bd139dc3e905317fc7c905a1c699/zeus_open.py' -OutFile '%CD%\zeus_open.py'; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/954c2862e3d517b322be45aa4672f85cadf579c5/zeus_desktop.py' -OutFile '%CD%\zeus_desktop.py'; Invoke-WebRequest -UseBasicParsing -Uri '%BASE%/install_zone.py' -OutFile '%CD%\install_zone.py'; Invoke-WebRequest -UseBasicParsing -Uri '%BASE%/part0.txt' -OutFile '%CD%\part0.txt'; Invoke-WebRequest -UseBasicParsing -Uri '%BASE%/part1.txt' -OutFile '%CD%\part1.txt'; Invoke-WebRequest -UseBasicParsing -Uri '%BASE%/part2.txt' -OutFile '%CD%\part2.txt'; Invoke-WebRequest -UseBasicParsing -Uri '%BASE%/part3.txt' -OutFile '%CD%\part3.txt'; Invoke-WebRequest -UseBasicParsing -Uri '%BASE%/zeus_patch.py' -OutFile '%CD%\zeus_patch.py'; Invoke-WebRequest -UseBasicParsing -Uri '%BASE%/signals_engine.py' -OutFile '%CD%\src\zeus3\v19\signals_engine.py'; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/49d4c269f0183b6697d1fdc324405b370f4cc5fc/signals_page.py' -OutFile '%CD%\src\zeus3\v19\signals_page.py'; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/55f29dbb1463bd139dc3e905317fc7c905a1c699/live_mapping.py' -OutFile '%CD%\src\zeus3\instruments\live_mapping.py'; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/c4932ba7e694be42395bc0bc161fa4b1a8e39c77/zeus_patch.py' -OutFile '%CD%\zeus_patch.py'"
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
if exist "%CD%\ZEUS_SERVER.log" del "%CD%\ZEUS_SERVER.log"
start "ZEUS Server" /D "%CD%" cmd /c ""%PY%" -u -m zeus3.v19.web > "%CD%\ZEUS_SERVER.log" 2>&1"
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
