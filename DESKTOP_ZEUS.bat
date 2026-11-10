@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PY=%CD%\runtime\python\python.exe"
set "LOG=%CD%\ZEUS_SERVER_LOG.txt"
set "WLOG=%CD%\ZEUS_WINDOW_LOG.txt"
if not exist "%PY%" (
  echo Put DESKTOP_ZEUS.bat in the ZEUS folder, next to START_ZEUS3_V19_RC.bat
  pause
  exit /b 2
)
echo This does not open Chrome or Edge.
powershell -NoProfile -Command "$p=Join-Path (Get-Location).Path 'src\gold_shadow\shadow_book.py'; if(Test-Path -LiteralPath $p){ $t=[IO.File]::ReadAllText($p); $n=$t.Replace('from sweep_shadow import','from gold_shadow.sweep_shadow import'); if($t -ne $n){ $enc=New-Object System.Text.UTF8Encoding $false; [IO.File]::WriteAllText($p,$n,$enc); Write-Host 'Shadow page fixed.' } else { Write-Host 'Shadow page already fixed.' } }"
powershell -NoProfile -Command "$b='aW1wb3J0IHN5cywgdGltZSwgdHJhY2ViYWNrLCB1cmxsaWIucmVxdWVzdApVUkwgPSAiaHR0cDovLzEyNy4wLjAuMTo4NzgzLyIKCmRlZiB3YWl0X3VudGlsX3VwKHRpbWVvdXQ9MTIwKToKICAgIGVuZCA9IHRpbWUudGltZSgpICsgdGltZW91dAogICAgd2hpbGUgdGltZS50aW1lKCkgPCBlbmQ6CiAgICAgICAgdHJ5OgogICAgICAgICAgICB1cmxsaWIucmVxdWVzdC51cmxvcGVuKFVSTCwgdGltZW91dD0yKS5jbG9zZSgpCiAgICAgICAgICAgIHJldHVybiBUcnVlCiAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjoKICAgICAgICAgICAgdGltZS5zbGVlcCgwLjUpCiAgICByZXR1cm4gRmFsc2UKCmRlZiBtYWluKCk6CiAgICBwcmludCgiV2FpdGluZyBmb3IgdGhlIFpFVVMgZW5naW5lLi4uIikKICAgIGlmIG5vdCB3YWl0X3VudGlsX3VwKCk6CiAgICAgICAgcHJpbnQoIlRoZSBlbmdpbmUgZGlkIG5vdCBhbnN3ZXIuIFJlYWQgWkVVU19TRVJWRVJfTE9HLnR4dCIpCiAgICAgICAgcmV0dXJuIDEKICAgIHByaW50KCJPcGVuaW5nIHRoZSBaRVVTIHdpbmRvdy4gVGhpcyBpcyBub3QgQ2hyb21lIG9yIEVkZ2UuIikKICAgIGltcG9ydCB3ZWJ2aWV3CiAgICB3ZWJ2aWV3LmNyZWF0ZV93aW5kb3coIlpFVVMiLCBVUkwsIHdpZHRoPTE0NDAsIGhlaWdodD05MDApCiAgICB3ZWJ2aWV3LnN0YXJ0KCkKICAgIHByaW50KCJaRVVTIHdpbmRvdyBjbG9zZWQuIikKICAgIHJldHVybiAwCgppZiBfX25hbWVfXyA9PSAiX19tYWluX18iOgogICAgdHJ5OgogICAgICAgIHJhaXNlIFN5c3RlbUV4aXQobWFpbigpKQogICAgZXhjZXB0IFN5c3RlbUV4aXQ6CiAgICAgICAgcmFpc2UKICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgdHJhY2ViYWNrLnByaW50X2V4YygpCiAgICAgICAgcHJpbnQoIldJTkRPVyBGQUlMRUQiKQogICAgICAgIHJhaXNlIFN5c3RlbUV4aXQoMSkK'; [IO.File]::WriteAllBytes((Join-Path (Get-Location).Path 'zeus_desktop.py'), [Convert]::FromBase64String($b))"
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
echo Starting the ZEUS window. Leave this window open.
"%PY%" -u "%CD%\zeus_desktop.py" 1>"%WLOG%" 2>&1
echo.
echo The chart window ended. This text is why:
echo.
type "%WLOG%"
echo.
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8783" ^| findstr "LISTENING"') do taskkill /PID %%P /F >nul 2>&1
pause
exit /b 0
