param(
    [string]$HostAddress = "127.0.0.1",
    [int]$ApiPort = 8474
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$ServerPath = Join-Path $PSScriptRoot "toxiproxy\toxiproxy-server.exe"

if (-not (Test-Path $ServerPath)) {
    $Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $Python)) {
        $Python = "python"
    }
    & $Python (Join-Path $PSScriptRoot "download_toxiproxy.py")
}

$LogPath = Join-Path $PSScriptRoot "toxiproxy\toxiproxy-server.log"
$ErrPath = Join-Path $PSScriptRoot "toxiproxy\toxiproxy-server.err.log"
$Process = Start-Process `
    -FilePath $ServerPath `
    -ArgumentList @("-host", $HostAddress, "-port", [string]$ApiPort) `
    -WorkingDirectory (Join-Path $PSScriptRoot "toxiproxy") `
    -RedirectStandardOutput $LogPath `
    -RedirectStandardError $ErrPath `
    -WindowStyle Hidden `
    -PassThru

Write-Host "Toxiproxy server started: PID=$($Process.Id), API=http://$HostAddress`:$ApiPort"
