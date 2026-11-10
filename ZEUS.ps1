$ErrorActionPreference = "Continue"
$root = (Get-Location).Path
$py = Join-Path $root "runtime\python\python.exe"
if (-not (Test-Path -LiteralPath $py)) {
  Write-Host "Put DESKTOP_ZEUS.bat in the ZEUS folder, next to START_ZEUS3_V19_RC.bat"
  exit 2
}
Write-Host "ZEUS desktop. This does not open Chrome or Edge."

$shadow = Join-Path $root "src\gold_shadow\shadow_book.py"
if (Test-Path -LiteralPath $shadow) {
  $t = [IO.File]::ReadAllText($shadow)
  $n = $t.Replace("from sweep_shadow import", "from gold_shadow.sweep_shadow import")
  if ($t -ne $n) {
    $enc = New-Object System.Text.UTF8Encoding $false
    [IO.File]::WriteAllText($shadow, $n, $enc)
    Write-Host "Shadow page fixed."
  }
}

$desktopPy = @"
import sys, time, traceback, urllib.request
URL = "http://127.0.0.1:8783/"

def wait_until_up(timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        try:
            urllib.request.urlopen(URL, timeout=2).close()
            return True
        except Exception:
            time.sleep(0.4)
    return False

def main():
    print("Opening the ZEUS window.")
    if not wait_until_up():
        print("The chart engine stopped before the window opened.")
        return 1
    import webview
    webview.create_window("ZEUS", URL, width=1440, height=900, min_size=(1100, 700))
    webview.start()
    print("ZEUS window closed.")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        print("WINDOW FAILED")
        raise SystemExit(1)
"@
$utf8 = New-Object System.Text.UTF8Encoding $false
[IO.File]::WriteAllText((Join-Path $root "zeus_desktop.py"), $desktopPy, $utf8)

function Stop-Zeus {
  $lines = netstat -ano | Select-String ":8783" | Select-String "LISTENING"
  foreach ($line in $lines) {
    $parts = ($line.ToString() -split "\s+") | Where-Object { $_ -ne "" }
    $procId = $parts[-1]
    if ($procId -match "^\d+$") { taskkill /PID $procId /F | Out-Null }
  }
}
Stop-Zeus

& $py -c "import webview" | Out-Null
if ($LASTEXITCODE -ne 0) {
  Write-Host "Installing the window toolkit. Internet is required this once."
  $getpip = Join-Path $root "get-pip.py"
  Invoke-WebRequest -UseBasicParsing -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getpip
  & $py $getpip --no-warn-script-location
  if ($LASTEXITCODE -ne 0) { Write-Host "Could not add pip."; exit 2 }
  & $py -m pip install pywebview
  if ($LASTEXITCODE -ne 0) { Write-Host "The window toolkit did not install."; exit 2 }
}

$env:PYTHONPATH = Join-Path $root "src"
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like "*zeus3.v19.web*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Write-Host "Starting the chart engine..."
$proc = Start-Process -FilePath $py -ArgumentList "-u","-m","zeus3.v19.web" -WorkingDirectory $root -WindowStyle Minimized -PassThru

$up = $false
for ($i = 1; $i -le 90; $i++) {
  if ($proc.HasExited) { break }
  try {
    $resp = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8783/" -TimeoutSec 2
    if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500) { $up = $true; break }
  } catch {}
  Write-Host "Waiting for the chart engine... $i"
  Start-Sleep -Seconds 1
}

if (-not $up) {
  Write-Host "The chart engine did not start."
  Write-Host "Click the minimized ZEUS Server window on the taskbar and send me the text in it."
  exit 1
}
Write-Host "Chart engine is running. Opening the ZEUS window."
& $py -u (Join-Path $root "zeus_desktop.py")
if ($LASTEXITCODE -ne 0) {
  Write-Host "The ZEUS window did not open. Installing the Windows window component. This does not open the Edge browser."
  $setup = Join-Path $root "MicrosoftEdgeWebview2Setup.exe"
  Invoke-WebRequest -UseBasicParsing -Uri "https://go.microsoft.com/fwlink/p/?LinkId=2124703" -OutFile $setup
  Start-Process -FilePath $setup -ArgumentList "/silent","/install" -Wait
  & $py -u (Join-Path $root "zeus_desktop.py")
  if ($LASTEXITCODE -ne 0) {
    Write-Host "The ZEUS window still did not open."
    exit 1
  }
}
Stop-Zeus
Write-Host "ZEUS closed."
exit 0
