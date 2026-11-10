@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PY=%CD%\runtime\python\python.exe"
set "LOG=%CD%\ZEUS_SERVER_LOG.txt"
if not exist "%PY%" (
  echo Put DESKTOP_ZEUS.bat in the ZEUS folder, next to START_ZEUS3_V19_RC.bat
  pause
  exit /b 2
)
if not exist "%CD%\zeus_desktop.py" (
  echo zeus_desktop.py is missing from this folder.
  pause
  exit /b 2
)
echo This does not open Chrome or Edge.
powershell -NoProfile -Command "$p=Join-Path (Get-Location).Path 'src\gold_shadow\shadow_book.py'; if(Test-Path -LiteralPath $p){ $t=[IO.File]::ReadAllText($p); $n=$t.Replace('from sweep_shadow import','from gold_shadow.sweep_shadow import'); if($t -ne $n){ $enc=New-Object System.Text.UTF8Encoding $false; [IO.File]::WriteAllText($p,$n,$enc); Write-Host 'Shadow page fixed.' } else { Write-Host 'Shadow page already fixed.' } } else { Write-Host 'Shadow file not found. The chart will still open.' }"
"%PY%" -c "import webview" >nul 2>&1
if errorlevel 1 (
  echo Adding the ZEUS window toolkit. Internet is required this once.
  powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%CD%\get-pip.py'"
  if errorlevel 1 (
    echo Could not download the toolkit installer.
    pause
    exit /b 2
  )
  "%PY%" "%CD%\get-pip.py" --no-warn-script-location
  if errorlevel 1 (
    echo Could not add pip.
    pause
    exit /b 2
  )
  "%PY%" -m pip install pywebview
  if errorlevel 1 (
    echo The window toolkit did not install. Chrome and Edge were not opened.
    pause
    exit /b 2
  )
)
echo Closing any old ZEUS server...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8783" ^| findstr "LISTENING"') do taskkill /PID %%P /F >nul 2>&1
set "PYTHONPATH=%CD%\src"
echo ZEUS start %DATE% %TIME%> "%LOG%"
start "ZEUS Server" /D "%CD%" /MIN "%PY%" -u -m zeus3.v19.web 1>> "%LOG%" 2>&1
"%PY%" "%CD%\zeus_desktop.py"
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8783" ^| findstr "LISTENING"') do taskkill /PID %%P /F >nul 2>&1
exit /b 0
