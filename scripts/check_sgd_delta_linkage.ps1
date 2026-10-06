param([Parameter(Mandatory=$true)][string]$Out)
$ErrorActionPreference='Stop';$Out=[IO.Path]::GetFullPath($Out)
$p=Get-Content -LiteralPath (Join-Path $Out 'table-validation-plan.json') -Raw -Encoding UTF8|ConvertFrom-Json
$cases=(Get-Content -LiteralPath (Join-Path $Out 'singapura-uob-checks.json') -Raw -Encoding UTF8|ConvertFrom-Json).comparisons
$excel=$null;$w=$null;$checks=@()
function Check($name,$actual,$expected){$ok=if($expected -is [string]){[string]$actual -eq $expected}else{$null -ne $actual -and [math]::Abs([double]$actual-[double]$expected) -lt 0.00000000001};if(-not $ok){throw ($name+': '+$actual+' expected '+$expected)};$script:checks+=@{check=$name;passed=$true}}
try{
 $excel=New-Object -ComObject Excel.Application;$excel.Visible=$false;$excel.DisplayAlerts=$false;$excel.EnableEvents=$false;$excel.AutomationSecurity=3;$excel.AskToUpdateLinks=$false
 $w=$excel.Workbooks.Open($p.report_output,0,$true);$s=$w.Worksheets.Item('SGD促销')
 foreach($bank in @('UOB','Singapura Finance')){
  $case=$cases|Where-Object {$_.bank -eq $bank -and $null -ne $_.previous_column -and $_.expected -isnot [string]}|Select-Object -First 1
  $r=[int]$case.row;$rate=$s.Cells.Item($r,3);$formula=$rate.Formula;$prior=$s.Cells.Item($r,[int]$case.previous_column).Value2;$gap=$s.Cells.Item($r,4).Value2
  Check ($bank+' saved change') $s.Range([string]$case.address).Value2 $case.expected
  $rate.Value2=[double]$rate.Value2+0.001;$excel.CalculateFull()
  Check ($bank+' changed input recalculates delta') $s.Range([string]$case.address).Value2 ([double]$case.expected+0.001)
  Check ($bank+' prior history preserved') $s.Cells.Item($r,[int]$case.previous_column).Value2 $prior
  Check ($bank+' missing historical period preserved') $s.Cells.Item($r,4).Value2 ([string]$gap)
  $rate.Formula=$formula;$excel.CalculateFull()
 }
 $missing=$cases|Where-Object {-not $_.previous_column}|Select-Object -First 1
 Check 'No history explicitly labelled' $s.Range([string]$missing.address).Value2 '无上期数据'
 $w.Close($false);$w=$null
 $checks|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $Out 'sgd-delta-linkage-checks.json') -Encoding UTF8
 Write-Output ('SGD formula linkage: '+$checks.Count+' checks passed; changes not saved.')
}finally{if($null -ne $w){$w.Close($false)};if($null -ne $excel){$excel.Quit();[Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel)|Out-Null};[GC]::Collect();[GC]::WaitForPendingFinalizers()}
