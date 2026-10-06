param([Parameter(Mandatory=$true)][string]$PlanPath)
$ErrorActionPreference='Stop'
$p=Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8|ConvertFrom-Json
$out=Split-Path $PlanPath;$excel=$null;$workbook=$null
function Picture($sheet,$area,$name){$sheet.PageSetup.PrintArea=$area;$sheet.PageSetup.Orientation=2;$sheet.PageSetup.Zoom=$false;$sheet.PageSetup.FitToPagesWide=1;$sheet.PageSetup.FitToPagesTall=1;$sheet.ExportAsFixedFormat(0,(Join-Path $out ($name+'.pdf')),0,$true,$false)}
try{
 $excel=New-Object -ComObject Excel.Application;$excel.Visible=$false;$excel.DisplayAlerts=$false;$excel.EnableEvents=$false;$excel.AutomationSecurity=3;$excel.AskToUpdateLinks=$false
 $workbook=$excel.Workbooks.Open($p.report_output,0,$true)
 $matrix=$p.matrices|Where-Object {$_.currency -eq 'SGD'};$g=$matrix.groups|Where-Object {$_.bank -eq 'OCBC'}
 Picture $workbook.Worksheets.Item($matrix.sheet) ('A'+$g.target_row+':S'+([int]$g.target_row+$g.rows.Count-1)) 'ocbc-sgd-full-preview'
 $h=$p.histories|Where-Object {$_.currency -eq 'USD'};$i=@($h.inserts|Where-Object {$_.label -eq 'OCBC'})[0]
 if($null -ne $i){Picture $workbook.Worksheets.Item($h.sheet) ('B'+$i.target_anchor+':F'+([int]$i.target_row+$i.count-1)) 'ocbc-usd-history-preview'}
 $workbook.Close($false);$workbook=$null
 $workbook=$excel.Workbooks.Open($p.rainbow_output,0,$true)
 foreach($cur in @('SGD','USD')){
  $block=$p.rainbow_blocks|Where-Object {$_.currency -eq $cur -and $_.tenor -eq '3M'};$g=$block.groups|Where-Object {$_.bank -eq 'OCBC'}
  $sheet=$workbook.Worksheets.Item($block.sheet);$first=[int]$g.target_row;$last=$first+$g.rows.Count-1
  $area=$sheet.Range($sheet.Cells.Item($first,[int]$block.col),$sheet.Cells.Item($last,[int]$block.col+2)).Address()
  Picture $sheet $area ('ocbc-'+$cur.ToLower()+'-rainbow-preview')
 }
 $workbook.Close($false);$workbook=$null
}finally{if($null -ne $workbook){$workbook.Close($false)};if($null -ne $excel){$excel.Quit();[Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel)|Out-Null};[GC]::Collect();[GC]::WaitForPendingFinalizers()}
