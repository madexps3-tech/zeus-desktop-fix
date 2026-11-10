@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PY=%CD%\runtime\python\python.exe"
if not exist "%PY%" (
  echo Put this file in the ZEUS folder, next to DESKTOP_ZEUS.bat
  pause
  exit /b 2
)
echo Applying the broker clock and Sierra order-flow fix.
powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/7553243a1f66a8611b89d447245621c52c7a696e/shadow_book_page.py' -OutFile '%CD%\src\zeus3\v19\shadow_book_page.py'; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/e002b75f52da17fac0c99ec76ebb29e36ae51b15/apply_mbo.py' -OutFile '%CD%\apply_mbo.py'"
if errorlevel 1 (
  echo The fix did not download.
  pause
  exit /b 1
)
"%PY%" "%CD%\apply_mbo.py"
echo.
echo Close the ZEUS Server window. Then run DESKTOP_ZEUS.bat once.
echo The first load is slow. Leave both windows open after it appears.
pause
