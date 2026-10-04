# Runs the FastAPI backend on this PC and exposes it through a Cloudflare quick tunnel.
# Requests through the tunnel need a bearer token; a new one is generated per run unless
# REMOTE_ACCESS_TOKEN is already set. The tunnel URL also changes per run, so open the printed
# dashboard link (it carries both in the URL fragment). Press Ctrl+C to stop both processes.
param(
    [string]$DashboardUrl = $env:MCBOT_DASHBOARD_URL,
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$backendDir = Join-Path $root "backend"
$python = Join-Path $backendDir ".venv\Scripts\python.exe"
$cloudflared = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
if (-not $cloudflared) {
    $cloudflared = Join-Path $HOME "tools\cloudflared.exe"
}

foreach ($exe in @($python, $cloudflared)) {
    if (-not (Test-Path $exe)) {
        throw "Not found: $exe"
    }
}

if (-not $env:REMOTE_ACCESS_TOKEN) {
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $env:REMOTE_ACCESS_TOKEN = [System.BitConverter]::ToString($bytes).Replace("-", "").ToLower()
}

$logDir = Join-Path $root "tmps"
$backendLog = Join-Path $logDir "backend.log"
$tunnelLog = Join-Path $logDir "tunnel.log"

$uvicornArgs = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", $Port)
if (Test-Path (Join-Path $backendDir ".env")) {
    $uvicornArgs += @("--env-file", ".env")
}

# Child processes inherit REMOTE_ACCESS_TOKEN from this session.
$backend = Start-Process $python -ArgumentList $uvicornArgs -WorkingDirectory $backendDir `
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
    Write-Host "Token   : $env:REMOTE_ACCESS_TOKEN"
    if ($DashboardUrl) {
        Write-Host "Open    : $($DashboardUrl.TrimEnd('/'))/#api=$tunnelUrl&token=$env:REMOTE_ACCESS_TOKEN"
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
