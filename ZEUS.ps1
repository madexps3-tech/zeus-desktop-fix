$ErrorActionPreference = "Continue"
$root = (Get-Location).Path
$py = Join-Path $root "runtime\python\python.exe"
if (-not (Test-Path -LiteralPath $py)) {
  Write-Host "Put DESKTOP_ZEUS.bat in the ZEUS folder, next to START_ZEUS3_V19_RC.bat"
  exit 2
}
Write-Host "ZEUS desktop. This does not open Chrome or Edge."
Write-Host "Close every MetaTrader except MetaTrader 5 Copy. That Copy must be logged in."

$web = Join-Path $root "src\zeus3\v19\web.py"
if (Test-Path -LiteralPath $web) {
  $txt = [IO.File]::ReadAllText($web)
  if ($txt -notlike "*ZEUS engine started*") {
    $txt2 = $txt.Replace("def main() -> int:", "def main() -> int:`r`n    print(`"ZEUS engine started.`", flush=True)")
    if ($txt2 -ne $txt) {
      $enc = New-Object System.Text.UTF8Encoding $false
      [IO.File]::WriteAllText($web, $txt2, $enc)
      Write-Host "Engine will now print as soon as it starts."
    }
  }
}

$shadow = Join-Path $root "src\gold_shadow\shadow_book.py"
if (Test-Path -LiteralPath $shadow) {
  $t = [IO.File]::ReadAllText($shadow)
  $n = $t.Replace("from sweep_shadow import", "from gold_shadow.sweep_shadow import")
  if ($t -ne $n) {
    $enc = New-Object System.Text.UTF8Encoding $false
    [IO.File]::WriteAllText($shadow, $n, $enc)
  }
}

$desktopPy = @"
import sys, time, traceback, urllib.request
URL = "http://127.0.0.1:8783/"

def wait_until_up(timeout=20):
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

Write-Host "Closing old ZEUS engine processes."
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
  $_.CommandLine -like "*zeus3.v19.web*" -or $_.ExecutablePath -like "*ZEUS_RC11_WINDOWS_RETRY\runtime\python*"
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2

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

$terminal = "C:\Users\madex\OneDrive\Desktop\MetaTrader 5 - Copy\terminal64.exe"
if (-not (Test-Path -LiteralPath $terminal)) {
  Write-Host "MetaTrader 5 Copy was not found."
  exit 1
}
$env:PYTHONPATH = Join-Path $root "src"
$env:ZEUS3_MT5_TERMINAL_PATH = $terminal
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $py
$psi.Arguments = "-u -m zeus3.v19.web --terminal-path `"$terminal`""
$psi.WorkingDirectory = $root
$psi.UseShellExecute = $true
$psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Normal
Write-Host "Opening the engine. Its window should say ZEUS engine started within a few seconds."
$proc = [Diagnostics.Process]::Start($psi)

function Test-ZeusPort {
  $client = New-Object System.Net.Sockets.TcpClient
  try {
    $wait = $client.BeginConnect("127.0.0.1", 8783, $null, $null)
    $ok = $wait.AsyncWaitHandle.WaitOne(400, $false)
    if (-not $ok) { return $false }
    $client.EndConnect($wait)
    return $true
  } catch { return $false } finally { $client.Close() }
}

$up = $false
for ($i = 1; $i -le 45; $i++) {
  if ($proc.HasExited) {
    Write-Host "The engine window closed. Send me the text in it."
    exit 1
  }
  if (Test-ZeusPort) { $up = $true; break }
  if (($i % 5) -eq 0) { Write-Host "Waiting for the engine window to say ZEUS engine started... $i" }
  Start-Sleep -Seconds 1
}
if (-not $up) {
  Write-Host "Stopped. The engine did not answer."
  Write-Host "If the other window is still blank, MetaTrader is not answering. Close the other MetaTrader and leave only the Copy logged in."
  if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
  exit 1
}
Write-Host "Chart engine is running. Opening the ZEUS window."
& $py -u (Join-Path $root "zeus_desktop.py")
if ($LASTEXITCODE -ne 0) {
  Write-Host "The ZEUS window did not open."
  exit 1
}
Write-Host "ZEUS is open. Leave the engine window open."
exit 0
