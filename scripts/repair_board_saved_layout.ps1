param([Parameter(Mandatory=$true)][string]$PlanPath)
$ErrorActionPreference='Stop'
$p=Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8|ConvertFrom-Json
$out=Split-Path $PlanPath;$excel=$null;$w=$null
function Preview($s,$area,$name){
 $ps=$s.PageSetup;$old=@($ps.PrintArea,$ps.Orientation,$ps.Zoom,$ps.FitToPagesWide,$ps.FitToPagesTall)
 try{$ps.PrintArea=$area;$ps.Orientation=2;$ps.Zoom=$false;$ps.FitToPagesWide=1;$ps.FitToPagesTall=1;$s.ExportAsFixedFormat(0,(Join-Path $out ($name+'.pdf')),0,$true,$false)}
 finally{$ps.PrintArea=$old[0];$ps.Orientation=$old[1];$ps.Zoom=$old[2];$ps.FitToPagesWide=$old[3];$ps.FitToPagesTall=$old[4]}
}
try{
 $excel=New-Object -ComObject Excel.Application;$excel.Visible=$false;$excel.DisplayAlerts=$false;$excel.EnableEvents=$false;$excel.AutomationSecurity=3;$excel.AskToUpdateLinks=$false
 $w=$excel.Workbooks.Open($p.report_output,0,$false)
 foreach($m in $p.matrices){
  $s=$w.Worksheets.Item($m.sheet);$bc=[int]$m.bank_col;$ac=[int]$m.amount_col;$nc=[int]$m.note_col
  $s.Columns.Item($ac).ColumnWidth=36;$s.Columns.Item($nc).ColumnWidth=58
  $s.Range($s.Cells.Item(3,$bc),$s.Cells.Item([int]$m.end,$nc)).Font.Size=10
  $s.Range($s.Cells.Item(3,$ac+1),$s.Cells.Item([int]$m.end,[int]$m.last_col)).WrapText=$false
 }
 foreach($h in $p.histories){$s=$w.Worksheets.Item($h.sheet);$s.Columns.Item([int]$h.bank_col+1).ColumnWidth=46}
 $sgd=$p.matrices|Where-Object {$_.currency -eq 'SGD'}
 foreach($bank in @('BEA','Maybank')){
  $g=$sgd.groups|Where-Object {$_.bank -eq $bank};$first=[int]$g.target_row;$last=$first+[Math]::Min(6,$g.rows.Count)-1
  Preview $w.Worksheets.Item($sgd.sheet) ('A'+$first+':S'+$last) ($bank.ToLower()+'-sgd-repair-preview')
 }
 $h=$p.histories|Where-Object {$_.currency -eq 'CNY'}
 Preview $w.Worksheets.Item($h.sheet) 'A1:F20' 'cny-history-preview'
 Preview $w.Worksheets.Item($sgd.sheet) 'A1:S22' 'sgd-board-preview'
 $w.Save();$w.Close($false);$w=$null
 $w=$excel.Workbooks.Open($p.rainbow_output,0,$false)
 foreach($block in $p.rainbow_blocks){
  $s=$w.Worksheets.Item($block.sheet);$c=[int]$block.col
  foreach($g in $block.groups){$n=[int]$g.target_row
   foreach($row in $g.rows){$cell=$s.Cells.Item($n,$c+2);$cell.Value2=([string]$row.amount -replace '\s+',' ');$cell.WrapText=$true;$cell.Font.Size=10;$s.Rows.Item($n).RowHeight=96;$n++}
  }
 }
 $sgdBlock=$p.rainbow_blocks|Where-Object {$_.currency -eq 'SGD' -and $_.tenor -eq '3M'}|Select-Object -First 1
 $g=$sgdBlock.groups|Where-Object {$_.bank -eq 'Maybank'};$first=[int]$g.target_row;$last=$first+$g.rows.Count-1
 Preview $w.Worksheets.Item($sgdBlock.sheet) ('G'+$first+':I'+$last) 'maybank-rainbow-repair-preview'
 Preview $w.Worksheets.Item($sgdBlock.sheet) 'G2:I25' 'sgd-rainbow-preview'
 $w.Save();$w.Close($false);$w=$null
 Write-Output 'Saved layout repaired; run complete workbook readback before publication.'
}finally{if($null -ne $w){$w.Close($false)};if($null -ne $excel){$excel.Quit();[Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel)|Out-Null};[GC]::Collect();[GC]::WaitForPendingFinalizers()}
