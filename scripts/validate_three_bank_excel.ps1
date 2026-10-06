param([Parameter(Mandatory=$true)][string]$PlanPath,[switch]$Retry)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'preserve_history_borders.ps1')
. (Join-Path $PSScriptRoot 'quote_icon_formats.ps1')
$plan=Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8 | ConvertFrom-Json
$dateShift=if($null -eq $plan.date_column_shift){1}else{[int]$plan.date_column_shift}
$lastCol=if($plan.report_last_col){[int]$plan.report_last_col}else{243}
$rainbowLast=if($plan.rainbow_original_last_row){[int]$plan.rainbow_original_last_row}else{44}
$out=Split-Path -Parent ([IO.Path]::GetFullPath($PlanPath))
if($plan.mode -ne 'validation_only'){throw '仅允许验证副本'}
foreach($k in @('report','rainbow')){
    $target=[IO.Path]::GetFullPath($plan.($k+'_output'))
    if((Split-Path -Parent $target) -ne $out){throw '输出必须是验证目录中的新文件'}
    if(Test-Path -LiteralPath $target){
        if(-not $Retry){throw '输出已存在；本次验证重试请使用 Retry'}
        $archive=[IO.Path]::GetFullPath((Join-Path $out ('attempts/'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+[IO.Path]::GetFileName($target))))
        if(-not $archive.StartsWith($out+[IO.Path]::DirectorySeparatorChar)){throw '重试归档路径越界'}
        New-Item -ItemType Directory -Path (Split-Path -Parent $archive) -Force|Out-Null
        Move-Item -LiteralPath $target -Destination $archive
    }
    if((Get-FileHash -LiteralPath $plan.($k+'_template')).Hash.ToLower() -ne $plan.($k+'_sha256')){throw '原始模板哈希变化'}
}
$checks=New-Object System.Collections.Generic.List[object]
function Check([string]$name,[bool]$ok,$detail){$checks.Add(@{name=$name;passed=$ok;detail=$detail});if(-not $ok){throw ('验证失败：'+$name)}}
function Eq($v,[double]$n){return $null -ne $v -and [math]::Abs([double]$v-$n) -lt 0.00000000001}
function RateFormula($rows){return '=MAX('+ (($rows | ForEach-Object {"'"+$plan.input_sheet+"'!H"+$_}) -join ',') +')'}
function MainFormula($g){$personal=@($g.details|Where-Object {$_.audience -eq 'personal'});if($personal.Count -eq 0){$personal=@($g.details)};return (RateFormula @($personal|ForEach-Object {$_.input_row}))}
function Description($d){
    $short=switch($d.product_id){'rhb-sgd-promo' {'定存促销'} 'cimb-sgd-online' {'普通在线'} 'cimb-wwfd-online' {'Why Wait'} 'cimb-preferred-welcome' {'Preferred迎新'} 'hlf-branch-promo' {'普通促销'} 'hlf-digital-promo' {'Digital'} 'boc-sgd-welcome' {'新客户促销'} default {'定存促销'}}
    $channel=switch($d.channel){'online' {'在线'} 'branch' {'分行'} 'branch_or_online' {'分行/在线'} 'online_banking|sc_mobile' {'网银/SC Mobile'} 'branch_or_mobile' {'分行/手机'} 'branch_or_instruction' {'分行/指令表单'} 'staff_instruction' {'分行/客户经理指令'} 'hlf_digital' {'HLF Digital'} default {'渠道待核'}}
    $audience=switch($d.audience){'premier_elite' {'Premier Elite'} 'premier_wealth' {'Premier(财富/FX)'} 'premier_standard' {'Premier(无财富持仓)'} default {$d.audience}}
    if($d.product_id -eq 'singapura-sgd-online'){$short='Vivid在线定存'}
    $amount=if($null -eq $d.amount_min){'金额待核'}else{'S$'+([double]$d.amount_min).ToString('#,##0.##')}
    if($null -ne $d.amount_max){$amount+=' - '+$(if($d.max_inclusive){''}else{'<'})+([double]$d.amount_max).ToString('#,##0.##')}else{$amount+='起'}
    $fund=if($d.fresh_funds -eq 'yes'){';新资金'}else{''}
    $extra=if($d.bank -eq 'SBI' -and $d.conditions -match '个人多笔合计 < SGD ([\d.]+)'){';个人合计< S$'+([double]$Matches[1]).ToString('#,##0')}else{''}
    if($d.rate_basis -eq 'unknown'){$extra+=';计息口径待核'}
    if($d.reference_quote){$extra+="`n公告期 "+$d.valid_from+'–'+$d.valid_to+'（最新公开参考，公告已截止）'}
    elseif($d.bank -eq 'BOC' -and $d.valid_from -and $d.valid_to){$extra+="`n公告期 "+$d.valid_from+'–'+$d.valid_to}
    if($d.bank -eq 'CITI'){$extra+=';客户资格见明细'}
    if($d.product_id -eq 'singapura-sgd-online'){$extra+=';须有Vivid储蓄账户'}
    if($d.product_id -eq 'singapura-sgd-promo'){$extra+=';须有储蓄账户(新开S$200)'}
    if($d.product_id -eq 'maybank-sgd-bundle'){
        $short='存款组合促销'
        if($d.conditions -match '组合有效年利率：([\d.]+)%'){$extra+="`n组合有效年利率"+$Matches[1]+'%'}
        if($d.conditions -match '附加存款比例：([\d.]+)%'){$extra+=';须另存'+$Matches[1]+'%并锁定'}
    }
    return [string]($short+' / '+$audience+' / '+([double]$d.rate_pct).ToString('0.00')+"%`n"+$d.tenor_value+$d.tenor_unit+'; '+$amount+'; '+$channel+$fund+$extra)
}
function Snapshot($s,[string]$area,[string]$name){
    $p=$s.PageSetup;$old=@{PrintArea=$p.PrintArea;Orientation=$p.Orientation;Zoom=$p.Zoom;FitToPagesWide=$p.FitToPagesWide;FitToPagesTall=$p.FitToPagesTall;PrintTitleRows=$p.PrintTitleRows;PrintTitleColumns=$p.PrintTitleColumns;BlackAndWhite=$p.BlackAndWhite}
    try{$p.PrintArea=$area;$p.Orientation=2;$p.Zoom=$false;$p.FitToPagesWide=1;$p.FitToPagesTall=1;$p.PrintTitleRows='';$p.PrintTitleColumns='';$p.BlackAndWhite=$false;$s.ExportAsFixedFormat(0,(Join-Path $out ($name+'.pdf')),0,$true,$false)}
    finally{$p.PrintArea=[string]$old.PrintArea;$p.Orientation=[int]$old.Orientation;$p.FitToPagesWide=[int]$old.FitToPagesWide;$p.FitToPagesTall=[int]$old.FitToPagesTall;if($old.Zoom -is [bool]){$p.Zoom=[bool]$old.Zoom}else{$p.Zoom=[int]$old.Zoom};$p.PrintTitleRows=[string]$old.PrintTitleRows;$p.PrintTitleColumns=[string]$old.PrintTitleColumns;$p.BlackAndWhite=[bool]$old.BlackAndWhite}
}
function Set-Group($s,$g,[int]$start,[int]$height,[bool]$new){
    $prior=$s.Cells.Item($start,4).Value2
    $s.Range($s.Cells.Item($start,3),$s.Cells.Item($start+$height-1,3)).UnMerge() | Out-Null
    $s.Range($s.Cells.Item($start,3),$s.Cells.Item($start+$height-1,3)).Value2='-'
    $n=$g.details.Count
    $s.Range($s.Cells.Item($start,2),$s.Cells.Item($start+$n-1,2)).UnMerge()|Out-Null
    if($n -gt 1){$s.Range($s.Cells.Item($start,3),$s.Cells.Item($start+$n-1,3)).Merge()|Out-Null}
    $s.Cells.Item($start,3).Formula=(MainFormula $g);$s.Cells.Item($start,3).NumberFormat='0.00%'
    $s.Cells.Item($start,3).Font.Strikethrough=$false
    if($new){
        if($n -gt 1){$s.Range($s.Cells.Item($start,1),$s.Cells.Item($start+$n-1,1)).Merge()|Out-Null}
        $s.Cells.Item($start,1).Value2=[string]$g.bank
    }
    for($j=0;$j -lt $n;$j++){
        $s.Cells.Item($start+$j,2).Value2=[string](Description $g.details[$j]);$s.Cells.Item($start+$j,2).WrapText=$true
        $s.Cells.Item($start+$j,2).Font.Size=11;$s.Rows.Item($start+$j).RowHeight=if($g.details[$j].reference_quote -or $g.bank -eq 'BOC'){72}else{42}
        $s.Cells.Item($start+$j,2).Font.Strikethrough=$false
    }
    $status=if($g.human_reviewed){'已人工确认；沿用已核验采集结果'}elseif($new){'新增独立产品行（待复核）'}elseif($prior -is [double] -and (Eq $prior ([double]$g.main_pct/100))){'本周已检查，数字未调整（待复核）'}else{'本周已检查，数字调整（待复核）'}
    $s.Cells.Item($start,2).Value2=[string]($s.Cells.Item($start,2).Value2+"`n"+$status+'；证据 '+$plan.bank_dates.($g.bank))
    if($plan.manual_notes.($g.id)){$s.Cells.Item($start,2).Value2=[string]($s.Cells.Item($start,2).Value2+"`n人工备注："+$plan.manual_notes.($g.id));$s.Rows.Item($start).RowHeight=90}
    $s.Rows.Item($start).RowHeight=if($plan.manual_notes.($g.id) -or $g.bank -eq 'BOC' -or @($g.details|Where-Object {$_.reference_quote}).Count){90}elseif($g.bank -eq 'Maybank'){80}else{58}
}
$excel=$null;$book=$null;$input=$null;$sourceRainbow=$null
try{
    $excel=New-Object -ComObject Excel.Application;$excel.Visible=$false;$excel.DisplayAlerts=$false;$excel.EnableEvents=$false;$excel.AskToUpdateLinks=$false;$excel.AutomationSecurity=3;$excel.ScreenUpdating=$false
    $input=$excel.Workbooks.Open((Join-Path $out 'validation-inputs.xlsx'),0,$true)
    $book=$excel.Workbooks.Open($plan.report_template,0,$true);$s=$book.Worksheets.Item('SGD促销')
    $historyBorders=Read-HistoryBoundaryBorders $s $plan
    Snapshot $s 'A60:F81' 'report-before'
    if($dateShift -eq 1){$s.Columns.Item(3).Insert()|Out-Null;$s.Columns.Item(3).ColumnWidth=$s.Columns.Item(4).ColumnWidth}
    foreach($a in $plan.current_cells){
        $r=[int]($a -replace '[A-Z]','');$from=$s.Cells.Item($r,(3+$dateShift)).MergeArea
        if($from.Column -ne (3+$dateShift) -or $from.Columns.Count -ne 1){continue}
        if($dateShift -eq 1){
            $to=$s.Range($s.Cells.Item($r,3),$s.Cells.Item($r+$from.Rows.Count-1,3));$from.Copy()|Out-Null;$to.PasteSpecial(-4122)|Out-Null
            if($from.Rows.Count -gt 1 -and -not $to.MergeCells){$to.Merge()|Out-Null}
        }
        $s.Cells.Item($r,3).Value2='-'
    }
    $s.Range('C3').Value2=[datetime]::Parse($plan.as_of).ToOADate();$s.Range('C3').NumberFormat='yyyy-mm-dd'
    foreach($r in $plan.date_rows){if($r -ne 3){$s.Cells.Item([int]$r,3).Formula='=$C$3';$s.Cells.Item([int]$r,3).NumberFormat='yyyy-mm-dd'}}
    $styleRow=if($plan.style_row){[int]$plan.style_row}else{54}
    if($s.Cells.Item($styleRow,1).Value2 -ne 'BEA'){throw '未合并行样式样本已变化'}
    $styleSheet=$book.Worksheets.Add();$styleSheet.Name='临时行样式'
    $s.Range(('A'+$styleRow+':C'+$styleRow)).Copy()|Out-Null;$styleSheet.Range('A1:C1').PasteSpecial(-4122)|Out-Null
    Remove-QuoteIcons $styleSheet
    # Insert only at bank block boundaries. Original history shifts natively.
    $boundaries=@($plan.report_inserts | Group-Object at | Sort-Object {[int]$_.Name} -Descending)
    foreach($boundary in $boundaries){
        $r=[int]$boundary.Name;$count=($boundary.Group | Measure-Object -Property count -Sum).Sum
        for($c=2;$c -le $lastCol;$c++){$m=$s.Cells.Item($r,$c).MergeArea;if($m.Row -lt $r -and $m.Row+$m.Rows.Count -gt $r){throw '插入边界跨历史合并块'}}
        $s.Rows.Item([string]($r.ToString()+':'+($r+$count-1))).Insert()|Out-Null
        $fresh=$s.Range($s.Cells.Item($r,1),$s.Cells.Item($r+$count-1,$lastCol));$fresh.UnMerge()|Out-Null;$fresh.ClearContents()|Out-Null
        for($j=0;$j -lt $count;$j++){
            $styleSheet.Range('A1:C1').Copy()|Out-Null
            $s.Range($s.Cells.Item($r+$j,1),$s.Cells.Item($r+$j,3)).PasteSpecial(-4122)|Out-Null
        }
        $fresh.UnMerge()|Out-Null
        Check ('插入边界 '+$r+' 的新行历史为空') ($excel.WorksheetFunction.CountA($s.Range($s.Cells.Item($r,4),$s.Cells.Item($r+$count-1,$lastCol))) -eq 0) $count
    }
    $input.Worksheets.Item(1).Copy([Type]::Missing,$book.Worksheets.Item($book.Worksheets.Count))
    foreach($u in $plan.report_updates){
        if($null -ne $u.group){Set-Group $s $u.group ([int]$u.target_start) ([int]($u.target_end-$u.target_start+1)) $false}
        elseif($u.missing_status){$s.Cells.Item([int]$u.target_start,2).Value2=[string]($u.missing_status+'；本期不参与报价比较');$s.Cells.Item([int]$u.target_start,2).WrapText=$true}
    }
    foreach($i in $plan.report_inserts){if(-not $i.extension){Set-Group $s $i.group ([int]$i.target_start) ([int]$i.count) $true}}
    foreach($m in $plan.bank_merges){
        $label=$s.Range($s.Cells.Item([int]$m.start,1),$s.Cells.Item([int]$m.end,1))
        $label.UnMerge()|Out-Null;$label.ClearContents()|Out-Null
        if($m.end -gt $m.start){$label.Merge()|Out-Null}
        $s.Cells.Item([int]$m.start,1).Value2=[string]$m.bank
    }
    foreach($delta in $plan.deltas){$s.Cells.Item([int]$delta.row,[int]$delta.col).Formula=[string]$delta.formula}
    $styleSheet.Delete()
    Remove-QuoteIcons $s
    $quoteIcons=@($s.Columns.Item(3).FormatConditions|Where-Object {$_.Type -eq 6})
    Check '本期报价列不含箭头条件格式' ($quoteIcons.Count -eq 0) $quoteIcons.Count
    $restoredBorders=Restore-HistoryBoundaryBorders $s $plan $historyBorders
    $s.Range('A1').Value2=[string]($plan.as_of+' '+$plan.collection_label+'（待复核；各行注明证据日；其余本期为-）')
    $summary=$book.Worksheets.Item('最高报价汇总 ');$summary.Range('B2').Value2=[string]('新元促销（'+($plan.banks -join '/')+'；证据日见明细；其余保留底稿）')
    foreach($v in $plan.summary){$cell=$summary.Cells.Item([int]$v.row,[int]$v.col);if($v.input_rows.Count){$cell.Formula=(RateFormula $v.input_rows);$cell.NumberFormat='0.00%'}else{$cell.Value2='-'}}
    $excel.CalculateFull()
    foreach($g in $plan.groups){Check ('调研主报价 '+$g.id) (Eq $s.Cells.Item([int]$g.report_row,3).Value2 ([double]$g.main_pct/100)) $g.main_pct}
    foreach($v in $plan.summary){if($v.input_rows.Count){$highest=(@($plan.details|Where-Object {$v.input_rows -contains $_.input_row})|Measure-Object -Property rate_pct -Maximum).Maximum;Check ('最高报价 '+$v.bank+'/'+$v.tenor) (Eq $summary.Cells.Item([int]$v.row,[int]$v.col).Value2 ([double]$highest/100)) $highest}}
    # Change/restore Personal and special-customer inputs to prove native formulas.
    $candidates=@($plan.groups|Where-Object {@($_.details|Where-Object {$_.audience -eq 'personal'}).Count -gt 0 -and @($_.details|Where-Object {$_.audience -ne 'personal'}).Count -gt 0})
    $ordinary=@($candidates|Where-Object {$_.product_id -eq 'cimb-sgd-online' -and $_.display_tenor -eq '6M'})[0]
    if($null -eq $ordinary){$ordinary=$candidates[0]}
    if($null -eq $ordinary){throw '本批缺少可验证 Personal/其他客群公式的组合，请补充专用验证'}
    $ins=$book.Worksheets.Item($plan.input_sheet);$pRow=[int]$ordinary.details[0].input_row
    $wRow=[int](@($ordinary.details|Where-Object {$_.audience -ne 'personal'})[0].input_row)
    $oldP=$ins.Cells.Item($pRow,8).Value2;$oldW=$ins.Cells.Item($wRow,8).Value2
    $oldHistory=$s.Cells.Item([int]$ordinary.report_row,4).Value2
    $ins.Cells.Item($pRow,8).Value2=0.0191;$ins.Cells.Item($wRow,8).Value2=0.0244;$excel.CalculateFull()
    Check 'Personal变动驱动主报价' (Eq $s.Cells.Item([int]$ordinary.report_row,3).Value2 0.0191) '1.91%'
    $summaryTarget=@($plan.summary|Where-Object {$_.bank -eq $ordinary.bank -and $_.tenor -eq $ordinary.display_tenor})[0]
    Check '特殊客群变动驱动全客群最高报价' (Eq $summary.Cells.Item([int]$summaryTarget.row,[int]$summaryTarget.col).Value2 0.0244) '2.44%'
    Check '修改本期明细不改变上一期' ($s.Cells.Item([int]$ordinary.report_row,4).Value2 -eq $oldHistory) $oldHistory
    $ins.Cells.Item($pRow,8).Value2=$oldP;$ins.Cells.Item($wRow,8).Value2=$oldW;$excel.CalculateFull()
    foreach($delta in $plan.deltas){
        $now=$s.Cells.Item([int]$delta.row,3).Value2;$old=$s.Cells.Item([int]$delta.row,4).Value2
        $actual=$s.Cells.Item([int]$delta.row,[int]$delta.col).Value2
        $numeric=$now -is [double] -and $old -is [double]
        $ok=if($numeric){Eq $actual ([double]$now-[double]$old)}else{$actual -eq '-'}
        Check ('最新两期变动 '+$delta.source) $ok $actual
    }
    # Verify the actual output formula survives one more date-column insertion.
    $s.Copy([Type]::Missing,$book.Worksheets.Item($book.Worksheets.Count))
    $future=$book.Worksheets.Item($book.Worksheets.Count)
    $r=[int]$ordinary.report_row;$delta=@($plan.deltas|Where-Object {$_.row -eq $r})[0]
    $future.Columns.Item(3).Insert()|Out-Null
    Remove-QuoteIcons $future
    Check '下周新日期列不含箭头条件格式' (@($future.Columns.Item(3).FormatConditions|Where-Object {$_.Type -eq 6}).Count -eq 0) 'C列'
    $future.Cells.Item($r,4).MergeArea.Value2=0.0175
    $future.Cells.Item($r,3).MergeArea.Value2=0.019
    $excel.CalculateFull()
    Check '再次插日期列仍比较最新两期' (Eq $future.Cells.Item($r,[int]$delta.col+1).Value2 0.0015) '0.15个百分点'
    $future.Cells.Item($r,3).MergeArea.Value2='-';$excel.CalculateFull()
    Check '新一期缺失时不显示旧期涨跌' ($future.Cells.Item($r,[int]$delta.col+1).Value2 -eq '-') '-'
    $future.Delete();$excel.CalculateFull()
    foreach($g in @($plan.groups|Where-Object {($_.bank -eq 'UOB' -and $_.display_tenor -eq '12M') -or ($_.bank -eq 'BOC' -and $_.display_tenor -in @('3M','9M'))})){
        Snapshot $s ('A'+$g.report_row+':E'+([int]$g.report_row+$g.details.Count-1)) ('quote-'+$g.bank.ToLower()+'-'+$g.display_tenor.ToLower())
    }
    $six=@($plan.report_updates|Where-Object {$_.tenor -eq '6M'});$first=($six|Measure-Object target_start -Minimum).Minimum;$last=($six|Measure-Object target_end -Maximum).Maximum
    foreach($i in $plan.report_inserts|Where-Object {$_.group.display_tenor -eq '6M'}){$last=[math]::Max($last,([int]$i.target_start+[int]$i.count-1))}
    Snapshot $s ('A'+$first+':F'+$last) 'report-after';Snapshot $summary 'B3:I20' 'summary-after'
    $rhb=@($plan.report_updates|Where-Object {$_.bank -eq 'RHB' -and $_.tenor -eq '6M'})[0]
    $cimb=@($plan.report_updates|Where-Object {$_.bank -eq 'CIMB' -and $_.tenor -eq '6M'})[0]
    Snapshot $s ('A'+$rhb.target_start+':IG'+$cimb.target_end) 'delta-after'
    $rendered=@{};foreach($g in $plan.groups){for($j=0;$j -lt $g.details.Count;$j++){$row=[int]$g.report_row+$j;$rendered['B'+$row]=[string]$s.Cells.Item($row,2).Value2}}
    $rendered|ConvertTo-Json -Depth 5|Set-Content -LiteralPath (Join-Path $out 'rendered-values.json') -Encoding UTF8
    $s.Activate()|Out-Null;$excel.Goto($s.Range('A'+$first),$true);$book.SaveAs($plan.report_output,51);$book.Close($false);$book=$null
    $book=$excel.Workbooks.Open($plan.rainbow_template,0,$true);$rs=$book.Worksheets.Item('SGD Promotional Rate')
    $input.Worksheets.Item(1).Copy([Type]::Missing,$book.Worksheets.Item($book.Worksheets.Count))
    # Keep a source worksheet copy in memory for formatting, then remove before saving.
    $rs.Copy([Type]::Missing,$book.Worksheets.Item($book.Worksheets.Count));$sourceRainbow=$book.Worksheets.Item($book.Worksheets.Count)
    $sourceRainbow.Range('A3:U'+$rainbowLast).UnMerge()|Out-Null
    foreach($rg in $plan.rainbow_groups){
        $c=[int]$rg.col;$end=[math]::Max($rainbowLast,[int]$rg.last_row)
        $area=$rs.Range($rs.Cells.Item(3,$c),$rs.Cells.Item($end,$c+2));$area.UnMerge()|Out-Null;$area.ClearContents()|Out-Null
        foreach($b in $rg.blocks){
            $r=[int]$b.target_start;$count=$b.rows.Count
            for($j=0;$j -lt $count;$j++){
                $src=if($null -ne $b.source_start){[int]$b.source_start+$j}else{3}
                $sourceRainbow.Range($sourceRainbow.Cells.Item($src,$c),$sourceRainbow.Cells.Item($src,$c+2)).Copy()|Out-Null
                $rs.Range($rs.Cells.Item($r+$j,$c),$rs.Cells.Item($r+$j,$c+2)).PasteSpecial(-4122)|Out-Null
            }
            $rs.Range($rs.Cells.Item($r,$c),$rs.Cells.Item($r+$count-1,$c+2)).UnMerge()|Out-Null
            if($count -gt 1){$rs.Range($rs.Cells.Item($r,$c),$rs.Cells.Item($r+$count-1,$c)).Merge()|Out-Null}
            $rs.Cells.Item($r,$c).Value2=[string]$b.bank
            for($j=0;$j -lt $count;$j++){
                if($null -ne $b.group){$d=$b.group.details[$j];$rs.Cells.Item($r+$j,$c+1).Formula=("='"+$plan.input_sheet+"'!H"+$d.input_row);$rs.Cells.Item($r+$j,$c+2).Value2=[string](Description $d)}
                else{
                    $v=$b.rows[$j][1]
                    if($null -eq $v){$rs.Cells.Item($r+$j,$c+1).ClearContents()|Out-Null}
                    elseif($v -is [string]){$rs.Cells.Item($r+$j,$c+1).Value2=[string]$v}
                    else{$rs.Cells.Item($r+$j,$c+1).Value2=[double]$v}
                    $rs.Cells.Item($r+$j,$c+2).Value2=[string]$b.rows[$j][2]
                }
                $rs.Cells.Item($r+$j,$c+1).NumberFormat='0.00%';$rs.Cells.Item($r+$j,$c+2).WrapText=$true
                $rs.Rows.Item($r+$j).RowHeight=if($null -ne $b.group -and ($b.group.details[$j].reference_quote -or $b.group.bank -eq 'BOC')){72}else{42}
            }
        }
        foreach($label in $rg.bank_labels){
            $a=$rs.Range($rs.Cells.Item([int]$label.start,$c),$rs.Cells.Item([int]$label.end,$c))
            $a.UnMerge()|Out-Null;$a.ClearContents()|Out-Null
            if($label.end -gt $label.start){$a.Merge()|Out-Null}
            $rs.Cells.Item([int]$label.start,$c).Value2=[string]$label.bank
        }
    }
    $sourceRainbow.Delete();$sourceRainbow=$null
    $rs.Range('A1').Value2=[string]($plan.as_of+' '+$plan.collection_label+'（待复核；各银行证据日见明细；其余保留底稿；改值后重新生成排序）')
    $excel.CalculateFull()
    foreach($rg in $plan.rainbow_groups){foreach($b in $rg.blocks){if($null -ne $b.group){Check ('彩虹表主报价 '+$b.group.id) (Eq $rs.Cells.Item([int]$b.target_start,[int]$rg.col+1).Value2 ([double]$b.group.main_pct/100)) $b.target_start}}}
    $ins=$book.Worksheets.Item($plan.input_sheet);$ins.Cells.Item($wRow,8).Value2=0.0244;$excel.CalculateFull()
    $ordinaryRainbow=@($plan.rainbow_groups|Where-Object {$_.tenor -eq $ordinary.display_tenor})[0]
    $ordinaryBlock=@($ordinaryRainbow.blocks|Where-Object {$null -ne $_.group -and $_.group.id -eq $ordinary.id})[0]
    $detailIndex=0
    for($j=0;$j -lt $ordinaryBlock.group.details.Count;$j++){if($ordinaryBlock.group.details[$j].input_row -eq $wRow){$detailIndex=$j}}
    Check '彩虹表公式随输入重新计算' (Eq $rs.Cells.Item([int]$ordinaryBlock.target_start+$detailIndex,[int]$ordinaryRainbow.col+1).Value2 0.0244) '恢复原值后保存'
    $ins.Cells.Item($wRow,8).Value2=$oldW;$excel.CalculateFull()
    foreach($t in @('3M','6M','9M','12M')){
        $rg=@($plan.rainbow_groups|Where-Object {$_.tenor -eq $t})[0]
        $ends=@($rg.blocks|ForEach-Object {[int]$_.target_start+$_.rows.Count-1})
        $end=@($ends|Where-Object {$_ -ge 20}|Select-Object -First 1)
        if($end.Count -eq 0){$end=@([int]$rg.last_row)}
        $left=([char](64+[int]$rg.col)).ToString();$right=([char](66+[int]$rg.col)).ToString()
        $name=if($t -eq '6M'){'rainbow-6m-top'}else{'rainbow-'+$t.ToLower()}
        Snapshot $rs ($left+'2:'+$right+$end[0]) $name
        if($t -eq '6M'){Snapshot $rs ($left+([int]$end[0]+1)+':'+$right+$rg.last_row) 'rainbow-6m-bottom'}
    }
    $rs.Activate()|Out-Null;$excel.Goto($rs.Range('G1'),$true);$book.SaveAs($plan.rainbow_output,51);$book.Close($false);$book=$null
    $checks|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $out 'native-checks.json') -Encoding UTF8
    Write-Output ('原生检查通过：'+$checks.Count+'项。')
}catch{Write-Output $_.ScriptStackTrace;throw}
finally{foreach($b in @($book,$input)){if($null -ne $b){$b.Close($false)|Out-Null}};if($null -ne $excel){$excel.Quit();[Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel)|Out-Null};[GC]::Collect();[GC]::WaitForPendingFinalizers()}
