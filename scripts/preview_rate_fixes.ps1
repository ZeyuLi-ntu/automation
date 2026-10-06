param([Parameter(Mandatory=$true)][string]$Out)
$ErrorActionPreference='Stop'
$Out=[IO.Path]::GetFullPath($Out)
$p=Get-Content -LiteralPath (Join-Path $Out 'table-validation-plan.json') -Raw -Encoding UTF8|ConvertFrom-Json
$excel=$null;$w=$null
function Export-Selection($sheet,$area,$name){
 $sheet.PageSetup.PrintArea=$area;$sheet.PageSetup.Zoom=$false;$sheet.PageSetup.FitToPagesWide=1;$sheet.PageSetup.FitToPagesTall=1;$sheet.PageSetup.Orientation=2
 $sheet.ExportAsFixedFormat(0,(Join-Path $Out ($name+'.pdf')),0,$true,$false)
}
try{
 $excel=New-Object -ComObject Excel.Application;$excel.Visible=$false;$excel.DisplayAlerts=$false;$excel.EnableEvents=$false;$excel.AutomationSecurity=3;$excel.AskToUpdateLinks=$false
 $w=$excel.Workbooks.Open($p.report_output,0,$true)
 $s=$w.Worksheets.Item('SGD挂牌');$s.Rows.Item('3:33').Hidden=$true
 Export-Selection $s 'A2:S35' 'cimb-sgd-fixed'
 $s=$w.Worksheets.Item('USD挂牌');$s.Rows.Item('35:48').Hidden=$true;$s.Columns.Item('F:IQ').Hidden=$true;$s.Columns.Item('IR').Hidden=$false
 Export-Selection $s 'B34:IR52' 'cimb-usd-delta-fixed'
 $s=$w.Worksheets.Item('USD促销');$s.Rows.Item('5:9').Hidden=$true;$s.Columns.Item('F:IN').Hidden=$true;$s.Columns.Item('IO').Hidden=$false
 Export-Selection $s 'B4:IO11' 'boc-usd-fixed'
 Export-Selection $w.Worksheets.Item('最高报价汇总 ') 'B67:P75' 'other-fx-summary-preview'
 $w.Close($false);$w=$null
}finally{if($null -ne $w){$w.Close($false)};if($null -ne $excel){$excel.Quit();[Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel)|Out-Null};[GC]::Collect();[GC]::WaitForPendingFinalizers()}
