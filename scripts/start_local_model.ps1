$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$runtimeConfigPath=Join-Path $projectRoot 'config/ollama.runtime.local.json'
$runtimeConfig=$null
if (Test-Path -LiteralPath $runtimeConfigPath) {
    $runtimeConfig=Get-Content -LiteralPath $runtimeConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $ollamaPath=$runtimeConfig.binary
    if ($runtimeConfig.model_directory) { $env:OLLAMA_MODELS=$runtimeConfig.model_directory }
} else {
    $command=Get-Command ollama -ErrorAction SilentlyContinue
    $ollamaPath=if ($command) { $command.Source } else { Join-Path $env:LOCALAPPDATA 'Programs/Ollama/ollama.exe' }
}
if (-not (Test-Path -LiteralPath $ollamaPath)) { throw 'Install Ollama for Windows first: https://ollama.com/download/windows' }
try {
    $version=Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/version' -TimeoutSec 2
} catch { $version=$null }
if ($version) {
    if ($runtimeConfig.version -and $version.version -ne $runtimeConfig.version) {
        throw ('Port 11434 is occupied by Ollama '+$version.version+'; the verified project runtime is '+$runtimeConfig.version+'. Stop the older Ollama service before starting this script.')
    }
    Write-Output ('Existing local Ollama service: '+$version.version+'. Its settings were not changed.')
    exit 0
}
$runtimeDir=Join-Path $projectRoot 'data/local-model'
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
$env:OLLAMA_HOST='127.0.0.1:11434'
$env:OLLAMA_NO_CLOUD='1'
$env:OLLAMA_NUM_PARALLEL='1'
$env:OLLAMA_MAX_LOADED_MODELS='1'
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
$server=Start-Process -FilePath $ollamaPath -ArgumentList 'serve' -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeDir ($stamp+'.out.log')) -RedirectStandardError (Join-Path $runtimeDir ($stamp+'.err.log'))
$ready=$null
for ($attempt=0; $attempt -lt 30; $attempt++) {
    if ($server.HasExited) { throw 'Ollama exited during startup; inspect the log directory.' }
    try { $ready=Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/version' -TimeoutSec 2; break } catch { Start-Sleep -Milliseconds 500 }
}
if (-not $ready) { throw 'Ollama did not become ready; inspect the log directory.' }
@{pid=$server.Id; binary=$ollamaPath; version=$ready.version; started_at=(Get-Date).ToUniversalTime().ToString('o'); stderr=(Join-Path $runtimeDir ($stamp+'.err.log'))} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimeDir 'service.json') -Encoding UTF8
Write-Output ('Started local-only Ollama '+$ready.version+', PID '+$server.Id+'. No models downloaded.')
Write-Output ('Logs: '+$runtimeDir)
Write-Output ('To download the configured model, run: & "'+$ollamaPath+'" pull qwen3.5:4b')
