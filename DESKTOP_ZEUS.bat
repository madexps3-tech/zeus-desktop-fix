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
echo This does not open Chrome or Edge.
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
powershell -NoProfile -Command "$p=Join-Path (Get-Location).Path 'zeus_desktop.py'; @'
import sys, time, urllib.request
URL = "http://127.0.0.1:8783/"
def wait_until_up(timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        try:
            urllib.request.urlopen(URL, timeout=2).close()
            return True
        except Exception:
            time.sleep(0.4)
    return False
def main():
    if not wait_until_up():
        print("ZEUS did not start. Read ZEUS_SERVER_LOG.txt")
        return 1
    import webview
    webview.create_window("ZEUS", URL, width=1440, height=900)
    webview.start()
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
'@ | Set-Content -LiteralPath $p -Encoding UTF8"
echo Closing any old ZEUS server...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8783" ^| findstr "LISTENING"') do taskkill /PID %%P /F >nul 2>&1
set "PYTHONPATH=%CD%\src"
echo ZEUS start %DATE% %TIME%> "%LOG%"
start "ZEUS Server" /D "%CD%" /MIN "%PY%" -u -m zeus3.v19.web 1>> "%LOG%" 2>&1
"%PY%" "%CD%\zeus_desktop.py"
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8783" ^| findstr "LISTENING"') do taskkill /PID %%P /F >nul 2>&1
exit /b 0
