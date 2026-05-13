param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$backendRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$logDir = Join-Path $repoRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$patterns = @(
    "uvicorn app\.main:app",
    "multiprocessing\.spawn.*app\.main",
    "spawn_main\(parent_pid=.*uvicorn"
)

$targets = Get-CimInstance Win32_Process -Filter "name = 'python.exe'" |
    Where-Object {
        $cmd = $_.CommandLine
        $patterns | Where-Object { $cmd -match $_ }
    }

foreach ($target in $targets) {
    Stop-Process -Id $target.ProcessId -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Seconds 2

$portUsers = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique
foreach ($ownerPid in $portUsers) {
    if ($ownerPid -and $ownerPid -ne 0) {
        Stop-Process -Id $ownerPid -Force -ErrorAction SilentlyContinue
    }
}

Start-Sleep -Seconds 1

Start-Process python `
    -WorkingDirectory $backendRoot `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--reload", "--port", "$Port") `
    -RedirectStandardOutput (Join-Path $logDir "uvicorn.out.log") `
    -RedirectStandardError (Join-Path $logDir "uvicorn.err.log") `
    -WindowStyle Hidden

$deadline = (Get-Date).AddSeconds(20)
do {
    Start-Sleep -Seconds 1
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -eq 200) {
            Write-Output "Backend restarted on http://127.0.0.1:$Port"
            Write-Output $response.Content
            exit 0
        }
    } catch {
        # keep waiting
    }
} while ((Get-Date) -lt $deadline)

Write-Error "Backend did not become healthy within 20 seconds. Check logs/uvicorn.err.log."
