param([string]$Output)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false)
$env:PYTHONUTF8='1'
$project=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $project
if(-not $Output){$latest=Get-Content outputs/latest-workflow.json -Raw -Encoding UTF8|ConvertFrom-Json;$Output=$latest.output}
Write-Host ('准备登记的文件夹：'+$Output)
Write-Host '请先检查两份 Excel。明细中的利率、产品名修正会延续到下一期；不会自动批准下次新采集的数据。'
$answer=Read-Host '检查完成后输入 YES 登记；其他输入退出'
if($answer -cne 'YES'){exit 0}
& (Join-Path $project '.venv/Scripts/python.exe') -X utf8 -m scripts.approve_weekly --output $Output --acknowledgement '用户运行确认入口并输入 YES：已人工检查本期两份工作簿'
exit $LASTEXITCODE
