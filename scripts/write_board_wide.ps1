param([Parameter(Mandatory=$true)][string]$PlanPath)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'quote_icon_formats.ps1')
. (Join-Path $PSScriptRoot 'board_history_layout.ps1')
$p=Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8|ConvertFrom-Json
$out=Split-Path $PlanPath;$excel=$null;$books=@();$checks=[Collections.Generic.List[object]]::new()
function Assign($c,$v){if($v -is [string] -and $v.StartsWith('=')){$c.Formula=$v}elseif($v -is [double] -or $v -is [int] -or $v -is [decimal]){$c.Value2=[double]$v}else{$c.Value2=[string]$v}}
function TestCell($s,$r,$c,$v){$actual=$s.Cells.Item($r,$c).Value2;$ok=if($v -is [double] -or $v -is [int] -or $v -is [decimal]){$null -ne $actual -and [math]::Abs([double]$actual-[double]$v) -lt 0.00000000001}else{[string]$actual -ceq [string]$v};$checks.Add(@{sheet=$s.Name;row=$r;col=$c;passed=$ok});if(-not $ok){throw "Readback failed: $($s.Name) $r/$c $actual expected $v"}}
function Put($s,$cells){foreach($c in $cells){Assign $s.Range([string]$c.address) $c.formula;$s.Range([string]$c.address).NumberFormat='0.0000%'}}
function CloneStyle($s,$w){$s.Copy([Type]::Missing,$w.Worksheets.Item($w.Worksheets.Count))|Out-Null;$temp=$w.Worksheets.Item($w.Worksheets.Count);$temp.Name='_wide_style_temp';$temp.UsedRange.UnMerge()|Out-Null;return $temp}
function Picture($s,$area,$name){$ps=$s.PageSetup;$old=@($ps.PrintArea,$ps.Orientation,$ps.Zoom,$ps.FitToPagesWide,$ps.FitToPagesTall);try{$ps.PrintArea=$area;$ps.Orientation=2;$ps.Zoom=$false;$ps.FitToPagesWide=1;$ps.FitToPagesTall=1;$s.ExportAsFixedFormat(0,(Join-Path $out ($name+'.pdf')),0,$true,$false)}finally{$ps.PrintArea=$old[0];$ps.Orientation=$old[1];$ps.Zoom=$old[2];$ps.FitToPagesWide=$old[3];$ps.FitToPagesTall=$old[4]}}
try{
 $excel=New-Object -ComObject Excel.Application;$excel.Visible=$false;$excel.DisplayAlerts=$false;$excel.EnableEvents=$false;$excel.AutomationSecurity=3;$excel.AskToUpdateLinks=$false;$excel.ScreenUpdating=$false
 $inputs=$excel.Workbooks.Open((Join-Path $out 'board-inputs.xlsx'),0,$true);$books+=,$inputs
 foreach($kind in @('report','rainbow')){
  $w=$excel.Workbooks.Open($p.($kind+'_template'),0,$true);$books+=,$w;$w.SaveAs($p.($kind+'_output'),51)
  $inputs.Worksheets.Item(1).Copy([Type]::Missing,$w.Worksheets.Item($w.Worksheets.Count))|Out-Null
  if($w.Worksheets.Item($w.Worksheets.Count).Name -cne $p.input_sheet){throw 'Input sheet name collision; formulas would reference stale inputs'}
  if($kind -eq 'report'){
   foreach($m in $p.matrices){
    $s=$w.Worksheets.Item($m.sheet);$temp=CloneStyle $s $w;$bc=[int]$m.bank_col;$ac=[int]$m.amount_col;$nc=[int]$m.note_col
    foreach($i in @($m.inserts|Sort-Object before -Descending)){$s.Rows.Item(([int]$i.before).ToString()+':'+([int]$i.before+[int]$i.count-1)).Insert()|Out-Null}
    $area=$s.Range($s.Cells.Item(3,$bc),$s.Cells.Item([int]$m.end,$nc));$area.UnMerge()|Out-Null;$area.ClearContents()|Out-Null
    foreach($g in $m.groups){$n=[int]$g.target_row
     foreach($r in $g.rows){$source=[int]$r.source_row;$temp.Range($temp.Cells.Item($source,$bc),$temp.Cells.Item($source,$nc)).Copy($s.Range($s.Cells.Item($n,$bc),$s.Cells.Item($n,$nc)))|Out-Null
      $s.Cells.Item($n,$bc).ClearContents()|Out-Null;$s.Cells.Item($n,$ac).Value2=[string]$r.amount;$s.Cells.Item($n,$nc).Value2=[string]$r.note
      foreach($v in $r.values){Assign $s.Cells.Item($n,[int]$v.col) $v.formula;$s.Cells.Item($n,[int]$v.col).NumberFormat='0.0000%'}
      $s.Range($s.Cells.Item($n,$ac),$s.Cells.Item($n,$nc)).WrapText=$true;$s.Rows.Item($n).RowHeight=60;$n++
     }
     if($g.rows.Count -gt 1){$s.Range($s.Cells.Item([int]$g.target_row,$bc),$s.Cells.Item($n-1,$bc)).Merge()|Out-Null};$s.Cells.Item([int]$g.target_row,$bc).Value2=[string]$g.label
    }
    $s.Columns.Item($ac).ColumnWidth=36;$s.Columns.Item($nc).ColumnWidth=58
    $s.Range($s.Cells.Item(3,$bc),$s.Cells.Item([int]$m.end,$nc)).Font.Size=10
    $s.Range($s.Cells.Item(3,$ac+1),$s.Cells.Item([int]$m.end,[int]$m.last_col)).WrapText=$false
    $temp.Delete();$s.Cells.Item(1,$bc).Value2=[string]($m.currency+'挂牌 '+$p.as_of+'；银行来源日期及待核项见本期明细')
    $dateCol=if($m.currency -eq 'SGD'){15}else{10};$s.Cells.Item(1,$dateCol).Value2=[double]([datetime]::Parse($p.as_of).ToOADate());$s.Cells.Item(1,$dateCol).NumberFormat='yyyy-mm-dd'
    $excel.CalculateFull();foreach($g in $m.groups){$n=[int]$g.target_row;foreach($r in $g.rows){foreach($v in $r.values){TestCell $s $n ([int]$v.col) $v.expected};$n++}}
   }
   foreach($h in $p.histories){
    $s=$w.Worksheets.Item($h.sheet);$cc=[int]$h.current_col;$bc=[int]$h.bank_col
    $s.Columns.Item($bc+1).ColumnWidth=46
    if($h.insert_date){
     $merges=@();foreach($addr in $h.merges){$ma=$s.Range([string]$addr);$merges+=,@($ma.Row,$ma.Column,$ma.Rows.Count,$ma.Columns.Count)}
     $s.Columns.Item($cc).Insert()|Out-Null;$s.Columns.Item($cc+1).Copy()|Out-Null;$s.Columns.Item($cc).PasteSpecial(-4122)|Out-Null
     foreach($m in $merges){$left=[int]$m[1];$right=$left+[int]$m[3]-1;if($left -ge $cc){$left++};if($right -ge $cc){$right++};$s.Range($s.Cells.Item([int]$m[0],$left),$s.Cells.Item([int]$m[0]+[int]$m[2]-1,$right)).Merge()|Out-Null}
     for($r=1;$r -le [int]$h.old_max_row;$r++){if(-not $s.Cells.Item($r,$cc).MergeCells){$s.Cells.Item($r,$cc).Value2='-'}}
    }
    foreach($i in @($h.inserts|Sort-Object before -Descending)){
     $before=[int]$i.before;$anchor=[int]$i.anchor;$count=[int]$i.count;$s.Cells.Item($anchor,$bc).MergeArea.UnMerge()|Out-Null
     $s.Rows.Item($before.ToString()+':'+($before+$count-1)).Insert()|Out-Null
     for($j=0;$j -lt $count;$j++){
      $dest=$before+$j;$s.Rows.Item($anchor).Copy()|Out-Null;$s.Rows.Item($dest).PasteSpecial(-4122)|Out-Null;$s.Rows.Item($dest).ClearContents()|Out-Null
      $s.Cells.Item($dest,$bc+1).Value2=[string]$i.rows[$j].amount;Assign $s.Cells.Item($dest,$cc) $i.rows[$j].formula;$s.Cells.Item($dest,$cc).NumberFormat='0.0000%'
      $s.Cells.Item($dest,$bc+1).WrapText=$true;$s.Rows.Item($dest).RowHeight=96
     }
     $s.Range($s.Cells.Item($anchor,$bc),$s.Cells.Item($before+$count-1,$bc)).Merge()|Out-Null;$s.Cells.Item($anchor,$bc).Value2=[string]$i.label
    }
    foreach($r in $h.date_rows){$s.Cells.Item([int]$r,$cc).Value2=[double]([datetime]::Parse($p.as_of).ToOADate());$s.Cells.Item([int]$r,$cc).NumberFormat='yyyy-mm-dd'}
    Put $s $h.existing;Remove-QuoteIcons $s $cc
    $delta=$s.UsedRange.Find('当日最高报价变动')
    if($null -ne $delta){$dc=$delta.Column;for($r=1;$r -le [int]$h.max_row;$r++){$cell=$s.Cells.Item($r,$dc);if($cell.HasFormula){$cell.Formula=('=IF(AND(ISNUMBER(INDEX('+ $r+':'+$r+',1,'+$cc+')),ISNUMBER(INDEX('+ $r+':'+$r+',1,'+($cc+1)+'))),INDEX('+ $r+':'+$r+',1,'+$cc+')-INDEX('+ $r+':'+$r+',1,'+($cc+1)+'),"-")')}}}
    $s.Cells.Item(1,$bc).Value2=[string]($h.currency+'挂牌 '+$p.as_of+'；原CNH按CNY；新增条件在本银行内，历史保留')
    # Set widths after column insertion/format pasting, which can reset them.
    $s.Columns.Item($bc+1).ColumnWidth=46
    Format-BoardHistoryRows $s $h
    $excel.CalculateFull();foreach($c in $h.existing){$cell=$s.Range([string]$c.address);TestCell $s $cell.Row $cell.Column $c.expected}
    foreach($i in $h.inserts){for($j=0;$j -lt $i.count;$j++){TestCell $s ([int]$i.target_row+$j) $cc $i.rows[$j].expected}}
   }
   $s=$w.Worksheets.Item('最高报价汇总 ');Put $s $p.summary;$s.Range('H41').Value2=[string]$p.as_of;$s.Range('H58').Value2=[string]$p.as_of
   $s.Range('B41').Value2='美元挂牌；覆盖及待核见本期明细';$excel.CalculateFull()
   Picture $w.Worksheets.Item('SGD挂牌') 'A1:S22' 'sgd-board-preview'
   Picture $w.Worksheets.Item('CNY挂牌') 'A1:F20' 'cny-history-preview'
   $sgdMatrix=$p.matrices|Where-Object {$_.currency -eq 'SGD'}
   foreach($bankName in @('BEA','Maybank','OCBC')){
    $group=$sgdMatrix.groups|Where-Object {$_.bank -eq $bankName}
    if($null -ne $group){$first=[int]$group.target_row;$last=$first+[Math]::Min(6,$group.rows.Count)-1;Picture $w.Worksheets.Item('SGD挂牌') ('A'+$first+':S'+$last) ($bankName.ToLower()+'-sgd-repair-preview')}
   }
   foreach($cur in @('AUD','EUR','HKD')){
    $matrix=$p.matrices|Where-Object {$_.currency -eq $cur}
    $group=$matrix.groups|Where-Object {$_.bank -eq 'OCBC'}
    if($null -ne $group){$first=[int]$group.target_row;$last=$first+$group.rows.Count-1;Picture $w.Worksheets.Item($matrix.sheet) ('B'+$first+':N'+$last) ('ocbc-'+$cur.ToLower()+'-preview')}
   }
  }else{
   foreach($name in @('SGD Board Rate','USD Rate + Other Currency Rates')){
    $s=$w.Worksheets.Item($name);$temp=CloneStyle $s $w
    if($name -ne 'SGD Board Rate' -and [int]$p.rainbow_shift -gt 0){$s.Rows.Item((([int]$p.rainbow_insert_before).ToString()+':'+([int]$p.rainbow_insert_before+[int]$p.rainbow_shift-1))).Insert()|Out-Null}
    foreach($block in @($p.rainbow_blocks|Where-Object {$_.sheet -eq $name})){
     $c=[int]$block.col;$s.Range($s.Cells.Item([int]$block.start,$c),$s.Cells.Item([int]$block.end,$c+2)).UnMerge()|Out-Null;$s.Range($s.Cells.Item([int]$block.start,$c),$s.Cells.Item([int]$block.end,$c+2)).ClearContents()|Out-Null
     foreach($g in $block.groups){$n=[int]$g.target_row
      foreach($r in $g.rows){$source=[int]$r.source_row;$temp.Range($temp.Cells.Item($source,$c),$temp.Cells.Item($source,$c+2)).Copy($s.Range($s.Cells.Item($n,$c),$s.Cells.Item($n,$c+2)))|Out-Null
       $s.Cells.Item($n,$c).ClearContents()|Out-Null;Assign $s.Cells.Item($n,$c+1) $r.formula;$s.Cells.Item($n,$c+1).NumberFormat='0.0000%';$s.Cells.Item($n,$c+2).Value2=([string]$r.amount -replace '\s+',' ');$s.Cells.Item($n,$c+2).WrapText=$true;$s.Cells.Item($n,$c+2).Font.Size=10;$s.Rows.Item($n).RowHeight=96;$n++
      }
      if($n-[int]$g.target_row -gt 1){$s.Range($s.Cells.Item([int]$g.target_row,$c),$s.Cells.Item($n-1,$c)).Merge()|Out-Null};$s.Cells.Item([int]$g.target_row,$c).Value2=[string]$g.label
     }
    }
    $temp.Delete()
   }
   $s=$w.Worksheets.Item('USD Rate + Other Currency Rates');Put $s $p.rainbow_cells;$s.Range('A31').Value2='USD Board Rates '+$p.as_of+'；范围及待核见明细';$s.Range('A'+([int]$p.rainbow_cny_title+[int]$p.rainbow_shift)).Value2='CNY Board Rates '+$p.as_of+'；含CNH'
   $w.Worksheets.Item('SGD Board Rate').Range('A1').Value2='SGD挂牌 '+$p.as_of+'；范围及待核见明细'
   $excel.CalculateFull();foreach($b in $p.rainbow_blocks){$s=$w.Worksheets.Item($b.sheet);foreach($g in $b.groups){$n=[int]$g.target_row;foreach($r in $g.rows){TestCell $s $n ([int]$b.col+1) $r.expected;$n++}}}
   Picture $w.Worksheets.Item('SGD Board Rate') 'G2:I25' 'sgd-rainbow-preview'
   $sh=[int]$p.rainbow_shift;Picture $w.Worksheets.Item('USD Rate + Other Currency Rates') ('A'+([int]$p.rainbow_cny_title+$sh)+':J'+([int]$p.rainbow_cny_title+12+$sh)) 'cny-rainbow-preview'
  }
  $w.Save();$w.Close($false);$books=@($books|Where-Object {$_ -ne $w})
 }
 $checks|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $out 'native-checks.json') -Encoding UTF8
 Write-Output ('Native checks passed: '+$checks.Count)
}finally{foreach($w in $books){try{$w.Close($false)}catch{}};if($null -ne $excel){$excel.Quit();[Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel)|Out-Null};[GC]::Collect();[GC]::WaitForPendingFinalizers()}
foreach($kind in @('report','rainbow')){if((Get-FileHash -LiteralPath $p.($kind+'_template')).Hash.ToLower() -ne $p.($kind+'_sha256')){throw 'Source changed'}}
