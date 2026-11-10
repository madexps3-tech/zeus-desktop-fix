@echo off
setlocal EnableExtensions
set "ROOT=C:\Zeus V3 world brian\ZEUS_RC11_WINDOWS_RETRY"
set "BASE=https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/53554f970633cd88a7e78376695d5fb99c720d09"
curl -fsSL "%BASE%/zeus_desktop.py" -o "%ROOT%\zeus_desktop.py"
if errorlevel 1 goto fail
cd /d "%ROOT%"
echo Opening the ZEUS window. Leave the black server window open.
"%ROOT%\runtime\python\python.exe" "%ROOT%\zeus_desktop.py"
if errorlevel 1 goto fail
echo Window opened.
pause
exit /b 0
:fail
echo The window did not open. Leave the server window open and send me this text.
pause
exit /b 1
