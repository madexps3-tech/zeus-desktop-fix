@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PY=%CD%\runtime\python\python.exe"
set "LOG=%CD%\ZEUS_SERVER_LOG.txt"
if not exist "%PY%" (
  echo Put OPEN_ZEUS.bat in the ZEUS folder, next to START_ZEUS3_V19_RC.bat
  pause
  exit /b 2
)
echo Log into MetaTrader 5 before this window can finish.
echo Closing any old ZEUS server...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8783" ^| findstr "LISTENING"') do taskkill /PID %%P /F >nul 2>&1
echo Starting ZEUS. A blank server window is normal until MetaTrader answers.
set "PYTHONPATH=%CD%\src"
echo ZEUS start %DATE% %TIME%> "%LOG%"
start "ZEUS Server" /D "%CD%" "%PY%" -u -m zeus3.v19.web 1>> "%LOG%" 2>&1
set /a N=0
:WAIT
set /a N+=1
if %N% GTR 90 (
  echo.
  echo ZEUS did not open. The last lines of the log are:
  echo.
  powershell -NoProfile -Command "Get-Content -LiteralPath '%LOG%' -Tail 25"
  echo.
  echo If it says terminal selection, open MetaTrader 5, log in, and run this again.
  pause
  exit /b 1
)
powershell -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8783/ -TimeoutSec 2).StatusCode | Out-Null; exit 0 } catch { exit 1 }"
if errorlevel 1 (
  echo Waiting for ZEUS... %N%
  timeout /t 1 /nobreak >nul
  goto :WAIT
)
set "EDGE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" set "EDGE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" (
  echo Microsoft Edge was not found. ZEUS is running at http://127.0.0.1:8783/v19/shadow
  pause
  exit /b 2
)
start "" "%EDGE%" --app=http://127.0.0.1:8783/v19/shadow
echo ZEUS is open.
echo Leave the ZEUS Server window open while you use it.
pause
exit /b 0
