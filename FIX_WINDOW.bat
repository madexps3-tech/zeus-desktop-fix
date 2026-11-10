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
  echo Adding pip to the ZEUS Python...
  "%PY%" -m ensurepip
  "%PY%" -m pip install pywebview
  if errorlevel 1 (
    echo Could not install the window toolkit.
    pause
    exit /b 2
  )
)
echo Creating the desktop icon...
powershell -NoProfile -Command "$dir=(Get-Location).Path; $d=[Environment]::GetFolderPath('Desktop'); $s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'ZEUS.lnk')); $s.TargetPath=(Join-Path $dir 'FIX_WINDOW.bat'); $s.WorkingDirectory=$dir; $s.WindowStyle=7; $s.Description='ZEUS'; $s.Save()"
echo Starting ZEUS in its own window...
set "PYTHONPATH=%CD%\src"
start "ZEUS Server" /MIN "%PY%" -u -m zeus3.v19.web
"%PY%" "%CD%\zeus_desktop.py"
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8783" ^| findstr "LISTENING"') do taskkill /PID %%P /F >nul 2>&1
exit /b 0
