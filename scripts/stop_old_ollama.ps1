# Run elevated only to stop the verified, idle legacy service. The replacement
# service is started separately without administrator privileges.
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$repairRoot=Join-Path $projectRoot 'data/ollama-repair-20260925'
try {
    $before=Get-Content -LiteralPath (Join-Path $repairRoot 'activation-before.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($before.old_version -ne '0.18.2' -or $before.old_pid -ne 17616) { throw 'Legacy service identity changed' }
    $version=Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/version' -TimeoutSec 3
    $loaded=Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/ps' -TimeoutSec 3
    if ($version.version -ne '0.18.2' -or @($loaded.models).Count -gt 0) { throw 'Legacy service is changed or busy' }
    $owners=@((Get-NetTCPConnection -LocalPort 11434 -State Listen).OwningProcess | Select-Object -Unique)
    if ($owners.Count -ne 1 -or $owners[0] -ne $before.old_pid) { throw 'Port owner changed' }
    $legacy=Get-Process -Id $before.old_pid
    if ($legacy.ProcessName -ne 'ollama' -or $legacy.StartTime.ToString('yyyy-MM-ddTHH:mm:ss') -ne '2026-09-24T23:18:12') { throw 'Process identity changed' }
    Stop-Process -Id $legacy.Id -Force
    if (-not $legacy.WaitForExit(10000)) { throw 'Legacy service did not exit' }
    @{stopped=$true; pid=$legacy.Id; at=(Get-Date).ToUniversalTime().ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $repairRoot 'old-service-stopped.json') -Encoding UTF8
} catch {
    @{stopped=$false; error=$_.Exception.Message; at=(Get-Date).ToUniversalTime().ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $repairRoot 'old-service-stopped.json') -Encoding UTF8
    exit 1
}
