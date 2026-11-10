@echo off
setlocal
set "ROOT="
for %%D in ("C:\Zeus V3 world brian" "C:\ZEUS" "%USERPROFILE%\Desktop") do (
  if exist "%%~D\src\zeus3\v19\shadow_book_page.py" set "ROOT=%%~D"
)
if not defined ROOT (
  for /d %%G in ("C:\Zeus*" "C:\ZEUS*") do (
    if exist "%%~G\src\zeus3\v19\shadow_book_page.py" set "ROOT=%%~G"
  )
)
if not defined ROOT (
  echo Could not find the ZEUS folder. Put this bat inside it and run it again.
  pause
  exit /b 1
)
echo Installing into %ROOT%
set "BASE=https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/c47cc6d4ff2f04f9bdc9f5dfd0a2fb98c468eccb"
curl -fsSL "%BASE%/mbo_book.py" -o "%ROOT%\src\gold_shadow\mbo_book.py"
if errorlevel 1 goto fail
curl -fsSL "%BASE%/shadow_book_page.py" -o "%ROOT%\src\zeus3\v19\shadow_book_page.py"
if errorlevel 1 goto fail
curl -fsSL "https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/ffa4a1b9753b1f2507e73a64a5eebda77e71c802/apply_clock.py" -o "%TEMP%\apply_clock.py"
if errorlevel 1 goto fail
python "%TEMP%\apply_clock.py" "%ROOT%"
if errorlevel 1 goto fail
echo.
echo Installed. Close ZEUS, then open it again from the desktop icon.
echo The Shadow page will show GC, NQ and CL. Orders are not sent.
pause
exit /b 0
:fail
echo Install failed. Leave ZEUS closed and run this bat again.
pause
exit /b 1
