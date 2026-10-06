# Forward options as plain arguments; advanced PowerShell parameters reserve --out.
$rateArguments=@($args)
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$ratePython=Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $ratePython)) {
    $ratePython=Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
}
if (-not (Test-Path -LiteralPath $ratePython)) {
    $command=Get-Command python -ErrorAction SilentlyContinue
    if (-not $command) { throw 'Python 3.11+ is required' }
    $ratePython=$command.Source
}
Push-Location $projectRoot
try { & $ratePython -X utf8 -m market_rates @rateArguments; $result=$LASTEXITCODE }
finally { Pop-Location }
exit $result
