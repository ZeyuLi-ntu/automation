param([string]$RepairPlanPath)
$ErrorActionPreference='Stop'

function Read-HistoryBoundaryBorders($sheet,$plan) {
    $edges=New-Object System.Collections.Generic.List[object]
    $last=$sheet.UsedRange.Column+$sheet.UsedRange.Columns.Count-1
    foreach($at in @($plan.report_inserts.at | Sort-Object -Unique)) {
        # Insertion can transfer the bottom/top edge away from the old row.
        foreach($side in @(@{row=([int]$at-1);edge=9},@{row=[int]$at;edge=8})) {
            for($col=3;$col -le $last;$col++) {
                $b=$sheet.Cells.Item($side.row,$col).Borders.Item($side.edge)
                $edges.Add(@{row=$side.row;col=$col;edge=$side.edge;line=[int]$b.LineStyle;weight=[int]$b.Weight;color=[double]$b.Color})
            }
        }
    }
    return $edges
}

function Restore-HistoryBoundaryBorders($sheet,$plan,$edges) {
    $changed=0
    foreach($e in $edges) {
        $row=[int]$e.row
        foreach($i in $plan.report_inserts){if([int]$i.at -le [int]$e.row){$row+=[int]$i.count}}
        $shift=if($null -eq $plan.date_column_shift){1}else{[int]$plan.date_column_shift}
        if($shift -eq 0 -and [int]$e.col -eq 3){continue}
        $b=$sheet.Cells.Item($row,([int]$e.col+$shift)).Borders.Item([int]$e.edge)
        if([int]$b.LineStyle -eq $e.line -and ($e.line -eq -4142 -or ([int]$b.Weight -eq $e.weight -and [double]$b.Color -eq $e.color))){continue}
        $b.LineStyle=[int]$e.line
        if($e.line -ne -4142){$b.Weight=[int]$e.weight;$b.Color=[double]$e.color}
        $changed++
    }
    return $changed
}

if($RepairPlanPath) {
    $plan=Get-Content -LiteralPath $RepairPlanPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $out=Split-Path -Parent ([IO.Path]::GetFullPath($RepairPlanPath))
    if($plan.mode -ne 'validation_only' -or (Split-Path -Parent ([IO.Path]::GetFullPath($plan.report_output))) -ne $out){throw 'Only validation outputs may be repaired'}
    if((Get-FileHash -LiteralPath $plan.report_template).Hash.ToLower() -ne $plan.report_sha256){throw 'Source hash changed'}
    $excel=$null;$source=$null;$target=$null
    try {
        $excel=New-Object -ComObject Excel.Application
        $excel.Visible=$false;$excel.DisplayAlerts=$false;$excel.EnableEvents=$false;$excel.AutomationSecurity=3;$excel.AskToUpdateLinks=$false;$excel.ScreenUpdating=$false
        $source=$excel.Workbooks.Open($plan.report_template,0,$true)
        $edges=Read-HistoryBoundaryBorders $source.Worksheets.Item('SGD促销') $plan
        $target=$excel.Workbooks.Open($plan.report_output,0,$false)
        $changed=Restore-HistoryBoundaryBorders $target.Worksheets.Item('SGD促销') $plan $edges
        $excel.CalculateFull();$target.Save()
        Write-Output ('Historical borders restored: '+$changed)
    } finally {
        foreach($book in @($source,$target)){if($null -ne $book){$book.Close($false)}}
        if($null -ne $excel){$excel.Quit();[Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel)|Out-Null}
        [GC]::Collect();[GC]::WaitForPendingFinalizers()
    }
    if((Get-FileHash -LiteralPath $plan.report_template).Hash.ToLower() -ne $plan.report_sha256){throw 'Source hash changed'}
}
