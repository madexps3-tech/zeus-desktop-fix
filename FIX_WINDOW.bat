@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PY=%CD%\runtime\python\python.exe"
if not exist "%PY%" (
  echo Put FIX_WINDOW.bat in the ZEUS folder, next to ZEUS_ONE.bat
  pause
  exit /b 2
)
echo Closing any old ZEUS server...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8783" ^| findstr "LISTENING"') do taskkill /PID %%P /F >nul 2>&1
"%PY%" -c "import webview" >nul 2>&1
if errorlevel 1 (
  echo This Python has no pip. Downloading it. Internet is required once.
  powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%CD%\get-pip.py'"
  if errorlevel 1 goto :EDGE
  "%PY%" "%CD%\get-pip.py" --no-warn-script-location
  if errorlevel 1 goto :EDGE
  "%PY%" -m pip install pywebview
  if errorlevel 1 goto :EDGE
)
echo Creating the desktop icon...
powershell -NoProfile -Command "$dir=(Get-Location).Path; $d=[Environment]::GetFolderPath('Desktop'); $s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'ZEUS.lnk')); $s.TargetPath=(Join-Path $dir 'FIX_WINDOW.bat'); $s.WorkingDirectory=$dir; $s.WindowStyle=7; $s.Description='ZEUS'; $s.Save()"
echo Starting ZEUS in its own window...
set "PYTHONPATH=%CD%\src"
start "ZEUS Server" /MIN "%PY%" -u -m zeus3.v19.web
"%PY%" "%CD%\zeus_desktop.py"
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8783" ^| findstr "LISTENING"') do taskkill /PID %%P /F >nul 2>&1
exit /b 0
:EDGE
echo Could not install the private window toolkit.
echo Opening one ZEUS window. This does not open your Chrome tabs.
set "PYTHONPATH=%CD%\src"
start "ZEUS Server" /MIN "%PY%" -u -m zeus3.v19.web
timeout /t 4 /nobreak >nul
set "EDGE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" set "EDGE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if exist "%EDGE%" (
  start "" "%EDGE%" --app=http://127.0.0.1:8783/v19/shadow
  echo Leave the black ZEUS Server window open while you use it.
  pause
  exit /b 0
)
echo Could not find a way to open the window.
pause
exit /b 2
