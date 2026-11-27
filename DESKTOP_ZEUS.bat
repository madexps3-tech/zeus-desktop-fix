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
echo Writing the study file first.
if not exist "%CD%\src\zeus3\v19" mkdir "%CD%\src\zeus3\v19"
if not exist "%CD%\src\gold_shadow" mkdir "%CD%\src\gold_shadow"
powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/df2abed6b50b2796b0951f977ae83a9fddd67fe9/ZeusMboFlags.cpp' -OutFile '%CD%\ZeusMboFlags.cpp'; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/ba45da8493833ae5c43c44877db161f6f6a3fa2c/zeus_wait.py' -OutFile '%CD%\zeus_wait.py'; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/55f29dbb1463bd139dc3e905317fc7c905a1c699/zeus_open.py' -OutFile '%CD%\zeus_open.py'; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/bbf62aad4736d7b24ca8a1e2033ffb0a38335ea5/zeus_desktop.py' -OutFile '%CD%\zeus_desktop.py'; Invoke-WebRequest -UseBasicParsing -Uri '%BASE%/install_zone.py' -OutFile '%CD%\install_zone.py'; Invoke-WebRequest -UseBasicParsing -Uri '%BASE%/part0.txt' -OutFile '%CD%\part0.txt'; Invoke-WebRequest -UseBasicParsing -Uri '%BASE%/part1.txt' -OutFile '%CD%\part1.txt'; Invoke-WebRequest -UseBasicParsing -Uri '%BASE%/part2.txt' -OutFile '%CD%\part2.txt'; Invoke-WebRequest -UseBasicParsing -Uri '%BASE%/part3.txt' -OutFile '%CD%\part3.txt'; Invoke-WebRequest -UseBasicParsing -Uri '%BASE%/zeus_patch.py' -OutFile '%CD%\zeus_patch.py'; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/df2abed6b50b2796b0951f977ae83a9fddd67fe9/signals_engine.py' -OutFile '%CD%\src\zeus3\v19\signals_engine.py'; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/df2abed6b50b2796b0951f977ae83a9fddd67fe9/signals_page.py' -OutFile '%CD%\src\zeus3\v19\signals_page.py'; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/2d83d0cefc96a4bb77af8efe15d7a020c77b9f01/telegram_alert.py' -OutFile '%CD%\src\zeus3\v19\telegram_alert.py'; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/6c4d5cdc508d62e0e8060382a38774201cb59ad9/live_mapping.py' -OutFile '%CD%\src\zeus3\instruments\live_mapping.py'; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/df2abed6b50b2796b0951f977ae83a9fddd67fe9/zeus_patch.py' -OutFile '%CD%\zeus_patch.py'; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/a77a9641d180396a23497ef521c42a628dee54c6/mbo_book.py' -OutFile '%CD%\src\gold_shadow\mbo_book.py'; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/a76056645cf70e70c3da20e4dae715250ce77282/shadow_book_page.py' -OutFile '%CD%\src\zeus3\v19\shadow_book_page.py'"
"%PY%" "%CD%\install_zone.py" "%CD%"
if errorlevel 1 goto fail
findstr /C:"closedTick" "%CD%\ZeusMboFlags.cpp" >nul
if errorlevel 1 (
  echo The study file in the ZEUS folder is still the old one.
  echo Folder: %CD%
  goto fail
)
echo The study file in the ZEUS folder is the new one.
echo Folder: %CD%
set "COPIED="
for %%D in ("%CD%\ACS_Source" "%CD%\..\ACS_Source" "C:\SierraChart\ACS_Source" "C:\Sierra Chart\ACS_Source") do (
  if exist "%%~D\" (
    copy /Y "%CD%\ZeusMboFlags.cpp" "%%~D\ZeusMboFlags.cpp" >nul
    echo Copied the new study to %%~D
    set "COPIED=1"
  )
)
if not defined COPIED echo Sierra's ACS_Source folder was not found. The new file is in the ZEUS folder.
powershell -NoProfile -Command "Add-Type -Namespace Z -Name W -MemberDefinition '[DllImport(\"user32.dll\")] public static extern IntPtr FindWindow(string c, string n);'; if ([Z.W]::FindWindow($null, 'ZEUS') -ne [IntPtr]::Zero) { exit 0 } else { exit 1 }"
if not errorlevel 1 (
  echo ZEUS is already open. The study file is updated. Close ZEUS and run this again.
  exit /b 0
)
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
