param([Parameter(Mandatory=$true)][string]$PlanPath)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'board_history_layout.ps1')
$p=Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8|ConvertFrom-Json
$excel=$null;$book=$null
try{
 $excel=New-Object -ComObject Excel.Application;$excel.Visible=$false;$excel.DisplayAlerts=$false;$excel.EnableEvents=$false;$excel.AutomationSecurity=3;$excel.AskToUpdateLinks=$false
 $book=$excel.Workbooks.Open($p.report_output,0,$false)
 foreach($h in $p.histories){Format-BoardHistoryRows $book.Worksheets.Item($h.sheet) $h}
 $book.Save();$book.Close($false);$book=$null
}finally{if($null -ne $book){$book.Close($false)};if($null -ne $excel){$excel.Quit();[Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel)|Out-Null};[GC]::Collect();[GC]::WaitForPendingFinalizers()}
