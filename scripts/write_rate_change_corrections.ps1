param([Parameter(Mandatory=$true)][string]$PlanPath)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'rate_delta_columns.ps1')
. (Join-Path $PSScriptRoot 'sgd_comparison.ps1')
$p=Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8|ConvertFrom-Json
$excel=$null;$w=$null
try{
 $excel=New-Object -ComObject Excel.Application;$excel.Visible=$false;$excel.DisplayAlerts=$false;$excel.EnableEvents=$false;$excel.AutomationSecurity=3;$excel.AskToUpdateLinks=$false;$excel.ScreenUpdating=$false
 $w=$excel.Workbooks.Open($p.correction_source,0,$true);$w.SaveAs($p.report_output,51)
 $rates=Restore-RateDeltas $w
 $sgd=Restore-SGDTargetDeltas $w
 foreach($entry in $p.correction_bank_merges){
  $s=$w.Worksheets.Item([string]$entry.sheet)
  foreach($address in $entry.ranges){$range=$s.Range([string]$address);if($range.Cells.Item(1,1).MergeArea.Address() -ne $range.Address()){$range.UnMerge()|Out-Null;$range.Merge()|Out-Null}}
 }
 $excel.CalculateFull();$w.Save();$w.Close($false);$w=$null
 @{rates=$rates;sgd=$sgd}|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $p.output 'delta-native.json') -Encoding UTF8
 Write-Output 'Comparison formulas saved. Original rates and historical observations retained.'
}finally{if($null -ne $w){$w.Close($false)};if($null -ne $excel){$excel.Quit();[Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel)|Out-Null};[GC]::Collect();[GC]::WaitForPendingFinalizers()}
