param([Parameter(Mandatory=$true)][string]$Out)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'fx_notice_layout.ps1')
$Out=[IO.Path]::GetFullPath($Out);$p=Get-Content -LiteralPath (Join-Path $Out 'table-validation-plan.json') -Raw -Encoding UTF8|ConvertFrom-Json
$excel=$null;$w=$null;$checks=@()
function Check($name,$actual,$expected){if([Math]::Abs([double]$actual-[double]$expected) -gt 0.00000000001){throw ($name+': '+$actual+' expected '+$expected)};$script:checks+=@{check=$name;passed=$true}}
try{
 $excel=New-Object -ComObject Excel.Application;$excel.Visible=$false;$excel.DisplayAlerts=$false;$excel.EnableEvents=$false;$excel.AutomationSecurity=3;$excel.AskToUpdateLinks=$false
 $w=$excel.Workbooks.Open($p.report_output,0,$false);Format-FxNoticeRows $w $p;$w.Save()
 $s=$w.Worksheets.Item('USD促销');$inputs=$w.Worksheets.Item($p.input_sheet)
 $boc=$p.details|Where-Object {$_.bank -eq 'BOC' -and $_.currency -eq 'USD' -and $_.tenor_value -eq 1}|Select-Object -First 1
 $input=$inputs.Cells.Item([int]$boc.input_row,9);$old=[double]$input.Value2;$prior=[double]$s.Range('E10').Value2
 Check 'BOC prior date is preserved' $prior 0.037
 Check 'BOC latest minus prior' $s.Range('IO10').Value2 0.001
 $input.Value2=$old+0.001;$excel.CalculateFull()
 Check 'BOC linked rate changes delta' $s.Range('IO10').Value2 0.002
 Check 'BOC prior history unchanged by input' $s.Range('E10').Value2 $prior
 $input.Value2=$old;$excel.CalculateFull()
 $hs=$p.details|Where-Object {$_.bank -eq 'HSBC' -and $_.currency -eq 'USD' -and $_.tenor_value -eq 3 -and $_.audience -like 'premier*'}|Select-Object -First 1
 if($null -eq $hs){throw 'Missing HSBC audience comparison fixture'}
 $formulaId='!I'+$hs.input_row;$h=$p.histories|Where-Object {$_.sheet -eq 'USD促销'}
 $i=$h.inserts|Where-Object {(@($_.rows|Where-Object {$_.formula -like ('*'+$formulaId+'*')})).Count -gt 0}|Select-Object -First 1
 $delta=$s.Cells.Item([int]$i.target_anchor,249);$before=$delta.Value2;$input=$inputs.Cells.Item([int]$hs.input_row,9);$old=$input.Value2
 $input.Value2=0.09;$excel.CalculateFull()
 Check 'Premier change does not override Personal delta' $delta.Value2 $before
 $input.Value2=$old;$excel.CalculateFull()
 $w.Close($false);$w=$null
 $checks|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $Out 'formula-linkage-checks.json') -Encoding UTF8
 Write-Output ('Formula linkage checks passed: '+$checks.Count)
}finally{if($null -ne $w){$w.Close($false)};if($null -ne $excel){$excel.Quit();[Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel)|Out-Null};[GC]::Collect();[GC]::WaitForPendingFinalizers()}
