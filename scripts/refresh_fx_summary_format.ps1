param([Parameter(Mandatory=$true)][string]$Out)
$ErrorActionPreference='Stop';$Out=[IO.Path]::GetFullPath($Out)
. (Join-Path $PSScriptRoot 'fx_summary_format.ps1')
$p=Get-Content -LiteralPath (Join-Path $Out 'table-validation-plan.json') -Raw -Encoding UTF8|ConvertFrom-Json
$excel=$null;$w=$null
try{
 $excel=New-Object -ComObject Excel.Application;$excel.Visible=$false;$excel.DisplayAlerts=$false;$excel.EnableEvents=$false;$excel.AutomationSecurity=3;$excel.AskToUpdateLinks=$false
 $w=$excel.Workbooks.Open($p.report_output,0,$false);$s=$w.Worksheets.Item(1)
 Format-FxSummary $s
 $ps=$s.PageSetup;$old=@($ps.PrintArea,$ps.Orientation,$ps.Zoom,$ps.FitToPagesWide,$ps.FitToPagesTall)
 try{$ps.PrintArea='B27:I38';$ps.Orientation=2;$ps.Zoom=$false;$ps.FitToPagesWide=1;$ps.FitToPagesTall=1;$s.ExportAsFixedFormat(0,(Join-Path $Out 'fx-summary-preview.pdf'),0,$true,$false)}
 finally{$ps.PrintArea=$old[0];$ps.Orientation=$old[1];$ps.Zoom=$old[2];$ps.FitToPagesWide=$old[3];$ps.FitToPagesTall=$old[4]}
 $w.Save();$w.Close($false);$w=$null
}finally{if($null -ne $w){$w.Close($false)};if($null -ne $excel){$excel.Quit();[Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel)|Out-Null};[GC]::Collect();[GC]::WaitForPendingFinalizers()}
