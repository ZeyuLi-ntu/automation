param([Parameter(Mandatory=$true)][string]$PlanPath)
$ErrorActionPreference='Stop'
$p=Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8|ConvertFrom-Json
$out=Split-Path -Parent ([IO.Path]::GetFullPath($PlanPath))
$excel=$null;$book=$null
try {
    $excel=New-Object -ComObject Excel.Application
    $excel.Visible=$false;$excel.DisplayAlerts=$false;$excel.EnableEvents=$false;$excel.AskToUpdateLinks=$false;$excel.AutomationSecurity=3
    $book=$excel.Workbooks.Open($p.rainbow_output,0,$true);$s=$book.Worksheets.Item('SGD Promotional Rate')
    foreach($tenor in @('1M','18M','24M')) {
        $g=@($p.rainbow_groups|Where-Object {$_.tenor -eq $tenor})[0]
        $range=$s.Range($s.Cells.Item(2,[int]$g.col),$s.Cells.Item([int]$g.last_row,[int]$g.col+2))
        $s.PageSetup.PrintArea=$range.Address();$s.PageSetup.Orientation=2;$s.PageSetup.Zoom=$false;$s.PageSetup.FitToPagesWide=1;$s.PageSetup.FitToPagesTall=1
        $s.PageSetup.PrintTitleRows='';$s.PageSetup.PrintTitleColumns='';$s.PageSetup.BlackAndWhite=$false
        $s.ExportAsFixedFormat(0,(Join-Path $out ('rainbow-'+$tenor.ToLower()+'.pdf')),0,$true,$false)
    }
    $book.Close($false);$book=$null
    $book=$excel.Workbooks.Open($p.report_output,0,$true);$s=$book.Worksheets.Item('SGD促销')
    foreach($g in @($p.groups|Where-Object {$_.bank -eq 'Maybank'})) {
        $row=[int]$g.report_row
        $last=$row+@($g.input_rows).Count-1
        foreach($col in 1..5){$area=$s.Cells.Item($row,$col).MergeArea;$last=[Math]::Max($last,[int]$area.Row+[int]$area.Rows.Count-1)}
        $range=$s.Range($s.Cells.Item($row,1),$s.Cells.Item($last,5))
        $s.PageSetup.PrintArea=$range.Address();$s.PageSetup.Orientation=2;$s.PageSetup.Zoom=$false;$s.PageSetup.FitToPagesWide=1;$s.PageSetup.FitToPagesTall=1
        $s.PageSetup.PrintTitleRows='';$s.PageSetup.PrintTitleColumns='';$s.PageSetup.BlackAndWhite=$false
        $s.ExportAsFixedFormat(0,(Join-Path $out ('quote-maybank-'+$g.display_tenor.ToLower()+'.pdf')),0,$true,$false)
    }
} finally {
    if($null -ne $book){$book.Close($false)}
    if($null -ne $excel){$excel.Quit();[Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel)|Out-Null}
}
