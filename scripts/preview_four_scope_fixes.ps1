param([Parameter(Mandatory=$true)][string]$Out,[string]$ViewFile='four-scope-previews.json')
$ErrorActionPreference='Stop'
$Out=[IO.Path]::GetFullPath($Out)
$p=Get-Content -LiteralPath (Join-Path $Out 'table-validation-plan.json') -Raw -Encoding UTF8|ConvertFrom-Json
$views=Get-Content -LiteralPath (Join-Path $Out $ViewFile) -Raw -Encoding UTF8|ConvertFrom-Json
$excel=$null;$w=$null
try{
 $excel=New-Object -ComObject Excel.Application;$excel.Visible=$false;$excel.DisplayAlerts=$false;$excel.EnableEvents=$false;$excel.AutomationSecurity=3;$excel.AskToUpdateLinks=$false;$excel.ScreenUpdating=$false
 foreach($v in $views){
  $w=$excel.Workbooks.Open($p.report_output,0,$true);$s=$w.Worksheets.Item([string]$v.sheet)
  $header=2
  if($v.sheet -ne 'SGD挂牌'){
   for($r=[int]$v.start-1;$r -ge 1;$r--){if([string]$s.Cells.Item($r,[int]$v.bank_col).Value2 -in @('Bank','银行','日期')){$header=$r;break}}
  }
  if([int]$v.start -gt $header+1){$s.Rows.Item([string]($header+1)+':'+([int]$v.start-1)).Hidden=$true}
  if($v.compact_history){$keep=2;if($v.keep_history_columns){$keep=[int]$v.keep_history_columns};$s.Range($s.Cells.Item(1,([int]$v.current_col+$keep)),$s.Cells.Item(1,([int]$v.last_col-1))).EntireColumn.Hidden=$true;$s.Columns.Item([int]$v.last_col).Hidden=$false}
  $s.PageSetup.PrintArea=$s.Range($s.Cells.Item($header,[int]$v.bank_col),$s.Cells.Item([int]$v.end,[int]$v.last_col)).Address()
  $s.PageSetup.Zoom=$false;$s.PageSetup.FitToPagesWide=1;$s.PageSetup.FitToPagesTall=1;$s.PageSetup.Orientation=2
  $s.ExportAsFixedFormat(0,(Join-Path $Out ($v.name+'.pdf')),0,$true,$false)
  $w.Close($false);$w=$null
 }
 Write-Output ('Previewed '+$views.Count+' corrected ranges; workbooks unchanged.')
}finally{if($null -ne $w){$w.Close($false)};if($null -ne $excel){$excel.Quit();[Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel)|Out-Null};[GC]::Collect();[GC]::WaitForPendingFinalizers()}
