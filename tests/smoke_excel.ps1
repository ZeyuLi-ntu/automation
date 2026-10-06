param([Parameter(Mandatory=$true)][string]$Python,[switch]$ExtraProduct)
$ErrorActionPreference='Stop'
$testRoot=Join-Path ([IO.Path]::GetTempPath()) ('rate-excel-test-'+[guid]::NewGuid().ToString('N'))
New-Item -Path $testRoot -ItemType Directory | Out-Null
$excel=$null;$book=$null;$rainbow=$null
try {
    $excel=New-Object -ComObject Excel.Application
    $excel.Visible=$false;$excel.DisplayAlerts=$false
    $book=$excel.Workbooks.Add()
    $summary=$book.Worksheets.Item(1);$summary.Name='最高报价汇总 '
    $summary.Range('B4').Value2='DEMO_A';$summary.Range('B5').Value2='DEMO_B'
    $summary.Range('F2').Value2=[datetime]::Parse('2026-09-16').ToOADate()
    $sheet=$book.Worksheets.Add();$sheet.Name='SGD促销'
    $sheet.Range('A1').Value2='Fixture';$sheet.Range('A2').Value2='6 Months'
    $sheet.Range('A3').Value2='日期';$sheet.Range('C3').Value2=[datetime]::Parse('2026-09-16').ToOADate()
    $sheet.Range('A5').Value2='DEMO_A';$sheet.Range('B5').Value2='Personal';$sheet.Range('B6').Value2='Premier'
    $sheet.Range('C5').Value2=0.015;$sheet.Range('D5').Value2=0.014
    $sheet.Range('E5').Formula='=C5-D5'
    $sheet.Range('C5:C6').Merge() | Out-Null;$sheet.Range('D5:D6').Merge() | Out-Null
    $sheet.Range('A9').Value2='DEMO_C';$sheet.Range('B9').Value2='Withdrawn fixture'
    $sheet.Range('C9').Value2=0.014
    $other=$book.Worksheets.Add();$other.Name='USD挂牌';$other.Range('A1').Value2='UNCHANGED'
    $book.SaveAs((Join-Path $testRoot 'report-template.xlsx'),51);$book.Close($false);$book=$null
    $rainbow=$excel.Workbooks.Add();$rainbow.Worksheets.Item(1).Name='SGD Promotional Rate'
    $other=$rainbow.Worksheets.Add();$other.Name='Other';$other.Range('A1').Value2='UNCHANGED'
    $rainbow.SaveAs((Join-Path $testRoot 'rainbow-template.xlsx'),51);$rainbow.Close($false);$rainbow=$null
} finally {
    if ($book) {$book.Close($false)};if ($rainbow) {$rainbow.Close($false)}
    if ($excel) {$excel.Quit();[Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel) | Out-Null}
    [GC]::Collect();[GC]::WaitForPendingFinalizers()
}
$options=@();if($ExtraProduct){$options+= '--extra-product'}
& $Python -X utf8 -m tests.smoke_plan $testRoot @options
if ($LASTEXITCODE -ne 0) {throw 'Smoke plan failed'}
& (Join-Path $PSScriptRoot '../scripts/export_excel.ps1') -PlanPath (Join-Path $testRoot 'output/export-plan.json')
& $Python -X utf8 -m tests.smoke_plan $testRoot verify @options
if ($LASTEXITCODE -ne 0) {throw 'Smoke verification failed'}
Write-Output ('Temporary synthetic test files: '+$testRoot)
