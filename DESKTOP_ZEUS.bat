@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PY=%CD%\runtime\python\python.exe"
set "PYTHONPATH=%CD%\src"
if not exist "%PY%" (
  echo Put DESKTOP_ZEUS.bat in the ZEUS folder, next to START_ZEUS3_V19_RC.bat
  pause
  exit /b 2
)
echo Starting ZEUS. This does not open Chrome or Edge.
powershell -NoProfile -Command "$p=Join-Path (Get-Location).Path 'src\gold_shadow\shadow_book.py'; if(Test-Path -LiteralPath $p){$t=[IO.File]::ReadAllText($p); $n=$t.Replace('from sweep_shadow import','from gold_shadow.sweep_shadow import'); if($t -ne $n){$enc=New-Object System.Text.UTF8Encoding $false; [IO.File]::WriteAllText($p,$n,$enc)}}"
powershell -NoProfile -Command "$dir=(Get-Location).Path; [IO.File]::WriteAllBytes((Join-Path $dir 'zeus_wait.py'), [Convert]::FromBase64String('aW1wb3J0IHRpbWUsIHVybGxpYi5yZXF1ZXN0CnVybCA9ICJodHRwOi8vMTI3LjAuMC4xOjg3ODMvIgpmb3IgaSBpbiByYW5nZSg3MCk6CiAgICB0cnk6CiAgICAgICAgdXJsbGliLnJlcXVlc3QudXJsb3Blbih1cmwsIHRpbWVvdXQ9MikuY2xvc2UoKQogICAgICAgIHJhaXNlIFN5c3RlbUV4aXQoMCkKICAgIGV4Y2VwdCBTeXN0ZW1FeGl0OgogICAgICAgIHJhaXNlCiAgICBleGNlcHQgRXhjZXB0aW9uOgogICAgICAgIGlmIGkgJSAxMCA9PSA5OgogICAgICAgICAgICBwcmludCgiU3RpbGwgY29ubmVjdGluZy4uLiIsIGkgKyAxLCBmbHVzaD1UcnVlKQogICAgICAgIHRpbWUuc2xlZXAoMSkKcHJpbnQoIlRoZSBlbmdpbmUgZGlkIG5vdCBhbnN3ZXIuIFJlYWQgdGhlIFpFVVMgU2VydmVyIHdpbmRvdy4iKQpyYWlzZSBTeXN0ZW1FeGl0KDEpCg==')); [IO.File]::WriteAllBytes((Join-Path $dir 'zeus_desktop.py'), [Convert]::FromBase64String('aW1wb3J0IHRpbWUsIHVybGxpYi5yZXF1ZXN0ClVSTCA9ICJodHRwOi8vMTI3LjAuMC4xOjg3ODMvIgpvayA9IEZhbHNlCmVuZCA9IHRpbWUudGltZSgpICsgMzAKd2hpbGUgdGltZS50aW1lKCkgPCBlbmQ6CiAgICB0cnk6CiAgICAgICAgdXJsbGliLnJlcXVlc3QudXJsb3BlbihVUkwsIHRpbWVvdXQ9MikuY2xvc2UoKQogICAgICAgIG9rID0gVHJ1ZQogICAgICAgIGJyZWFrCiAgICBleGNlcHQgRXhjZXB0aW9uOgogICAgICAgIHRpbWUuc2xlZXAoMC40KQppZiBub3Qgb2s6CiAgICByYWlzZSBTeXN0ZW1FeGl0KDEpCnByaW50KCJPcGVuaW5nIHRoZSBaRVVTIHdpbmRvdy4iKQppbXBvcnQgd2Vidmlldwp3ZWJ2aWV3LmNyZWF0ZV93aW5kb3coIlpFVVMiLCBVUkwsIHdpZHRoPTE0NDAsIGhlaWdodD05MDApCndlYnZpZXcuc3RhcnQoKQo='))"
"%PY%" -c "import webview" >nul 2>&1
if errorlevel 1 (
  echo Installing the window toolkit. Internet is required this once.
  powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%CD%\get-pip.py'"
  "%PY%" "%CD%\get-pip.py" --no-warn-script-location
  "%PY%" -m pip install pywebview
  if errorlevel 1 (
    echo The window toolkit did not install.
    pause
    exit /b 2
  )
)
echo Leave MetaTrader 5 Copy logged in.
echo A window titled ZEUS Server will open. Leave it open.
start "ZEUS Server" /D "%CD%" "%PY%" -u -m zeus3.v19.web
"%PY%" "%CD%\zeus_wait.py"
if errorlevel 1 (
  echo The chart did not open. Send me the text in the ZEUS Server window.
  pause
  exit /b 1
)
echo Chart engine is running. Opening the ZEUS window.
"%PY%" "%CD%\zeus_desktop.py"
echo You can close this window. Leave ZEUS Server open while you use the chart.
pause
