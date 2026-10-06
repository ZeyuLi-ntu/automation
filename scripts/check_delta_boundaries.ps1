param([Parameter(Mandatory=$true)][string]$Out)
$ErrorActionPreference='Stop';$Out=[IO.Path]::GetFullPath($Out)
$p=Get-Content -LiteralPath (Join-Path $Out 'table-validation-plan.json') -Raw -Encoding UTF8|ConvertFrom-Json
$excel=$null;$w=$null;$checks=@()
function Check($name,$actual,$expected){$ok=if($expected -is [string]){[string]$actual -ceq $expected}else{$actual -is [double] -and [math]::Abs($actual-$expected) -lt 1e-12};if(-not $ok){throw "$name : $actual != $expected"};$script:checks+=@{name=$name;passed=$true}}
try{
 $excel=New-Object -ComObject Excel.Application;$excel.Visible=$false;$excel.DisplayAlerts=$false;$excel.EnableEvents=$false;$excel.AutomationSecurity=3;$excel.AskToUpdateLinks=$false
 $w=$excel.Workbooks.Open($p.report_output,0,$true);$s=$w.Worksheets.Item('USD促销');$dc=$s.UsedRange.Find('当日增幅',[Type]::Missing,-4163,1).Column
 foreach($r in @(22,33,63,94)){Check ('Exact zero row '+$r) $s.Cells.Item($r,$dc).Value2 0}
 $cell=$s.Cells.Item(33,$dc);$icons=@($cell.FormatConditions|Where-Object {$_.Type -eq 6})
 if($icons.Count -ne 1){throw 'Expected one comparison icon rule'}
 Check 'Zero has no icon' ([double]$icons[0].IconCriteria.Item(2).Icon) -1
 $prior=$s.Range('E34').Value2;$s.Range('E34').Value2=0.07;$excel.CalculateFull()
 Check 'Higher private-customer history excluded' $cell.Value2 0
 $formula=$s.Range('D40').Formula;$s.Range('D40').Value2=0.041;$excel.CalculateFull()
 Check 'Same-product rate increase recalculates' $cell.Value2 0.001
 $s.Range('D40').Value2=0.039;$excel.CalculateFull();Check 'Same-product rate decrease recalculates' $cell.Value2 -0.001
 $s.Range('D40').Formula=$formula;$s.Range('E34').Value2=$prior
 $sg=$w.Worksheets.Item('SGD促销');Check 'New 24M product explained' $sg.Range('IH204').Value2 '无上期数据'
 $sg.Range('D204').Value2=0.0176;$excel.CalculateFull();Check 'Added valid prior data enables formula' $sg.Range('IH204').Value2 0
 $cn=$w.Worksheets.Item('CNY促销');$cnd=$cn.UsedRange.Find('当日增幅',[Type]::Missing,-4163,1).Column
 $cnrule=$cn.Cells.Item(5,$cnd).FormatConditions|Where-Object {$_.Type -eq 6}|Select-Object -First 1
 Check 'CNY zero has no icon' ([double]$cnrule.IconCriteria.Item(2).Icon) -1
 $w.Close($false);$w=$null
 $checks|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $Out 'delta-boundary-checks.json') -Encoding UTF8
 Write-Output ('Native comparison boundary checks passed: '+$checks.Count+'; no test changes saved.')
}finally{if($null -ne $w){$w.Close($false)};if($null -ne $excel){$excel.Quit();[Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel)|Out-Null};[GC]::Collect();[GC]::WaitForPendingFinalizers()}
