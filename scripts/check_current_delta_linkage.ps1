param([Parameter(Mandatory=$true)][string]$Out)
$ErrorActionPreference='Stop';$Out=[IO.Path]::GetFullPath($Out)
$p=Get-Content -LiteralPath (Join-Path $Out 'table-validation-plan.json') -Raw -Encoding UTF8|ConvertFrom-Json
$excel=$null;$w=$null;$checks=@()
function Check($label,$actual,$expected){if($actual -isnot [double] -or [math]::Abs($actual-$expected) -gt 1e-10){throw "$label : $actual != $expected"};$script:checks+=@{name=$label;passed=$true}}
try{
 $excel=New-Object -ComObject Excel.Application;$excel.Visible=$false;$excel.DisplayAlerts=$false;$excel.EnableEvents=$false;$excel.AutomationSecurity=3;$excel.AskToUpdateLinks=$false
 $w=$excel.Workbooks.Open($p.report_output,0,$true)
 foreach($name in @('USD促销','CNY促销')){
  $s=$w.Worksheets.Item($name);$bc=if($name.StartsWith('CNY')){1}else{2};$cc=$bc+2
  $bank=$s.Columns.Item($bc).Find('ICBC',[Type]::Missing,-4163,1);if($null -eq $bank){throw 'ICBC group missing'}
  $area=$bank.MergeArea;$first=[int]$area.Row;$last=$first+[int]$area.Rows.Count-1
  if($last-$first -ne 1){throw 'Expected two ICBC amount rows'}
  $dc=$s.UsedRange.Find('当日增幅',[Type]::Missing,-4163,1).Column;$delta=$s.Cells.Item($first,$dc)
  $s.Range($s.Cells.Item($first,$cc+1),$s.Cells.Item($last,$cc+1)).Value2=0.03
  $s.Cells.Item($first,$cc).Value2=0.01;$s.Cells.Item($last,$cc).Value2=0.05;$excel.CalculateFull()
  Check ($name+' second amount band drives increase') $delta.Value2 0.02
  $s.Cells.Item($last,$cc).Value2=0.025;$excel.CalculateFull();Check ($name+' decrease recalculates') $delta.Value2 -0.005
  $s.Cells.Item($first,$cc).Value2=0.03;$s.Cells.Item($last,$cc).Value2=0.03;$excel.CalculateFull();Check ($name+' exact zero') $delta.Value2 0
  $rule=@($delta.FormatConditions|Where-Object {$_.Type -eq 6})
  if($rule.Count -ne 1){throw 'Expected one icon rule'}
  Check ($name+' zero has no icon') ([double]$rule[0].IconCriteria.Item(2).Icon) -1
 }
 $w.Close($false);$w=$null
 $checks|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $Out 'current-delta-linkage-checks.json') -Encoding UTF8
 Write-Output ('Native delta linkage passed: '+$checks.Count+'; no test edits saved.')
}finally{if($null -ne $w){$w.Close($false)};if($null -ne $excel){$excel.Quit();[Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel)|Out-Null};[GC]::Collect();[GC]::WaitForPendingFinalizers()}
