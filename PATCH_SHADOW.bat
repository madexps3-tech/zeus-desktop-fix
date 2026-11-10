@echo off
setlocal EnableExtensions
cd /d "%~dp0"
powershell -NoProfile -Command "$p=Join-Path (Get-Location).Path 'src\gold_shadow\shadow_book.py'; if(-not (Test-Path -LiteralPath $p)){ Write-Host ('Missing ' + $p); exit 2 }; $t=[IO.File]::ReadAllText($p); $n=$t.Replace('from sweep_shadow import','from gold_shadow.sweep_shadow import'); if($t -eq $n){ Write-Host 'Already fixed.' } else { $enc=New-Object System.Text.UTF8Encoding $false; [IO.File]::WriteAllText($p,$n,$enc); Write-Host 'Fixed the shadow import.' }"
if errorlevel 1 (
  echo The strategy file was not found.
  pause
  exit /b 2
)
echo Close the black ZEUS Server window, then double-click OPEN_ZEUS2.bat again.
pause
exit /b 0
