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
powershell -NoProfile -Command "$enc=New-Object System.Text.UTF8Encoding $false; $dir=(Get-Location).Path; [IO.File]::WriteAllText((Join-Path $dir 'zeus_wait.py'), 'import time, urllib.request
url="http://127.0.0.1:8783/"
for i in range(70):
    try:
        urllib.request.urlopen(url, timeout=2).close()
        raise SystemExit(0)
    except SystemExit:
        raise
    except Exception:
        if i %% 10 == 9:
            print("Still connecting...", i+1, flush=True)
        time.sleep(1)
print("The engine did not answer. Read the ZEUS Server window.")
raise SystemExit(1)
', $enc); [IO.File]::WriteAllText((Join-Path $dir 'zeus_desktop.py'), 'import time, urllib.request
URL="http://127.0.0.1:8783/"
ok=False
end=time.time()+30
while time.time()<end:
    try:
        urllib.request.urlopen(URL, timeout=2).close()
        ok=True
        break
    except Exception:
        time.sleep(0.4)
if not ok:
    raise SystemExit(1)
print("Opening the ZEUS window.")
import webview
webview.create_window("ZEUS", URL, width=1440, height=900)
webview.start()
', $enc)"
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
