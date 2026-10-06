param([switch]$OldServiceStopped)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$repairRoot = Join-Path $projectRoot 'data/ollama-repair-20260925'
$binary = Join-Path $repairRoot 'v0.34.4/ollama.exe'
$profilePath = Join-Path $projectRoot 'config/ollama.runtime.local.json'
$oldBinary = Join-Path $env:LOCALAPPDATA 'Programs/Ollama/ollama.exe'
$check = Get-Content -LiteralPath (Join-Path $repairRoot 'gpu-check/result.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($check.error -or $check.version.version -ne '0.34.4') { throw 'Staged GPU verification did not pass' }
foreach ($lane in @('text','vision')) {
    if (-not ($check.requests.$lane.runtime | Where-Object { $_.gpu_in_use })) { throw "No GPU evidence for $lane" }
}
if ((Get-AuthenticodeSignature -LiteralPath $binary).Status -ne 'Valid') { throw 'Ollama signature validation failed' }
if ($OldServiceStopped) {
    $receipt=Get-Content -LiteralPath (Join-Path $repairRoot 'old-service-stopped.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not $receipt.stopped) { throw 'Legacy service stop was not verified' }
    if (Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 11434 is occupied again' }
} else {
$oldVersion = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/version' -TimeoutSec 3
if ($oldVersion.version -ne '0.18.2') { throw 'Existing service changed; inspect it before switching' }
$loaded = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/ps' -TimeoutSec 3
if (@($loaded.models).Count -gt 0) { throw 'Existing service has a loaded model; inspect active work before switching' }
$listeners = @(Get-NetTCPConnection -LocalPort 11434 -State Listen)
$ownerIds = @($listeners.OwningProcess | Select-Object -Unique)
if ($ownerIds.Count -ne 1) { throw 'Cannot identify the single service owner' }
$oldProcess = Get-Process -Id $ownerIds[0]
if ($oldProcess.ProcessName -ne 'ollama') { throw 'Port 11434 does not belong to Ollama' }
}
$previousProfile = if (Test-Path -LiteralPath $profilePath) { Get-Content -LiteralPath $profilePath -Raw -Encoding UTF8 } else { $null }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$runtimeDir = Join-Path $projectRoot 'data/local-model'
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
if (-not $OldServiceStopped) {
@{old_pid=$oldProcess.Id; old_version=$oldVersion.version; old_binary=$oldBinary; previous_profile=$previousProfile; new_binary=$binary; at=(Get-Date).ToUniversalTime().ToString('o')} |
    ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $repairRoot 'activation-before.json') -Encoding UTF8
}
$stopped=[bool]$OldServiceStopped
$server=$null
try {
    if (-not $OldServiceStopped) {
    Stop-Process -Id $oldProcess.Id -Force
    $stopped=$true
    $oldProcess.WaitForExit(10000) | Out-Null
    }
    $env:OLLAMA_HOST='127.0.0.1:11434'
    $env:OLLAMA_NO_CLOUD='1'
    $env:OLLAMA_NUM_PARALLEL='1'
    $env:OLLAMA_MAX_LOADED_MODELS='1'
    $stderr = Join-Path $runtimeDir ($stamp+'.err.log')
    $server=Start-Process -FilePath $binary -ArgumentList 'serve' -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeDir ($stamp+'.out.log')) -RedirectStandardError $stderr
    $ready=$null
    for ($attempt=0; $attempt -lt 40; $attempt++) {
        if ($server.HasExited) { throw 'New Ollama exited during startup' }
        try { $ready=Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/version' -TimeoutSec 2; break } catch { Start-Sleep -Milliseconds 500 }
    }
    if ($ready.version -ne '0.34.4') { throw 'New Ollama failed readiness/version verification' }
    @{binary=$binary; version='0.34.4'; model_directory=$env:OLLAMA_MODELS; verified_result=(Join-Path $repairRoot 'gpu-check/result.json')} |
        ConvertTo-Json | Set-Content -LiteralPath $profilePath -Encoding UTF8
    $service=@{pid=$server.Id; binary=$binary; version=$ready.version; started_at=(Get-Date).ToUniversalTime().ToString('o'); stderr=$stderr}
    $service | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimeDir 'service.json') -Encoding UTF8
    $service | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $repairRoot 'activation-after.json') -Encoding UTF8
    $service | ConvertTo-Json
} catch {
    $failure=$_
    if ($server -and -not $server.HasExited) { Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue }
    if ($null -ne $previousProfile) { Set-Content -LiteralPath $profilePath -Value $previousProfile -Encoding UTF8 }
    elseif (Test-Path -LiteralPath $profilePath) { Remove-Item -LiteralPath $profilePath }
    if ($stopped) {
        Start-Process -FilePath $oldBinary -ArgumentList 'serve' -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimeDir ($stamp+'-rollback.out.log')) -RedirectStandardError (Join-Path $runtimeDir ($stamp+'-rollback.err.log')) | Out-Null
    }
    throw $failure
}
