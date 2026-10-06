param([ValidateSet('live','rebuild')][string]$Mode='live',[string]$Resume,[switch]$NoOpen)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false)
$env:PYTHONUTF8='1'
$project=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $project
$python=Join-Path $project '.venv/Scripts/python.exe'
if(-not (Test-Path -LiteralPath $python)){throw 'Python environment missing: .venv'}
$argsList=@('-X','utf8','-m','scripts.run_market_workflow','--mode',$Mode)
if($Resume){$argsList+=@('--resume',$Resume)}
if($NoOpen){$argsList+='--no-open'}
& $python @argsList
exit $LASTEXITCODE
