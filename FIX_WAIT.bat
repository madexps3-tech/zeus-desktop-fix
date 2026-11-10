@echo off
setlocal EnableExtensions
set "ROOT=C:\Zeus V3 world brian\ZEUS_RC11_WINDOWS_RETRY"
set "BASE=https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/53554f970633cd88a7e78376695d5fb99c720d09"
curl -fsSL "%BASE%/zeus_wait.py" -o "%ROOT%\zeus_wait.py"
if errorlevel 1 goto fail
curl -fsSL "%BASE%/zeus_desktop.py" -o "%ROOT%\zeus_desktop.py"
if errorlevel 1 goto fail
echo Wait updated. Open ZEUS once from the desktop icon and leave the window open.
pause
exit /b 0
:fail
echo Update failed.
pause
exit /b 1
