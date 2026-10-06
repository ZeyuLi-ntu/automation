param([Parameter(Mandatory=$true)][string]$Out)
$ErrorActionPreference='Stop';$Out=[IO.Path]::GetFullPath($Out)
$p=Get-Content -LiteralPath (Join-Path $Out 'table-validation-plan.json') -Raw -Encoding UTF8|ConvertFrom-Json
$excel=$null;$w=$null;$checks=@()
function Check($name,$actual,$expected){if([Math]::Abs([double]$actual-[double]$expected) -gt 0.00000000001){throw ($name+': '+$actual+' expected '+$expected)};$script:checks+=@{check=$name;passed=$true}}
try{
 $excel=New-Object -ComObject Excel.Application;$excel.Visible=$false;$excel.DisplayAlerts=$false;$excel.EnableEvents=$false;$excel.AutomationSecurity=3;$excel.AskToUpdateLinks=$false
 $w=$excel.Workbooks.Open($p.report_output,0,$true);$s=$w.Worksheets.Item('USD促销');$input=$w.Worksheets.Item($p.input_sheet)
 $personal=$p.details|Where-Object {$_.bank -eq 'SCB' -and $_.currency -eq 'USD' -and $_.tenor_value -eq 6 -and $_.audience -eq 'personal'}|Select-Object -First 1
 $premier=$p.details|Where-Object {$_.bank -eq 'SCB' -and $_.currency -eq 'USD' -and $_.tenor_value -eq 6 -and $_.audience -eq 'premier'}|Select-Object -First 1
 $h=$p.histories|Where-Object {$_.sheet -eq 'USD促销'};$entry=$h.existing|Where-Object {$_.input_row -eq $personal.input_row}|Select-Object -First 1
 if($null -eq $entry){throw 'SCB must update an existing customer row'}
 $rate=$s.Range([string]$entry.address);$row=[int]$rate.Row;$dc=[int]$s.Cells.Find('当日增幅').Column;$delta=$s.Cells.Item($row,$dc);$prior=$s.Cells.Item($row,5).Value2
 Check 'SCB Personal previous quote preserved' $prior 0.043
 Check 'SCB unchanged quote has zero change' $delta.Value2 0
 $input.Cells.Item([int]$personal.input_row,9).Value2=0.044;$excel.CalculateFull()
 Check 'SCB Personal new rate linked' $rate.Value2 0.044
 Check 'SCB daily change follows Personal quote' $delta.Value2 0.001
 Check 'SCB dated history remains fixed' $s.Cells.Item($row,5).Value2 $prior
 $input.Cells.Item([int]$premier.input_row,9).Value2=0.09;$excel.CalculateFull()
 Check 'SCB Priority rate does not replace Personal comparison' $delta.Value2 0.001
 $w.Close($false);$w=$null
 $checks|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $Out 'scb-delta-linkage-checks.json') -Encoding UTF8
 Write-Output ('SCB formula linkage: '+$checks.Count+' checks passed; changes not saved.')
}finally{if($null -ne $w){$w.Close($false)};if($null -ne $excel){$excel.Quit();[Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel)|Out-Null};[GC]::Collect();[GC]::WaitForPendingFinalizers()}
