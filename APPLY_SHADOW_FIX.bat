@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PY=%CD%\runtime\python\python.exe"
if not exist "%PY%" (
  echo Put this file in the ZEUS folder, next to DESKTOP_ZEUS.bat
  pause
  exit /b 2
)
echo Applying the broker clock and Sierra numbers.
powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/25d1a157d2728d0457a4b1d61fb9393dc2dd75f2/shadow_book_page.py' -OutFile '%CD%\src\zeus3\v19\shadow_book_page.py'; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/355b488cb7e21bdbdd9a6cb501057fe2dac3b462/apply_mbo.py' -OutFile '%CD%\apply_mbo.py'"
if errorlevel 1 (
  echo The fix did not download.
  pause
  exit /b 1
)
"%PY%" "%CD%\apply_mbo.py"
echo.
echo Close the ZEUS Server window. Then run DESKTOP_ZEUS.bat once.
pause
