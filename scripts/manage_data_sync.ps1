param(
    [ValidateSet('Install', 'Status', 'Run', 'Remove')]
    [string]$Action = 'Status',
    [string]$PythonPath = ''
)

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Script = Join-Path $Root 'backend\scripts\sync_data.py'
$TaskName = 'StockPilot-ObjectiveDataSync'
if ($Action -eq 'Status') {
    Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue | Select-Object TaskName, State
    Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction SilentlyContinue | Select-Object LastRunTime, LastTaskResult, NextRunTime
    $StatusPath = Join-Path $Root 'backend\data\data_sync\status.json'
    if (Test-Path -LiteralPath $StatusPath) { Get-Content -LiteralPath $StatusPath }
    exit
}
if ($Action -eq 'Remove') {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    exit
}
if (-not $PythonPath) { $PythonPath = (Get-Command python -ErrorAction Stop).Source }
$PythonPath = (Resolve-Path -LiteralPath $PythonPath).Path
if ($Action -eq 'Run') {
    & $PythonPath $Script
    exit $LASTEXITCODE
}
$Windowless = Join-Path (Split-Path $PythonPath) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $Windowless)) { throw 'pythonw.exe is required for hidden scheduled execution; provide the Python installation path.' }
$User = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$TaskAction = New-ScheduledTaskAction -Execute $Windowless -Argument ('"' + $Script + '"') -WorkingDirectory (Join-Path $Root 'backend')
$Periodic = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 30)
$Logon = New-ScheduledTaskTrigger -AtLogOn -User $User
$Principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 25)
$Task = New-ScheduledTask -Action $TaskAction -Trigger @($Periodic, $Logon) -Principal $Principal -Settings $Settings -Description 'Model-free Stock-Pilot data maintenance. No trades or holdings changes. Runs only while this user is logged in; does not wake the computer.'
Register-ScheduledTask -TaskName $TaskName -InputObject $Task -Force | Select-Object TaskName, State
