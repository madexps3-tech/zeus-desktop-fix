@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PY=%CD%\runtime\python\python.exe"
if not exist "%PY%" (
  echo Put OPEN_ZEUS.bat in the ZEUS folder, next to START_ZEUS3_V19_RC.bat
  pause
  exit /b 2
)
echo Closing any old ZEUS server...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8783" ^| findstr "LISTENING"') do taskkill /PID %%P /F >nul 2>&1
echo Starting ZEUS...
set "PYTHONPATH=%CD%\src"
start "ZEUS Server" /MIN "%PY%" -u -m zeus3.v19.web
set /a N=0
:WAIT
set /a N+=1
if %N% GTR 40 (
  echo ZEUS did not start. Read ZEUS3_V19_STARTUP_LOG.txt in this folder.
  pause
  exit /b 1
)
powershell -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8783/v19/shadow -TimeoutSec 2).StatusCode | Out-Null; exit 0 } catch { exit 1 }"
if errorlevel 1 (
  timeout /t 1 /nobreak >nul
  goto :WAIT
)
set "EDGE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" set "EDGE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" (
  echo Microsoft Edge was not found.
  pause
  exit /b 2
)
start "" "%EDGE%" --app=http://127.0.0.1:8783/v19/shadow
powershell -NoProfile -Command "$dir=(Get-Location).Path; $d=[Environment]::GetFolderPath('Desktop'); $s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'ZEUS.lnk')); $s.TargetPath=(Join-Path $dir 'OPEN_ZEUS.bat'); $s.WorkingDirectory=$dir; $s.WindowStyle=7; $s.Description='ZEUS'; $s.Save()"
echo ZEUS is open in its own window.
echo Leave the black ZEUS Server window open while you use it.
echo Close that black window when you are finished.
pause
exit /b 0
