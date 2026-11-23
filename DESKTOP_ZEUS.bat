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
powershell -NoProfile -Command "Add-Type -Namespace Z -Name W -MemberDefinition '[DllImport(\"user32.dll\")] public static extern IntPtr FindWindow(string c, string n);'; if ([Z.W]::FindWindow($null, 'ZEUS') -ne [IntPtr]::Zero) { exit 0 } else { exit 1 }"
if not errorlevel 1 (
  echo ZEUS is already open. Leaving it.
  exit /b 0
)
if not exist "%CD%\src\zeus3\v19" mkdir "%CD%\src\zeus3\v19"
if not exist "%CD%\src\gold_shadow" mkdir "%CD%\src\gold_shadow"
powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/f137d0998d7010df5961fc3b1241b751582da026/ZeusMboFlags.cpp' -OutFile '%CD%\ZeusMboFlags.cpp'; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/ba45da8493833ae5c43c44877db161f6f6a3fa2c/zeus_wait.py' -OutFile '%CD%\zeus_wait.py'; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/55f29dbb1463bd139dc3e905317fc7c905a1c699/zeus_open.py' -OutFile '%CD%\zeus_open.py'; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/b809f0e31c22df2bd6bc406e48fb7c47fb02e91d/zeus_desktop.py' -OutFile '%CD%\zeus_desktop.py'; Invoke-WebRequest -UseBasicParsing -Uri '%BASE%/install_zone.py' -OutFile '%CD%\install_zone.py'; Invoke-WebRequest -UseBasicParsing -Uri '%BASE%/part0.txt' -OutFile '%CD%\part0.txt'; Invoke-WebRequest -UseBasicParsing -Uri '%BASE%/part1.txt' -OutFile '%CD%\part1.txt'; Invoke-WebRequest -UseBasicParsing -Uri '%BASE%/part2.txt' -OutFile '%CD%\part2.txt'; Invoke-WebRequest -UseBasicParsing -Uri '%BASE%/part3.txt' -OutFile '%CD%\part3.txt'; Invoke-WebRequest -UseBasicParsing -Uri '%BASE%/zeus_patch.py' -OutFile '%CD%\zeus_patch.py'; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/185f2f26f996d91a8bbc9bd461ba775bc7279091/signals_engine.py' -OutFile '%CD%\src\zeus3\v19\signals_engine.py'; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/6b347880d222f6444d3715da4aa467f5c4681f76/signals_page.py' -OutFile '%CD%\src\zeus3\v19\signals_page.py'; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/a77a9641d180396a23497ef521c42a628dee54c6/telegram_alert.py' -OutFile '%CD%\src\zeus3\v19\telegram_alert.py'; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/6c4d5cdc508d62e0e8060382a38774201cb59ad9/live_mapping.py' -OutFile '%CD%\src\zeus3\instruments\live_mapping.py'; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/d39b5c0fbc7dc2bdac68957ce67c3a9c85f4265a/zeus_patch.py' -OutFile '%CD%\zeus_patch.py'; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/a77a9641d180396a23497ef521c42a628dee54c6/mbo_book.py' -OutFile '%CD%\src\gold_shadow\mbo_book.py'; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/a76056645cf70e70c3da20e4dae715250ce77282/shadow_book_page.py' -OutFile '%CD%\src\zeus3\v19\shadow_book_page.py'"
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
echo Opening the ZEUS window.
"%PY%" -c "import webview" >nul 2>&1
if errorlevel 1 (
  echo Installing the window toolkit.
  powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%CD%\get-pip.py'"
  "%PY%" "%CD%\get-pip.py" --no-warn-script-location
  "%PY%" -m pip install pywebview
)
start "" "%PY%" "%CD%\zeus_desktop.py"
exit /b 0
:fail
echo.
echo Send me this window.
pause
exit /b 1
