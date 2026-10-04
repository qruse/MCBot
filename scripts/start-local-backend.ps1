# Runs the FastAPI backend on this PC and exposes it through a Cloudflare quick tunnel.
# The tunnel URL changes on every run; open the printed dashboard link to point the
# Cloudflare-hosted frontend at it. Press Ctrl+C to stop both processes.
param(
    [string]$DashboardUrl = $env:MCBOT_DASHBOARD_URL,
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$python = Join-Path $root "backend\.venv\Scripts\python.exe"
$cloudflared = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
if (-not $cloudflared) {
    $cloudflared = Join-Path $HOME "tools\cloudflared.exe"
}

foreach ($exe in @($python, $cloudflared)) {
    if (-not (Test-Path $exe)) {
        throw "Not found: $exe"
    }
}

$logDir = Join-Path $root "tmps"
$backendLog = Join-Path $logDir "backend.log"
$tunnelLog = Join-Path $logDir "tunnel.log"

$backend = Start-Process $python `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", $Port `
    -WorkingDirectory (Join-Path $root "backend") `
    -RedirectStandardError $backendLog -PassThru -WindowStyle Hidden
$tunnel = Start-Process $cloudflared `
    -ArgumentList "tunnel", "--url", "http://127.0.0.1:$Port", "--no-autoupdate" `
    -RedirectStandardError $tunnelLog -PassThru -WindowStyle Hidden

try {
    $tunnelUrl = $null
    for ($i = 0; $i -lt 60 -and -not $tunnelUrl; $i++) {
        Start-Sleep -Seconds 1
        $match = Select-String -Path $tunnelLog -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" `
            -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($match) {
            $tunnelUrl = $match.Matches[0].Value
        }
    }

    if (-not $tunnelUrl) {
        throw "Tunnel URL not found. See $tunnelLog"
    }

    Write-Host ""
    Write-Host "Backend : http://127.0.0.1:$Port"
    Write-Host "Tunnel  : $tunnelUrl"
    if ($DashboardUrl) {
        Write-Host "Open    : $($DashboardUrl.TrimEnd('/'))/?api=$tunnelUrl"
    }
    Write-Host "Logs    : $logDir"
    Write-Host "Press Ctrl+C to stop."

    while (-not $backend.HasExited -and -not $tunnel.HasExited) {
        Start-Sleep -Seconds 2
    }
    Write-Host "A process exited. See logs in $logDir"
}
finally {
    foreach ($process in @($backend, $tunnel)) {
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id -Force
        }
    }
}
