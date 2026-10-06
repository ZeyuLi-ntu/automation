param([Parameter(Mandatory=$true)][string]$Out)
$ErrorActionPreference='Stop'
$Out=[IO.Path]::GetFullPath($Out)
$p=Get-Content -LiteralPath (Join-Path $Out 'table-validation-plan.json') -Raw -Encoding UTF8|ConvertFrom-Json
$excel=$null;$w=$null;$checks=@()
function Check($name,$actual,$expected){if([Math]::Abs([double]$actual-[double]$expected) -gt 0.00000000001){throw ($name+': '+$actual+' expected '+$expected)};$script:checks+=@{check=$name;passed=$true}}
try{
 $excel=New-Object -ComObject Excel.Application;$excel.Visible=$false;$excel.DisplayAlerts=$false;$excel.EnableEvents=$false;$excel.AutomationSecurity=3;$excel.AskToUpdateLinks=$false
 $d=$p.details|Where-Object {$_.bank -eq 'HSBC' -and $_.currency -eq 'USD' -and $_.tenor_value -eq 3 -and $_.audience -eq 'personal'}|Select-Object -First 1
 if($null -eq $d){throw 'Missing Personal USD 3M fixture'}
 $h=$p.histories|Where-Object {$_.sheet -eq 'USD促销'};$e=$h.existing|Where-Object {$_.input_row -eq $d.input_row}|Select-Object -First 1
 $w=$excel.Workbooks.Open($p.report_output,0,$true);$s=$w.Worksheets.Item('USD促销');$cell=$s.Range([string]$e.address);$row=[int]$cell.Row
 $delta=$s.Cells.Find('当日增幅');if($null -eq $delta){throw 'Missing daily change column'};$dc=[int]$delta.Column
 $input=$w.Worksheets.Item($p.input_sheet).Cells.Item([int]$d.input_row,9);$old=[double]$input.Value2;$prior=$s.Cells.Item($row,5).Value2;$oldDelta=$s.Cells.Item($row,$dc).Value2
 $summary=$w.Worksheets.Item('最高报价汇总 ');$sr=0
 for($r=29;$r -le 37;$r++){if($summary.Cells.Item($r,2).Value2 -eq 'HSBC'){$sr=$r;break}}
 if($sr -eq 0){throw 'Missing HSBC USD summary row'}
 $input.Value2=$old+0.001;$excel.CalculateFull()
 Check 'HSBC Personal input updates research' $cell.Value2 ($old+0.001)
 Check 'HSBC Personal input updates highest summary' $summary.Cells.Item($sr,4).Value2 ($old+0.001)
 Check 'HSBC 6M unchanged' $summary.Cells.Item($sr,5).Value2 0.029
 Check 'HSBC 12M unchanged' $summary.Cells.Item($sr,7).Value2 0.0275
 if($prior -is [double]){Check 'HSBC history unchanged' $s.Cells.Item($row,5).Value2 $prior;Check 'HSBC delta responds to source input' $s.Cells.Item($row,$dc).Value2 ([double]$oldDelta+0.001)}
 $w.Close($false);$w=$null
 $w=$excel.Workbooks.Open($p.rainbow_output,0,$true);$input=$w.Worksheets.Item($p.input_sheet).Cells.Item([int]$d.input_row,9);$input.Value2=$old+0.001;$excel.CalculateFull()
 $block=$p.rainbow_blocks|Where-Object {$_.currency -eq 'USD' -and $_.tenor -eq '3M'};$group=$block.groups|Where-Object {$_.bank -eq 'HSBC'}
 Check 'HSBC Personal input updates rainbow' $w.Worksheets.Item('USD Rate + Other Currency Rates').Cells.Item([int]$group.target_row,([int]$block.col+1)).Value2 ($old+0.001)
 $w.Close($false);$w=$null
 $checks|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $Out 'scope-linkage-checks.json') -Encoding UTF8
 Write-Output ('Live Excel formula checks passed: '+$checks.Count+'; test changes not saved.')
}finally{if($null -ne $w){$w.Close($false)};if($null -ne $excel){$excel.Quit();[Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel)|Out-Null};[GC]::Collect();[GC]::WaitForPendingFinalizers()}
