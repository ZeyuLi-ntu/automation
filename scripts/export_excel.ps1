param([Parameter(Mandatory=$true)][string]$PlanPath)
$ErrorActionPreference = 'Stop'
$plan = Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($plan.schema_version -ne 1) { throw '不支持的写入计划版本' }
foreach ($pair in @(@($plan.report_template,$plan.report_sha256), @($plan.rainbow_template,$plan.rainbow_sha256))) {
    if ((Get-FileHash -LiteralPath $pair[0] -Algorithm SHA256).Hash.ToLower() -ne $pair[1]) { throw '模板文件已变化，请重新生成计划' }
}
foreach ($target in @($plan.report_output,$plan.rainbow_output)) {
    if (Test-Path -LiteralPath $target) { throw "输出已存在，防止覆盖：$target" }
    if ([IO.Path]::GetFullPath($target) -in @([IO.Path]::GetFullPath($plan.report_template),[IO.Path]::GetFullPath($plan.rainbow_template))) { throw '不能覆盖原始模板' }
}
function Set-Text($cell,[string]$value) { $cell.NumberFormat = '@'; $cell.Value2 = $value }
function Set-Rate($cell,$pct) { $cell.NumberFormat='0.00%'; $cell.Value2=[double]::Parse([string]$pct,[Globalization.CultureInfo]::InvariantCulture)/100.0 }
function Get-Color([string]$hex) { return [Convert]::ToInt32($hex.Substring(0,2),16)+256*[Convert]::ToInt32($hex.Substring(2,2),16)+65536*[Convert]::ToInt32($hex.Substring(4,2),16) }
function Map-Row([int]$row) { return $row + @($plan.new_rows | Where-Object { $_.original_row -le $row }).Count }
function Add-Scope($workbook) {
    $name='本期更新范围'
    try { $sheet=$workbook.Worksheets.Item($name) } catch { $sheet=$workbook.Worksheets.Add(); $sheet.Name=$name }
    Set-Text $sheet.Range('A1') 'SGD促销试点更新说明'
    Set-Text $sheet.Range('A2') $plan.scope_note
    Set-Text $sheet.Range('A3') ('本期日期：'+$plan.as_of+'；运行编号：'+$plan.run_id)
    Set-Text $sheet.Range('A4') '未映射/未采集条目的本期值为-；原历史保留。仅当前SGD范围已通过本次复核。'
    if ($plan.demo) { Set-Text $sheet.Range('A5') '演示数据，不可用于市场报价' }
    $sheet.Columns.Item('A').ColumnWidth=110; $sheet.Range('A1:A5').WrapText=$true
}
function Add-Audit($workbook) {
    $name='本期逐项检查'
    try { $audit=$workbook.Worksheets.Item($name); $audit.Cells.Clear() | Out-Null } catch { $audit=$workbook.Worksheets.Add(); $audit.Name=$name }
    $labels=@('银行','产品','实际期限','展示期限','本期Personal优先值','已发布上期值','检查结论','产品身份','本期日期')
    for ($i=0;$i -lt $labels.Count;$i++) { Set-Text $audit.Cells.Item(1,$i+1) $labels[$i] }
    $r=2
    foreach ($u in $plan.updates) {
        Set-Text $audit.Cells.Item($r,1) $u.bank
        Set-Text $audit.Cells.Item($r,2) $u.product_name
        Set-Text $audit.Cells.Item($r,3) $u.actual_tenor
        Set-Text $audit.Cells.Item($r,4) $u.display_tenor
        if ($null -ne $u.main_pct) { Set-Rate $audit.Cells.Item($r,5) $u.main_pct } else { Set-Text $audit.Cells.Item($r,5) '-' }
        if ($null -ne $u.previous_pct) { Set-Rate $audit.Cells.Item($r,6) $u.previous_pct } else { Set-Text $audit.Cells.Item($r,6) '-' }
        Set-Text $audit.Cells.Item($r,7) $u.status
        Set-Text $audit.Cells.Item($r,8) $u.id
        Set-Text $audit.Cells.Item($r,9) $plan.as_of
        $r++
    }
    $audit.UsedRange.Columns.AutoFit() | Out-Null
}
$excel=$null; $report=$null; $rainbow=$null; $ok=$false
try {
    # A separate, invisible Excel instance. Never attaches to the user's open workbook.
    $excel=New-Object -ComObject Excel.Application
    $excel.Visible=$false; $excel.DisplayAlerts=$false; $excel.AskToUpdateLinks=$false
    $excel.AutomationSecurity=3
    $report=$excel.Workbooks.Open($plan.report_template,0,$true)
    $sheet=$report.Worksheets.Item('SGD促销')
    # Insert only on merge boundaries. Never split a historical merged block.
    foreach ($new in @($plan.new_rows | Sort-Object original_row -Descending)) {
        $r=[int]$new.original_row
        for ($c=1;$c -le $sheet.UsedRange.Columns.Count;$c++) {
            $area=$sheet.Cells.Item($r,$c).MergeArea
            if ($area.Row -lt $r -and ($area.Row+$area.Rows.Count) -gt $r) { throw "第$r 行处于历史合并块内部，请选择银行块边界插入" }
        }
        $sheet.Rows.Item($r).Insert() | Out-Null
    }
    # Native Excel insertion updates formulas, merges and external sheet references.
    $sheet.Columns.Item(3).Insert() | Out-Null
    $sheet.Columns.Item(4).Copy() | Out-Null
    $sheet.Columns.Item(3).PasteSpecial(-4122) | Out-Null
    $last=$sheet.UsedRange.Rows.Count
    $sheet.Range("C4:C$last").UnMerge() | Out-Null
    $sheet.Range("C4:C$last").ClearContents() | Out-Null
    $sheet.Range("C4:C$last").Interior.ColorIndex=-4142
    for ($r=4;$r -le $last;$r++) {
        $a=[string]$sheet.Cells.Item($r,1).Value2
        $b=[string]$sheet.Cells.Item($r,2).Value2
        if ($a -eq '日期') { $sheet.Cells.Item($r,3).Formula='=$C$3' }
        elseif ($b -and $b -ne '全部公开报价') { Set-Text $sheet.Cells.Item($r,3) '-' }
    }
    $sheet.Range('C3').Value2=[datetime]::ParseExact($plan.as_of,'yyyy-MM-dd',$null).ToOADate()
    $sheet.Range('C3').NumberFormat='yyyy-mm-dd'
    # Explicit header in the pilot keeps other currencies' global report date unchanged.
    Set-Text $sheet.Range('A1') ('新元促销利率市场调研（'+$plan.as_of+'，SGD试点）')
    $allWrites=New-Object System.Collections.Generic.List[object]
    foreach ($w in $plan.writes) { $allWrites.Add(@{row=(Map-Row ([int]$w.original_row));value=$w}) }
    $seenNew=@{}
    foreach ($w in @($plan.new_rows | Sort-Object original_row)) {
        $r=[int]$w.original_row
        $before=@($plan.new_rows | Where-Object { $_.original_row -lt $r }).Count
        $index=0; if ($seenNew.ContainsKey($r)) { $index=$seenNew[$r] }; $seenNew[$r]=$index+1
        $allWrites.Add(@{row=($r+$before+$index);value=$w})
    }
    foreach ($item in $allWrites) {
        $r=[int]$item.row; $w=$item.value
        Set-Text $sheet.Cells.Item($r,1) $w.bank
        Set-Text $sheet.Cells.Item($r,2) $w.condition
        if ($null -ne $w.main_pct) { Set-Rate $sheet.Cells.Item($r,3) $w.main_pct }
        else { Set-Text $sheet.Cells.Item($r,3) '-' }
        $sheet.Cells.Item($r,2).WrapText=$true
        $sheet.Rows.Item($r).AutoFit() | Out-Null
        $old=$sheet.Cells.Item($r,4).Value2
        if ($null -eq $old -or $old -is [string] -or [math]::Abs([double]$old-([double]$w.main_pct/100)) -gt 0.000000000001) {
            $sheet.Cells.Item($r,3).Interior.Color=65535
        }
    }
    foreach ($address in $plan.delta_formulas) {
        if ($address -notmatch '^([A-Z]+)([0-9]+)$') { throw 'Invalid delta formula address' }
        $oldCol=0
        foreach ($letter in $Matches[1].ToCharArray()) { $oldCol=26*$oldCol+([int]$letter-64) }
        $r=Map-Row ([int]$Matches[2])
        $now='INDEX('+$r+':'+$r+',1,3)';$previous='INDEX('+$r+':'+$r+',1,4)'
        $sheet.Cells.Item($r,$oldCol+1).Formula=('=IF(COUNT('+$now+','+$previous+')=2,'+$now+'-'+$previous+',"-")')
    }
    foreach($span in $plan.bank_spans){
        $start=Map-Row ([int]$span.start);$end=Map-Row ([int]$span.end)
        foreach($item in $allWrites){if($item.value.bank_anchor -eq $span.start){$start=[math]::Min($start,[int]$item.row);$end=[math]::Max($end,[int]$item.row)}}
        foreach($item in $allWrites){if($item.row -ge $start -and $item.row -le $end -and $item.value.bank -ne $span.bank){throw '新增产品映射跨越另一家银行，请调整插入边界'}}
        $area=$sheet.Range($sheet.Cells.Item($start,1),$sheet.Cells.Item($end,1))
        $area.UnMerge()|Out-Null;$area.ClearContents()|Out-Null
        if($end -gt $start){$area.Merge()|Out-Null}
        Set-Text $sheet.Cells.Item($start,1) $span.bank
    }
    # Pilot summary uses all-audience maxima, not the Personal main value.
    $summary=$report.Worksheets.Item('最高报价汇总 ')
    Set-Text $summary.Range('B2') ('新元促销利率（'+$plan.as_of+'，仅本区更新）')
    $tenors=@('1M','3M','6M','9M','12M','18M','24M')
    for ($r=4;$r -le 23;$r++) {
        $bank=[string]$summary.Cells.Item($r,2).Value2
        $alias=$plan.bank_aliases.PSObject.Properties[$bank]
        if ($null -ne $alias) { $bank=[string]$alias.Value }
        for ($i=0;$i -lt $tenors.Count;$i++) {
            $entry=$plan.highest.PSObject.Properties[$bank+'/'+$tenors[$i]]
            if ($null -ne $entry) { Set-Rate $summary.Cells.Item($r,$i+3) $entry.Value.rate_pct }
            else { Set-Text $summary.Cells.Item($r,$i+3) '-' }
        }
    }
    Add-Scope $report
    Add-Audit $report
    $rainbow=$excel.Workbooks.Open($plan.rainbow_template,0,$true)
    $rs=$rainbow.Worksheets.Item('SGD Promotional Rate')
    $rs.UsedRange.UnMerge() | Out-Null; $rs.UsedRange.ClearContents() | Out-Null
    $rs.UsedRange.Interior.ColorIndex=-4142
    Set-Text $rs.Range('A1') ($plan.as_of+' SGD促销试点')
    for ($i=0;$i -lt $tenors.Count;$i++) {
        $t=$tenors[$i];$col=1+3*$i;$row=3
        Set-Text $rs.Cells.Item(2,$col) $t
        Set-Text $rs.Cells.Item(2,$col+1) 'Promo Rate'
        Set-Text $rs.Cells.Item(2,$col+2) 'Condition'
        $bankLabels=New-Object System.Collections.Generic.List[object]
        foreach ($g in @($plan.groups | Where-Object { $_.display_tenor -eq $t })) {
            $start=$row
            foreach ($d in $g.details) {
                Set-Text $rs.Cells.Item($row,$col) $g.bank
                Set-Rate $rs.Cells.Item($row,$col+1) $d.rate_pct
                $low=if ($d.min_inclusive) { '≥' } else { '>' }
                $high=if ($d.max_inclusive) { '≤' } else { '<' }
                $equivalent=if ($d.amount_is_equivalent) { '等值' } else { '' }
                $min=if ($null -ne $d.amount_min) { $low+$d.amount_min } else { '起存待核实' }
                $max=if ($null -ne $d.amount_max) { $high+$d.amount_max } else { '无明确上限' }
                $condition=$g.product_name+' / 实际'+$d.tenor_value+$d.tenor_unit+' / '+$d.audience+' / '+$equivalent+$d.amount_currency+' '+$min+' '+$max+' / '+$d.channel+' / 新资金:'+$d.fresh_funds+' / '+$d.conditions+' / 有效期:'+$d.valid_from+'至'+$d.valid_to
                Set-Text $rs.Cells.Item($row,$col+2) $condition
                $rs.Cells.Item($row,$col+2).WrapText=$true
                $row++
            }
            if ($row-$start -gt 1) { $rs.Range($rs.Cells.Item($start,$col),$rs.Cells.Item($row-1,$col)).Merge() | Out-Null }
            if($bankLabels.Count -gt 0 -and $bankLabels[$bankLabels.Count-1].bank -eq $g.bank){$bankLabels[$bankLabels.Count-1].end=$row-1}
            else{$bankLabels.Add(@{bank=$g.bank;start=$start;end=$row-1})}
        }
        foreach($label in $bankLabels){
            $area=$rs.Range($rs.Cells.Item([int]$label.start,$col),$rs.Cells.Item([int]$label.end,$col));$area.UnMerge()|Out-Null;$area.ClearContents()|Out-Null
            if($label.end -gt $label.start){$area.Merge()|Out-Null};Set-Text $rs.Cells.Item([int]$label.start,$col) $label.bank
        }
        $rs.Range($rs.Cells.Item(2,$col),$rs.Cells.Item([math]::Max(2,$row-1),$col+2)).Interior.Color=(Get-Color $plan.colors.PSObject.Properties[$t].Value)
        $rs.Columns.Item($col).ColumnWidth=23;$rs.Columns.Item($col+1).ColumnWidth=12;$rs.Columns.Item($col+2).ColumnWidth=48
    }
    $rs.UsedRange.Rows.AutoFit() | Out-Null
    Add-Scope $rainbow
    Add-Audit $rainbow
    $excel.CalculateFull()
    foreach ($item in $allWrites) {
        if ($null -eq $item.value.main_pct) {
            if ($sheet.Cells.Item($item.row,3).Value2 -ne '-') { throw '缺失状态写入核验失败' }
        } elseif ([math]::Abs([double]$sheet.Cells.Item($item.row,3).Value2-[double]$item.value.main_pct/100) -gt 0.000000000001) { throw '写入核验失败' }
    }
    $report.SaveAs($plan.report_output,51)
    $rainbow.SaveAs($plan.rainbow_output,51)
    $ok=$true
    Write-Output ('已保存SGD试点输出：'+$plan.report_output+'；'+$plan.rainbow_output)
} finally {
    if ($null -ne $rainbow) { $rainbow.Close($false) | Out-Null }
    if ($null -ne $report) { $report.Close($false) | Out-Null }
    if ($null -ne $excel) { $excel.Quit(); [Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel) | Out-Null }
    [GC]::Collect(); [GC]::WaitForPendingFinalizers()
}
