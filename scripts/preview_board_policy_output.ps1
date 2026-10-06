param([Parameter(Mandatory=$true)][string]$PlanPath)
$ErrorActionPreference='Stop'
$p=Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8|ConvertFrom-Json
$out=Split-Path $PlanPath;$excel=$null;$workbook=$null
function Picture($sheet,$area,$name){$sheet.PageSetup.PrintArea=$area;$sheet.PageSetup.Orientation=2;$sheet.PageSetup.Zoom=$false;$sheet.PageSetup.FitToPagesWide=1;$sheet.PageSetup.FitToPagesTall=1;$sheet.ExportAsFixedFormat(0,(Join-Path $out ($name+'.pdf')),0,$true,$false)}
try{
 $excel=New-Object -ComObject Excel.Application;$excel.Visible=$false;$excel.DisplayAlerts=$false;$excel.EnableEvents=$false;$excel.AutomationSecurity=3;$excel.AskToUpdateLinks=$false
 $workbook=$excel.Workbooks.Open($p.report_output,0,$true)
 foreach($bank in @('HLF','ICBC')){
  $m=$p.matrices|Where-Object {$_.currency -eq 'SGD'};$g=$m.groups|Where-Object {$_.bank -eq $bank}
  Picture $workbook.Worksheets.Item($m.sheet) ('A'+$g.target_row+':S'+([int]$g.target_row+$g.rows.Count-1)) ($bank.ToLower()+'-sgd-policy-preview')
 }
 $m=$p.matrices|Where-Object {$_.currency -eq 'AUD'};$g=$m.groups|Where-Object {$_.bank -eq 'HSBC'}
 Picture $workbook.Worksheets.Item($m.sheet) ('B'+$g.target_row+':N'+([int]$g.target_row+5)) 'hsbc-aud-date-preview'
 foreach($cur in @('USD','CNY')){
  $h=$p.histories|Where-Object {$_.currency -eq $cur};$i=@($h.inserts|Where-Object {$_.bank -eq 'ICBC'})[0]
  if($null -ne $i){$first=$workbook.Worksheets.Item($h.sheet).Cells.Item([int]$i.target_anchor,[int]$h.bank_col);$last=$workbook.Worksheets.Item($h.sheet).Cells.Item(([int]$i.target_row+[int]$i.count-1),([int]$h.current_col+2));Picture $workbook.Worksheets.Item($h.sheet) ($workbook.Worksheets.Item($h.sheet).Range($first,$last).Address()) ('icbc-'+$cur.ToLower()+'-policy-preview')}
 }
 $workbook.Close($false);$workbook=$null
 $workbook=$excel.Workbooks.Open($p.rainbow_output,0,$true)
 foreach($bank in @('HLF','ICBC')){
  $block=$p.rainbow_blocks|Where-Object {$_.currency -eq 'SGD' -and $_.tenor -eq '3M'};$g=$block.groups|Where-Object {$_.bank -eq $bank}
  $s=$workbook.Worksheets.Item($block.sheet);$first=[int]$g.target_row;$last=$first+$g.rows.Count-1
  Picture $s ($s.Range($s.Cells.Item($first,[int]$block.col),$s.Cells.Item($last,[int]$block.col+2)).Address()) ($bank.ToLower()+'-rainbow-policy-preview')
 }
 $workbook.Close($false);$workbook=$null
}finally{if($null -ne $workbook){$workbook.Close($false)};if($null -ne $excel){$excel.Quit();[Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel)|Out-Null};[GC]::Collect();[GC]::WaitForPendingFinalizers()}
