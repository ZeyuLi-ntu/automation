param([Parameter(Mandatory=$true)][string]$PlanPath,[switch]$PolishOnly)
$ErrorActionPreference='Stop'
$plan=Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8 | ConvertFrom-Json
$out=Split-Path -Parent ([IO.Path]::GetFullPath($PlanPath))
if ($plan.mode -ne 'validation_only' -or $plan.source_pending -le 0) {throw '必须使用待复核试点的副本验证计划'}
foreach ($kind in @('report','rainbow')) {
    $source=$plan.($kind+'_template'); $target=[IO.Path]::GetFullPath($plan.($kind+'_output'))
    if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLower() -ne $plan.($kind+'_sha256')) {throw '模板已变化'}
    if ((Split-Path -Parent $target) -ne $out -or $target -eq [IO.Path]::GetFullPath($source)) {throw '副本必须写入验证目录'}
    if ((Test-Path -LiteralPath $target) -and -not $PolishOnly) {throw '验证副本已经存在；请换新输出目录'}
}
$checks=New-Object System.Collections.Generic.List[object]
function Check([string]$name,[bool]$ok,$detail) {
    $checks.Add(@{name=$name;passed=$ok;detail=$detail})
    if (-not $ok) {throw ('验证失败：'+$name+' '+$detail)}
}
function Equal-Rate($actual,[double]$expected) {return $null -ne $actual -and [math]::Abs([double]$actual-$expected) -lt 0.000000000001}
function Snapshot($sheet,[string]$range,[string]$name) {
    $ps=$sheet.PageSetup
    $old=@{PrintArea=$ps.PrintArea;Orientation=$ps.Orientation;Zoom=$ps.Zoom;FitToPagesWide=$ps.FitToPagesWide;FitToPagesTall=$ps.FitToPagesTall;PrintTitleRows=$ps.PrintTitleRows;PrintTitleColumns=$ps.PrintTitleColumns;BlackAndWhite=$ps.BlackAndWhite}
    try {
        $ps.PrintArea=$range;$ps.Orientation=2;$ps.Zoom=$false;$ps.FitToPagesWide=1;$ps.FitToPagesTall=1
        $ps.PrintTitleRows='';$ps.PrintTitleColumns='';$ps.BlackAndWhite=$false
        $sheet.ExportAsFixedFormat(0,(Join-Path $out ($name+'.pdf')),0,$true,$false)
    } finally {
        $ps.PrintArea=[string]$old.PrintArea;$ps.Orientation=[int]$old.Orientation
        $ps.FitToPagesWide=[int]$old.FitToPagesWide;$ps.FitToPagesTall=[int]$old.FitToPagesTall
        if ($old.Zoom -is [bool]) {$ps.Zoom=[bool]$old.Zoom} else {$ps.Zoom=[int]$old.Zoom}
        $ps.PrintTitleRows=[string]$old.PrintTitleRows;$ps.PrintTitleColumns=[string]$old.PrintTitleColumns
        $ps.BlackAndWhite=[bool]$old.BlackAndWhite
    }
}
function Add-Inputs($book,$inputs) {
    $inputs.Worksheets.Item(1).Copy([Type]::Missing,$book.Worksheets.Item($book.Worksheets.Count))
}
function Set-ValidationText($book,[bool]$isReport) {
    $input=$book.Worksheets.Item($plan.input_sheet)
    for($i=0;$i -lt $plan.source_urls.Count;$i++) {
        $input.Cells.Item(12+$i,1).Value2=[string]([uri]$plan.source_urls[$i]).GetLeftPart([UriPartial]::Path)
    }
    if ($isReport) {
        $s=$book.Worksheets.Item('SGD促销')
        foreach($tier in @(@{row=51;audience='personal';name='Personal Banking'},@{row=52;audience='preferred';name='Priority Banking'},@{row=53;audience='private';name='Priority Private'})) {
            $d=@($plan.details | Where-Object {$_.audience -eq $tier.audience})[0]
            $rate=([double]$d.rate_pct).ToString('0.00',[Globalization.CultureInfo]::InvariantCulture)
            $amount=([double]$d.amount_min).ToString('#,##0',[Globalization.CultureInfo]::InvariantCulture)
            $state=if(Equal-Rate $s.Range('D51').Value2 ([double]$plan.main_pct/100)) {'数字未调整'} else {'利率调整'}
            $line=if($tier.audience -eq 'personal') {'新资金；网上银行/SC Mobile；'+$state+'（待复核）'} else {'新资金；同渠道；身份保持至到期（待复核）'}
            $s.Cells.Item([int]$tier.row,2).Value2=[string]($rate+'% '+$tier.name+' / ≥S$'+$amount+"`n"+$line)
        }
        $s.Range('B51:B53').Rows.RowHeight=36
    }
}
function Verify-Recalculation($book,$excel,[bool]$isReport) {
    $input=$book.Worksheets.Item($plan.input_sheet)
    $input.Range('F4').Value2=0.0171;$input.Range('F5').Value2=0.0221
    $excel.CalculateFull()
    if ($isReport) {
        Check '改变Personal后调研表主报价随之变化' (Equal-Rate $book.Worksheets.Item('SGD促销').Range('C51').Value2 0.0171) '1.71%'
        Check '改变Private后最高汇总随之变化' (Equal-Rate $book.Worksheets.Item('最高报价汇总 ').Range('E10').Value2 0.0221) '2.21%'
    } else {
        $rs=$book.Worksheets.Item('SGD Promotional Rate')
        Check '彩虹表Personal公式重新计算' (Equal-Rate $rs.Range('H18').Value2 0.0171) '1.71%'
        Check '彩虹表Private公式重新计算' (Equal-Rate $rs.Range('H19').Value2 0.0221) '2.21%'
    }
    $input.Range('F4').Value2=[double]$plan.details[0].rate_pct/100
    $input.Range('F5').Value2=[double]$plan.details[1].rate_pct/100
    $excel.CalculateFull()
}
$excel=$null;$report=$null;$rainbow=$null;$inputs=$null;$temp=$null
try {
    $excel=New-Object -ComObject Excel.Application
    $excel.Visible=$false;$excel.DisplayAlerts=$false;$excel.EnableEvents=$false;$excel.AskToUpdateLinks=$false
    $excel.AutomationSecurity=3;$excel.ScreenUpdating=$false
    if ($PolishOnly) {
        foreach($kind in @('report','rainbow')) {
            $temp=$excel.Workbooks.Open($plan.($kind+'_output'),0,$false)
            Set-ValidationText $temp ($kind -eq 'report')
            $excel.CalculateFull()
            if ($kind -eq 'report') {Snapshot $temp.Worksheets.Item('SGD促销') 'A48:F54' 'native-report-after'}
            $temp.Save();$temp.Close($false);$temp=$null
        }
        Write-Output '已缩短来源网址和调研表说明，修复文字裁切。'
        return
    }
    $inputs=$excel.Workbooks.Open((Join-Path $out 'validation-inputs.xlsx'),0,$true)
    $report=$excel.Workbooks.Open($plan.report_template,0,$true)
    $sheet=$report.Worksheets.Item('SGD促销');$summary=$report.Worksheets.Item('最高报价汇总 ')
    Snapshot $sheet 'A48:F54' 'native-report-before'
    Snapshot $summary 'B8:I12' 'native-summary-before'
    $oldValue=$sheet.Range('C51').Value2
    $oldFormat=$sheet.Range('C51').NumberFormat
    $oldFormula=$summary.Range('E4').Formula
    $sheet.Columns.Item(3).Insert() | Out-Null
    $sheet.Columns.Item(3).ColumnWidth=$sheet.Columns.Item(4).ColumnWidth
    # Copy each complete vertical block. Never paste a partial horizontal merge.
    foreach($address in $plan.current_cells) {
        $r=[int]($address -replace '[A-Z]','')
        $source=$sheet.Cells.Item($r,4).MergeArea
        if ($source.Column -ne 4 -or $source.Columns.Count -ne 1) {continue}
        $target=$sheet.Range($sheet.Cells.Item($r,3),$sheet.Cells.Item($r+$source.Rows.Count-1,3))
        $source.Copy() | Out-Null;$target.PasteSpecial(-4122) | Out-Null
        if ($source.Rows.Count -gt 1 -and -not $target.MergeCells) {$target.Merge() | Out-Null}
        $sheet.Cells.Item($r,3).Value2='-'
    }
    $sheet.Range('C3').Value2=[datetime]::ParseExact($plan.as_of,'yyyy-MM-dd',$null).ToOADate()
    $sheet.Range('C3').NumberFormat='yyyy-mm-dd'
    foreach($r in $plan.date_rows) {if ($r -ne 3) {$sheet.Cells.Item([int]$r,3).Formula='=$C$3';$sheet.Cells.Item([int]$r,3).NumberFormat='yyyy-mm-dd'}}
    Add-Inputs $report $inputs
    $sheet.Range('C51').Formula="='插表验证明细'!F4"
    $sheet.Range('C51').NumberFormat=$oldFormat
    $sheet.Range('A1').Value2='新元促销利率市场调研（SCB插表验证，待复核）'
    foreach($tier in @(@{row=51;audience='personal';name='Personal Banking'},@{row=52;audience='preferred';name='Priority Banking'},@{row=53;audience='private';name='Priority Private'})) {
        $d=@($plan.details | Where-Object {$_.audience -eq $tier.audience})[0]
        $rate=([double]$d.rate_pct).ToString('0.00',[Globalization.CultureInfo]::InvariantCulture)
        $amount=([double]$d.amount_min).ToString('#,##0',[Globalization.CultureInfo]::InvariantCulture)
        $status=if($tier.audience -eq 'personal') {'本周已检查；数字未调整（待复核）'} else {'客群身份需保持至到期（待复核）'}
        $sheet.Cells.Item([int]$tier.row,2).Value2=[string]($rate+'% '+$tier.name+' / ≥S$'+$amount+"`n新资金；网上银行或SC Mobile；"+$status)
    }
    $sheet.Range('B51:B53').WrapText=$true;$sheet.Range('B51:B53').Font.Size=11
    $sheet.Range('B51:B53').Rows.RowHeight=36
    # Preserve unrelated summary formulas, currencies, bank positions and report date.
    $summary.Range('B2').Value2='新元促销利率（仅SCB为验证数据）'
    $summary.Range('E10').Formula="=MAX('插表验证明细'!F4:F6)"
    $summary.Range('E10').NumberFormat='0.00%'
    Verify-Recalculation $report $excel $true
    Set-ValidationText $report $true
    Check '新日期列已建立' ($sheet.Range('C3').Value2 -eq [datetime]::Parse($plan.as_of).ToOADate()) $sheet.Range('C3').Text
    Check '9月16日主报价仍在历史列' (Equal-Rate $sheet.Range('D51').Value2 $oldValue) $sheet.Range('D51').Text
    Check '9月16日历史合并保留' ($sheet.Range('D51').MergeArea.Address() -eq '$D$51:$D$53') $sheet.Range('D51').MergeArea.Address()
    Check '本期主报价仍按三行合并展示' ($sheet.Range('C51').MergeArea.Address() -eq '$C$51:$C$53') $sheet.Range('C51').MergeArea.Address()
    Check '其他银行汇总引用跟随旧期右移' ($summary.Range('E4').Formula -eq ($oldFormula -replace '!C60','!D60')) $summary.Range('E4').Formula
    Check 'Personal主报价恢复为1.70%' (Equal-Rate $sheet.Range('C51').Value2 ([double]$plan.main_pct/100)) $sheet.Range('C51').Text
    Check '全客群最高报价为2.00%' (Equal-Rate $summary.Range('E10').Value2 ([double]$plan.highest_pct/100)) $summary.Range('E10').Text
    Check '其他银行新日期单元格标为未核查' ($sheet.Range('C54').Value2 -eq '-') $sheet.Range('C54').Text
    Snapshot $sheet 'A48:F54' 'native-report-after'
    Snapshot $summary 'B8:I12' 'native-summary-after'
    $report.Worksheets.Item('SGD促销').Activate() | Out-Null
    $excel.Goto($sheet.Range('A48'),$true)
    $report.SaveAs($plan.report_output,51)
    $report.Close($false);$report=$null
    $rainbow=$excel.Workbooks.Open($plan.rainbow_template,0,$true)
    $rs=$rainbow.Worksheets.Item('SGD Promotional Rate')
    Snapshot $rs 'G13:I23' 'native-rainbow-before'
    $oldColor=$rs.Range('H18').Interior.Color
    $scb=@($plan.rainbow_blocks | Where-Object {$_.bank -eq 'SCB'})[0]
    Check '并列保持上期SCB位置' ($scb.target_start -eq 18) $scb.target_start
    Add-Inputs $rainbow $inputs
    $rs.Range('A1').Value2='20260924 SCB插表验证（待复核；其他数据沿用20260916）'
    for($i=0;$i -lt 3;$i++) {
        $r=18+$i;$inputrow=4+$i;$d=$plan.details[$i]
        $name=switch($d.audience) {'personal' {'Personal Banking'} 'private' {'Priority Private'} 'preferred' {'Priority Banking'}}
        $rs.Cells.Item($r,8).Formula=("='插表验证明细'!F"+$inputrow)
        $rs.Cells.Item($r,8).NumberFormat='0.00%'
        $rs.Cells.Item($r,9).Value2=[string]($name+' / '+$d.tenor_value+$d.tenor_unit+' / ≥S$'+([double]$d.amount_min).ToString('#,##0',[Globalization.CultureInfo]::InvariantCulture)+" / fresh funds`nOnline Banking or SC Mobile / 待复核")
        $rs.Cells.Item($r,9).WrapText=$true
        $rs.Rows.Item($r).RowHeight=34
    }
    Verify-Recalculation $rainbow $excel $false
    Set-ValidationText $rainbow $false
    Check '彩虹表期限颜色沿用16号模板' ($rs.Range('H18').Interior.Color -eq $oldColor) $oldColor
    Check '彩虹表银行三行合并保留' ($rs.Range('G18').MergeArea.Address() -eq '$G$18:$G$20') $rs.Range('G18').MergeArea.Address()
    Check '彩虹表排序值为Personal而非Private' (Equal-Rate $rs.Range('H18').Value2 ([double]$plan.main_pct/100)) '明细顺序为Personal、Private、Priority'
    Snapshot $rs 'G13:I23' 'native-rainbow-after'
    $rs.Activate() | Out-Null;$excel.Goto($rs.Range('G13'),$true)
    $rainbow.SaveAs($plan.rainbow_output,51)
    $rainbow.Close($false);$rainbow=$null
    # Exercise genuinely inserted rows, then close WITHOUT saving the simulations.
    foreach($case in @(@{row=54;name='新产品';following='BEA'},@{row=111;name='新期限';following='SCB'})) {
        $temp=$excel.Workbooks.Open($plan.report_output,0,$true)
        $s=$temp.Worksheets.Item('SGD促销');$r=[int]$case.row
        $before=$s.Cells.Item($r,1).Value2
        for($c=1;$c -le 243;$c++) {
            $m=$s.Cells.Item($r,$c).MergeArea
            if ($m.Row -lt $r -and $m.Row+$m.Rows.Count -gt $r) {throw '模拟插行位置跨越历史合并块'}
        }
        $summaryBefore=$temp.Worksheets.Item('最高报价汇总 ').Range('E4').Value2
        $s.Rows.Item($r).Insert() | Out-Null
        $s.Cells.Item($r,1).Value2='SCB'
        $s.Cells.Item($r,2).Value2=[string]('仅内存回归测试：'+$case.name)
        $s.Cells.Item($r,3).Value2=0.0123
        $excel.CalculateFull()
        Check ($case.name+'实际插行且原银行块下移') ($s.Cells.Item($r+1,1).Value2 -eq $before) ($r+1)
        Check ($case.name+'未伪造历史利率') ($null -eq $s.Cells.Item($r,4).Value2) '历史列为空'
        Check ($case.name+'插行后其他银行汇总值保持') (Equal-Rate $temp.Worksheets.Item('最高报价汇总 ').Range('E4').Value2 $summaryBefore) '原生公式引用随插行调整'
        $temp.Close($false);$temp=$null
    }
    $checks | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $out 'native-checks.json') -Encoding UTF8
    Write-Output ('Excel原生检查通过：'+$checks.Count+'项；两份副本已保存。')
} catch {
    Write-Output $_.ScriptStackTrace
    Write-Output $_.Exception.Message
    throw
} finally {
    foreach($b in @($temp,$rainbow,$report,$inputs)) {if ($null -ne $b) {$b.Close($false) | Out-Null}}
    if ($null -ne $excel) {$excel.Quit();[Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel) | Out-Null}
    [GC]::Collect();[GC]::WaitForPendingFinalizers()
}
