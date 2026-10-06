param([Parameter(Mandatory=$true)][string]$PlanPath,[Parameter(Mandatory=$true)][string]$ReportOutput)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'rate_delta_columns.ps1')
. (Join-Path $PSScriptRoot 'bank_group_layout.ps1')
$p=Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8|ConvertFrom-Json
$backup=$ReportOutput+'.before-delta-refresh.xlsx'
if(-not (Test-Path -LiteralPath $backup)){Copy-Item -LiteralPath $ReportOutput -Destination $backup}
$excel=$null;$w=$null
try{
 $excel=New-Object -ComObject Excel.Application;$excel.Visible=$false;$excel.DisplayAlerts=$false;$excel.EnableEvents=$false;$excel.AutomationSecurity=3;$excel.AskToUpdateLinks=$false;$excel.ScreenUpdating=$false
 $w=$excel.Workbooks.Open($ReportOutput,0,$false)
 $excel.Calculation=-4135
 Restore-CleanupBankMerges $w $p
 Restore-RateDeltas $w|Out-Null
 Restore-CleanupBankMerges $w $p
 $excel.Calculation=-4105;$excel.CalculateFull();$w.Save();$w.Close($false);$w=$null
 Write-Output 'Saved delta formulas refreshed; workbook checks required.'
}finally{if($null -ne $w){$w.Close($false)};if($null -ne $excel){$excel.Quit();[Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel)|Out-Null};[GC]::Collect();[GC]::WaitForPendingFinalizers()}
