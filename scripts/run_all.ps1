param([ValidateSet('live','rebuild')][string]$Mode='live',[switch]$Resume,[switch]$Check,[switch]$NoOpen)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false)
$env:PYTHONUTF8='1'
$project=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $project
$python=Join-Path $project '.venv/Scripts/python.exe'
if(-not (Test-Path -LiteralPath $python)){throw 'Python environment missing: .venv'}
$taskArguments=@('-X','utf8','-m','scripts.run_all','--mode',$Mode)
if($Resume){$latest=Get-Content -LiteralPath 'outputs/latest-all-run.json' -Raw -Encoding UTF8|ConvertFrom-Json;$taskArguments+=@('--resume',$latest.workflow)}
if($Check){$taskArguments+='--check'}
if($NoOpen){$taskArguments+='--no-open'}
& $python @taskArguments
exit $LASTEXITCODE
