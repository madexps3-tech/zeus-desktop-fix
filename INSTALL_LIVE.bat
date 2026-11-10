@echo off
setlocal EnableExtensions
set "ROOT=C:\Zeus V3 world brian\ZEUS_RC11_WINDOWS_RETRY"
if not exist "%ROOT%\src\zeus3\v19\shadow_book_page.py" (
  echo Could not find %ROOT%
  pause
  exit /b 1
)
echo Installing into %ROOT%
set "BASE=https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/c47cc6d4ff2f04f9bdc9f5dfd0a2fb98c468eccb"
curl -fsSL "%BASE%/mbo_book.py" -o "%ROOT%\src\gold_shadow\mbo_book.py"
if errorlevel 1 goto fail
curl -fsSL "%BASE%/shadow_book_page.py" -o "%ROOT%\src\zeus3\v19\shadow_book_page.py"
if errorlevel 1 goto fail
curl -fsSL "https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/14e1af1db553607f55534189c69246e5a3e65b60/apply_clock.py" -o "%TEMP%\apply_clock.py"
if errorlevel 1 goto fail
python "%TEMP%\apply_clock.py" "%ROOT%"
if errorlevel 1 goto fail
echo.
echo Installed. Close ZEUS, then open it again from the desktop icon.
echo The Shadow page will show GC, NQ and CL. Orders are not sent.
pause
exit /b 0
:fail
echo Install failed. Leave this window open and send me the text above.
pause
exit /b 1
