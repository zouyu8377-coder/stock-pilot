param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [switch]$Restart
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"

function Get-PortProcessId {
    param([int]$Port)
    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($connection) {
        return [int]$connection.OwningProcess
    }
    $line = netstat -ano -p tcp | Select-String -Pattern "(:|\.|0\.0\.0\.0:)$Port\s+.*LISTENING" | Select-Object -First 1
    if ($line -and $line.Line -match "\s+(\d+)$") {
        return [int]$Matches[1]
    }
    return $null
}

function Get-FreePort {
    param([int]$PreferredPort)
    $port = $PreferredPort
    while (Get-PortProcessId -Port $port) {
        $port += 1
    }
    return $port
}

function Stop-StockPilotProcess {
    $processes = Get-CimInstance Win32_Process | Where-Object {
        ($_.CommandLine -like "*Stock-Pilot*frontend*" -and ($_.CommandLine -like "*vite*" -or $_.CommandLine -like "*npm run dev*"))
    }
    foreach ($proc in $processes) {
        Write-Host "Stopping existing Stock-Pilot process $($proc.ProcessId)"
        Stop-ProcessTree -ProcessId $proc.ProcessId
    }

    foreach ($port in $BackendPort..($BackendPort + 20)) {
        $backendPortPid = Get-PortProcessId -Port $port
        if ($backendPortPid -and (Test-StockPilotBackend -Port $port)) {
            Write-Host "Stopping Stock-Pilot backend listener $backendPortPid on port $port"
            Stop-ProcessTree -ProcessId $backendPortPid
        }
    }
}

function Test-StockPilotBackend {
    param([int]$Port)
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 1
        return $response.service -eq "stock-copilot-backend"
    } catch {
        return $false
    }
}

function Stop-ProcessTree {
    param([int]$ProcessId)
    $children = Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $ProcessId }
    foreach ($child in $children) {
        Stop-ProcessTree -ProcessId $child.ProcessId
    }
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

if ($Restart) {
    Stop-StockPilotProcess
    Start-Sleep -Seconds 1
}

$actualBackendPort = Get-FreePort -PreferredPort $BackendPort
if ($actualBackendPort -ne $BackendPort) {
    Write-Host "Backend port $BackendPort is in use; using $actualBackendPort instead."
}

$actualFrontendPort = Get-FreePort -PreferredPort $FrontendPort
if ($actualFrontendPort -ne $FrontendPort) {
    Write-Host "Frontend port $FrontendPort is in use; using $actualFrontendPort instead."
}

$corsOrigins = "http://localhost:$actualFrontendPort,http://127.0.0.1:$actualFrontendPort"
$apiBaseUrl = "http://127.0.0.1:$actualBackendPort"

$backendPid = Get-PortProcessId -Port $actualBackendPort
if ($backendPid) {
    Write-Host "Backend port $actualBackendPort is already in use by PID $backendPid."
    Write-Host "Use -Restart to stop existing Stock-Pilot processes first."
} else {
    $backendCommand = "`$env:PYTHONPATH='$BackendDir'; `$env:CORS_ORIGINS='$corsOrigins'; cd '$BackendDir'; python -m uvicorn app.main:app --host 127.0.0.1 --port $actualBackendPort"
    Start-Process powershell -WindowStyle Hidden -ArgumentList "-NoProfile", "-Command", $backendCommand
    Write-Host "Started backend on $apiBaseUrl"
    Write-Host "Allowed frontend origins: $corsOrigins"
}

$frontendCommand = "`$env:VITE_API_BASE_URL='$apiBaseUrl'; cd '$FrontendDir'; npm run dev -- --host 127.0.0.1 --port $actualFrontendPort"
Start-Process powershell -WindowStyle Hidden -ArgumentList "-NoProfile", "-Command", $frontendCommand
Write-Host "Started frontend on http://127.0.0.1:$actualFrontendPort"

Write-Host ""
Write-Host "Stock-Pilot is starting..."
Write-Host "Frontend: http://127.0.0.1:$actualFrontendPort"
Write-Host "Backend:  $apiBaseUrl/health"
