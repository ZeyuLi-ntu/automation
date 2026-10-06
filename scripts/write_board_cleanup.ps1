param([Parameter(Mandatory=$true)][string]$PlanPath,[Parameter(Mandatory=$true)][string]$ReportOutput)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'rate_delta_columns.ps1')
. (Join-Path $PSScriptRoot 'bank_group_layout.ps1')
. (Join-Path $PSScriptRoot 'sgd_comparison.ps1')
$p=Get-Content -Raw -Encoding UTF8 -LiteralPath $PlanPath|ConvertFrom-Json
$ReportOutput=[IO.Path]::GetFullPath($ReportOutput)
$excel=$null;$w=$null
function Assign($cell,$v){if($v -is [string] -and $v.StartsWith('=')){$cell.Formula=$v}elseif($v -is [double] -or $v -is [int]){$cell.Value2=[double]$v}else{$cell.Value2=[string]$v}}
try{
 $excel=New-Object -ComObject Excel.Application;$excel.Visible=$false;$excel.DisplayAlerts=$false;$excel.EnableEvents=$false;$excel.AutomationSecurity=3;$excel.AskToUpdateLinks=$false;$excel.ScreenUpdating=$false
 $w=$excel.Workbooks.Open($p.report,0,$true);$w.SaveAs($ReportOutput,51)
 $excel.Calculation=-4135
 foreach($h in $p.sheets){
  $s=$w.Worksheets.Item($h.sheet)
  foreach($m in $h.bank_merges){$s.Cells.Item([int]$m.original_start,[int]$h.bank_col).MergeArea.UnMerge()|Out-Null}
  foreach($u in $h.updates){Assign $s.Range([string]$u.address) $u.value}
  foreach($r in @($h.delete_rows|Sort-Object -Descending)){$s.Rows.Item([int]$r).Delete()|Out-Null}
  foreach($m in $h.bank_merges){if([int]$m.end -gt [int]$m.start){$s.Range($s.Cells.Item([int]$m.start,[int]$h.bank_col),$s.Cells.Item([int]$m.end,[int]$h.bank_col)).Merge()|Out-Null};$s.Cells.Item([int]$m.start,[int]$h.bank_col).Value2=[string]$m.label}
  foreach($u in $h.updates){$cell=$s.Range([string]$u.final_address);$cell.NumberFormat='0.0000%';$s.Rows.Item($cell.Row).RowHeight=36}
 }
 if($null -ne $p.sgd_promo){
  $s=$w.Worksheets.Item('SGD促销');$pg=$p.sgd_promo
  foreach($u in $pg.updates){$s.Range([string]$u.address).MergeArea.UnMerge()|Out-Null}
  foreach($u in $pg.updates){Assign $s.Range([string]$u.address) $u.value;$s.Range([string]$u.address).NumberFormat='0.00%'}
  foreach($r in @($pg.delete_rows|Sort-Object -Descending)){$s.Rows.Item([int]$r).Delete()|Out-Null}
 }
 $s=$w.Worksheets.Item('SGD挂牌');$c=$p.cimb_sgd;$s.Cells.Item([int]$c.start,1).MergeArea.UnMerge()|Out-Null
 foreach($u in $c.updates){Assign $s.Range([string]$u.address) $u.value}
 $s.Cells.Item([int]$c.start,2).Value2=[string]$c.label;$s.Cells.Item([int]$c.start,19).Value2=[string]$c.note
 foreach($r in @($c.delete_rows|Sort-Object -Descending)){$s.Rows.Item([int]$r).Delete()|Out-Null}
 $s.Range('A'+$c.start+':A'+([int]$c.start+1)).Merge()|Out-Null;$s.Cells.Item([int]$c.start,1).Value2='CIMB';$s.Rows.Item([int]$c.start).RowHeight=60
 Restore-CleanupBankMerges $w $p
 Format-OrdinaryMaybankBoard $w
 $deltas=Restore-RateDeltas $w
 $sgdDeltas=Restore-SGDTargetDeltas $w
 # Excel may split bank merges while rebuilding comparison formats. Restore
 # group labels after all formatting operations, immediately before saving.
 Restore-CleanupBankMerges $w $p
 $excel.Calculation=-4105;$excel.CalculateFull();$w.Save();$w.Close($false);$w=$null
 $deltas|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $p.output 'delta-rebuild.json') -Encoding UTF8
 $sgdDeltas|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $p.output 'sgd-delta-rebuild.json') -Encoding UTF8
 Write-Output 'Board rows consolidated and daily formulas restored.'
}finally{if($null -ne $w){$w.Close($false)};if($null -ne $excel){$excel.Quit();[Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel)|Out-Null};[GC]::Collect();[GC]::WaitForPendingFinalizers()}
