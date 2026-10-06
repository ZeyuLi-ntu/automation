param([Parameter(Mandatory=$true)][string]$PlanPath)
$ErrorActionPreference='Stop'
$p=Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8|ConvertFrom-Json
$out=Split-Path (Resolve-Path -LiteralPath $PlanPath);$excel=$null;$book=$null
function Picture($sheet,$area,$name){$sheet.PageSetup.PrintArea=$area;$sheet.PageSetup.Orientation=2;$sheet.PageSetup.Zoom=$false;$sheet.PageSetup.FitToPagesWide=1;$sheet.PageSetup.FitToPagesTall=1;$sheet.ExportAsFixedFormat(0,(Join-Path $out ($name+'.pdf')),0,$true,$false)}
try{
 $excel=New-Object -ComObject Excel.Application;$excel.Visible=$false;$excel.DisplayAlerts=$false;$excel.EnableEvents=$false;$excel.AutomationSecurity=3;$excel.AskToUpdateLinks=$false
 $book=$excel.Workbooks.Open($p.report_output,0,$true)
 foreach($item in @(@('USD','DBS'),@('CNY','UOB'),@('CNY','RHB'))){
  $h=$p.histories|Where-Object {$_.currency -eq $item[0]};$g=@($h.inserts|Where-Object {$_.bank -eq $item[1] -and $_.tenor -eq '3M'})[0]
  if($null -eq $g){throw ('Missing history group '+$item)}
  $s=$book.Worksheets.Item($h.sheet);$area=$s.Range($s.Cells.Item([int]$g.target_anchor,[int]$h.bank_col),$s.Cells.Item(([int]$g.target_row+[int]$g.count-1),([int]$h.current_col+2))).Address()
  Picture $s $area ('remaining-'+$item[1]+'-'+$item[0])
 }
 foreach($item in @(@('SGD','CIMB'),@('HKD','HLB'),@('GBP','SBI'))){
  $m=$p.matrices|Where-Object {$_.currency -eq $item[0]};$g=$m.groups|Where-Object {$_.bank -eq $item[1]};$lastcol=if($item[0] -eq 'SGD'){19}else{14}
  $s=$book.Worksheets.Item($m.sheet);$area=$s.Range($s.Cells.Item([int]$g.target_row,1),$s.Cells.Item(([int]$g.target_row+$g.rows.Count-1),$lastcol)).Address()
  Picture $s $area ('remaining-'+$item[1]+'-'+$item[0])
 }
 $book.Close($false);$book=$null
 $book=$excel.Workbooks.Open($p.rainbow_output,0,$true)
 $b=$p.rainbow_blocks|Where-Object {$_.currency -eq 'SGD' -and $_.tenor -eq '3M'};$g=$b.groups|Where-Object {$_.bank -eq 'CIMB'};$s=$book.Worksheets.Item($b.sheet)
 Picture $s ($s.Range($s.Cells.Item([int]$g.target_row,[int]$b.col),$s.Cells.Item(([int]$g.target_row+$g.rows.Count-1),([int]$b.col+2))).Address()) 'remaining-CIMB-rainbow'
 $book.Close($false);$book=$null
}finally{if($null -ne $book){$book.Close($false)};if($null -ne $excel){$excel.Quit();[Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel)|Out-Null};[GC]::Collect();[GC]::WaitForPendingFinalizers()}
