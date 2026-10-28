param(
    [ValidateRange(1024, 65535)][int]$Port = 8010,
    [string]$Python = "python",
    [switch]$Build
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$LogDir = Join-Path $Root "logs"
$Url = "http://127.0.0.1:$Port"

if ($Build) {
    Push-Location $Frontend
    try {
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
    } finally { Pop-Location }
}
if (-not (Test-Path -LiteralPath (Join-Path $Frontend "dist/demo.html"))) {
    throw "Demo page is missing. Run this script with -Build after installing frontend dependencies."
}

$Existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($Existing) {
    try { $Health = Invoke-RestMethod "$Url/health" -TimeoutSec 2 }
    catch { throw "Port $Port is occupied. Choose another -Port; no existing process was stopped." }
    if ($Health.service -ne "isolated-collaboration-demo") {
        throw "Port $Port belongs to another service. Choose another -Port."
    }
    Write-Host "Existing isolated demo: $Url/demo.html"
    return
}

$Executable = (Get-Command $Python -CommandType Application -ErrorAction Stop).Source
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$Process = Start-Process -FilePath $Executable -ArgumentList '-m','uvicorn','app.demo_main:app','--host','127.0.0.1','--port',"$Port" -WorkingDirectory $Backend -WindowStyle Hidden -RedirectStandardOutput (Join-Path $LogDir "agent-demo-$Port-out.log") -RedirectStandardError (Join-Path $LogDir "agent-demo-$Port-err.log") -PassThru
for ($Attempt = 0; $Attempt -lt 40; $Attempt++) {
    try {
        $Health = Invoke-RestMethod "$Url/health" -TimeoutSec 1
        if ($Health.service -eq "isolated-collaboration-demo") {
            Write-Host "Isolated demo ready: $Url/demo.html (PID $($Process.Id))"
            return
        }
    } catch { }
    if ($Process.HasExited) { throw "Demo server exited. See $LogDir/agent-demo-$Port-err.log" }
    Start-Sleep -Milliseconds 250
}
throw "Demo did not become ready. See $LogDir/agent-demo-$Port-err.log (PID $($Process.Id))."
