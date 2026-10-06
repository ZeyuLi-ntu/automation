param([Parameter(Mandatory=$true)][string]$PlanPath)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'quote_icon_formats.ps1')
. (Join-Path $PSScriptRoot 'board_history_layout.ps1')
. (Join-Path $PSScriptRoot 'rate_delta_columns.ps1')
. (Join-Path $PSScriptRoot 'fx_notice_layout.ps1')
. (Join-Path $PSScriptRoot 'bank_group_layout.ps1')
. (Join-Path $PSScriptRoot 'fx_summary_format.ps1')
$p=Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8|ConvertFrom-Json
$PlanPath=(Resolve-Path -LiteralPath $PlanPath).Path;$out=Split-Path $PlanPath;$excel=$null;$books=@();$checks=[Collections.Generic.List[object]]::new()
function Assign($c,$v){if($v -is [string] -and $v.StartsWith('=')){$c.Formula=$v}elseif($v -is [double] -or $v -is [int] -or $v -is [decimal]){$c.Value2=[double]$v}else{$c.Value2=[string]$v}}
function TestCell($s,$address,$v){$actual=$s.Range([string]$address).Value2;$ok=if($v -is [double] -or $v -is [int] -or $v -is [decimal]){$null -ne $actual -and [math]::Abs([double]$actual-[double]$v) -lt 0.00000000001}else{[string]$actual -ceq [string]$v};$checks.Add(@{sheet=$s.Name;address=$address;passed=$ok});if(-not $ok){throw "Readback failed: $($s.Name) $address $actual expected $v"}}
function Put($s,$cells){foreach($c in $cells){Assign $s.Range([string]$c.address) $c.formula;if($c.expected -is [double]){$s.Range([string]$c.address).NumberFormat='0.0000%'}}}
function Picture($s,$area,$name){$ps=$s.PageSetup;$old=@($ps.PrintArea,$ps.Orientation,$ps.Zoom,$ps.FitToPagesWide,$ps.FitToPagesTall);try{$ps.PrintArea=$area;$ps.Orientation=2;$ps.Zoom=$false;$ps.FitToPagesWide=1;$ps.FitToPagesTall=1;$s.ExportAsFixedFormat(0,(Join-Path $out ($name+'.pdf')),0,$true,$false)}finally{$ps.PrintArea=$old[0];$ps.Orientation=$old[1];$ps.Zoom=$old[2];$ps.FitToPagesWide=$old[3];$ps.FitToPagesTall=$old[4]}}
function Color($hex){return [Convert]::ToInt32($hex.Substring(0,2),16)+256*[Convert]::ToInt32($hex.Substring(2,2),16)+65536*[Convert]::ToInt32($hex.Substring(4,2),16)}
try{
 $excel=New-Object -ComObject Excel.Application;$excel.Visible=$false;$excel.DisplayAlerts=$false;$excel.EnableEvents=$false;$excel.AutomationSecurity=3;$excel.AskToUpdateLinks=$false;$excel.ScreenUpdating=$false
 $inputs=$excel.Workbooks.Open((Join-Path $out 'fx-inputs.xlsx'),0,$true);$books+=,$inputs
 foreach($kind in @('report','rainbow')){
  $w=$excel.Workbooks.Open($p.($kind+'_template'),0,$true);$books+=,$w
  if($kind -eq 'report'){Picture $w.Worksheets.Item('USD促销') 'B39:G60' 'before-usd-promo'}else{Picture $w.Worksheets.Item('USD Rate + Other Currency Rates') 'I2:K21' 'before-usd-rainbow'}
  $w.SaveAs($p.($kind+'_output'),51)
  $inputs.Worksheets.Item(1).Copy([Type]::Missing,$w.Worksheets.Item($w.Worksheets.Count))|Out-Null
  if($w.Worksheets.Item($w.Worksheets.Count).Name -cne $p.input_sheet){throw 'Input sheet name collision; formulas would reference stale inputs'}
  if($kind -eq 'report'){
   foreach($h in $p.histories){
    $s=$w.Worksheets.Item($h.sheet);$cc=[int]$h.current_col;$bc=[int]$h.bank_col
    foreach($snap in $h.snapshots){Assign $s.Range([string]$snap.address) $snap.value}
    if($h.insert_date){
     $merges=@();foreach($addr in $h.merges){$ma=$s.Range([string]$addr);$merges+=,@($ma.Row,$ma.Column,$ma.Rows.Count,$ma.Columns.Count)}
     $s.Columns.Item($cc).Insert()|Out-Null;$s.Columns.Item($cc+1).Copy()|Out-Null;$s.Columns.Item($cc).PasteSpecial(-4122)|Out-Null
     foreach($m in $merges){$left=[int]$m[1];$right=$left+[int]$m[3]-1;if($left -ge $cc){$left++};if($right -ge $cc){$right++};$s.Range($s.Cells.Item([int]$m[0],$left),$s.Cells.Item([int]$m[0]+[int]$m[2]-1,$right)).Merge()|Out-Null}
     for($r=1;$r -le [int]$h.old_max_row;$r++){if(-not $s.Cells.Item($r,$cc).MergeCells){$s.Cells.Item($r,$cc).Value2='-'}}
    }
    $ordered=@($h.inserts);[array]::Reverse($ordered)
    foreach($i in $ordered){
     $before=[int]$i.before;$anchor=[int]$i.anchor;$count=[int]$i.count
     if(-not $i.new_bank){$s.Cells.Item($anchor,$bc).MergeArea.UnMerge()|Out-Null}
     $s.Rows.Item($before.ToString()+':'+($before+$count-1)).Insert()|Out-Null
     if($i.kind -eq 'tenor'){
      $s.Range($s.Cells.Item($before,$bc),$s.Cells.Item($before+1,$cc+2)).Font.Bold=$true
      $s.Cells.Item($before,$bc).Value2=[string]$i.label;$s.Cells.Item($before+1,$bc).Value2='银行';$s.Cells.Item($before+1,$bc+1).Value2='全部公开报价';$s.Cells.Item($before+1,$cc).Value2=[double]([datetime]::Parse($p.as_of).ToOADate());$s.Cells.Item($before+1,$cc).NumberFormat='yyyy-mm-dd'
      for($j=0;$j -lt $i.rows.Count;$j++){$dest=$before+2+$j;$s.Rows.Item($anchor).Copy()|Out-Null;$s.Rows.Item($dest).PasteSpecial(-4122)|Out-Null;$s.Rows.Item($dest).ClearContents()|Out-Null;$s.Cells.Item($dest,$bc).Value2=[string]$i.rows[$j].bank;$s.Cells.Item($dest,$bc+1).Value2=[string]$i.rows[$j].amount;Assign $s.Cells.Item($dest,$cc) $i.rows[$j].formula;$s.Cells.Item($dest,$cc).NumberFormat='0.0000%';$s.Cells.Item($dest,$bc+1).WrapText=$true;$s.Rows.Item($dest).RowHeight=132}
      continue
     }
     for($j=0;$j -lt $count;$j++){
      $dest=$before+$j;$s.Rows.Item($anchor).Copy()|Out-Null;$s.Rows.Item($dest).PasteSpecial(-4122)|Out-Null;$s.Rows.Item($dest).ClearContents()|Out-Null
      $s.Cells.Item($dest,$bc+1).Value2=[string]$i.rows[$j].amount;Assign $s.Cells.Item($dest,$cc) $i.rows[$j].formula;$s.Cells.Item($dest,$cc).NumberFormat='0.0000%'
      $s.Cells.Item($dest,$bc+1).WrapText=$true;$s.Rows.Item($dest).RowHeight=96
     }
     $mergeStart=if($i.new_bank){$before}else{$anchor}
     if($before+$count-1 -gt $mergeStart){$s.Range($s.Cells.Item($mergeStart,$bc),$s.Cells.Item($before+$count-1,$bc)).Merge()|Out-Null}
     $s.Cells.Item($mergeStart,$bc).Value2=[string]$i.label
    }
    foreach($r in $h.date_rows){$s.Cells.Item([int]$r,$cc).Value2=[double]([datetime]::Parse($p.as_of).ToOADate());$s.Cells.Item([int]$r,$cc).NumberFormat='yyyy-mm-dd'}
    Put $s $h.existing;Remove-QuoteIcons $s $cc
    foreach($r in $h.existing){if($r.amount){$row=$s.Range([string]$r.address).Row;$s.Cells.Item($row,$bc+1).Value2=[string]$r.amount;$s.Cells.Item($row,$bc+1).WrapText=$true;$s.Cells.Item($row,$bc+1).Font.Strikethrough=$false;$s.Rows.Item($row).RowHeight=112}}
    # Existing ICBC amount rows receive new values without inserted rows. Restore
    # their bank span explicitly, including older workbooks with no native merge.
    $icbcRows=@($h.existing|Where-Object {$_.bank -eq 'ICBC' -and $_.input_row}|ForEach-Object {[int]$s.Range([string]$_.address).Row}|Sort-Object)
    for($j=0;$j -lt $icbcRows.Count;$j+=2){
     if($j+1 -ge $icbcRows.Count -or $icbcRows[$j+1] -ne $icbcRows[$j]+1){throw ('ICBC must have two adjacent amount bands: '+$h.sheet)}
     $bankArea=$s.Range($s.Cells.Item($icbcRows[$j],$bc),$s.Cells.Item($icbcRows[$j+1],$bc));$bankArea.UnMerge()|Out-Null;$bankArea.Merge()|Out-Null;$s.Cells.Item($icbcRows[$j],$bc).Value2='ICBC';$bankArea.VerticalAlignment=-4108
    }
    $scbRows=@($h.existing|Where-Object {$_.bank -eq 'SCB' -and $_.input_row}|ForEach-Object {[int]$s.Range([string]$_.address).Row}|Sort-Object)
    for($j=0;$j -lt $scbRows.Count;$j+=3){
     if($j+2 -ge $scbRows.Count -or $scbRows[$j+2] -ne $scbRows[$j]+2){throw 'SCB customer bands must be adjacent'}
     $bankArea=$s.Range($s.Cells.Item($scbRows[$j],$bc),$s.Cells.Item($scbRows[$j+2],$bc));$bankArea.UnMerge()|Out-Null;$bankArea.Merge()|Out-Null;$s.Cells.Item($scbRows[$j],$bc).Value2='SCB';$bankArea.VerticalAlignment=-4108
    }
    $delta=$s.UsedRange.Find('当日最高报价变动')
    if($null -ne $delta){$dc=$delta.Column;for($r=1;$r -le [int]$h.max_row;$r++){$cell=$s.Cells.Item($r,$dc);if($cell.HasFormula){$cell.Formula=('=IF(AND(ISNUMBER(INDEX('+ $r+':'+$r+',1,'+$cc+')),ISNUMBER(INDEX('+ $r+':'+$r+',1,'+($cc+1)+'))),INDEX('+ $r+':'+$r+',1,'+$cc+')-INDEX('+ $r+':'+$r+',1,'+($cc+1)+'),"-")')}}}
    if($h.sheet -ne '其他外币促销利率'){$s.Cells.Item(1,$bc).Value2=[string]$h.title}
    $s.Columns.Item($bc+1).ColumnWidth=60;$s.Columns.Item($cc).ColumnWidth=18
    $regular=@($h.inserts|Where-Object {$_.kind -ne 'tenor'});$formatHistory=@{bank_col=$bc;current_col=$cc;inserts=$regular};Format-BoardHistoryRows $s $formatHistory
    $excel.CalculateFull();foreach($c in $h.existing){TestCell $s $c.address $c.expected}
    foreach($i in $h.inserts){$skip=if($i.kind -eq 'tenor'){2}else{0};for($j=0;$j -lt $i.rows.Count;$j++){TestCell $s $s.Cells.Item([int]$i.target_row+$skip+$j,$cc).Address($false,$false) $i.rows[$j].expected}}
    $preview=$h.inserts|Where-Object {$_.rows.Count -gt 0}|Select-Object -First 1
    if($null -ne $preview){$previewStart=[int]$preview.target_anchor;$previewEnd=[int]$preview.target_row+[Math]::Min(4,[int]$preview.count)-1}
    else{$previewStart=[int]$h.date_rows[0];$previewEnd=[Math]::Min($previewStart+5,[int]$h.max_row)}
    Picture $s ($s.Cells.Item($previewStart,$bc).Address($false,$false)+':'+$s.Cells.Item($previewEnd,$cc+2).Address($false,$false)) ($h.currency+'-promo-preview')
   }
   $s=$w.Worksheets.Item('最高报价汇总 ');$s.Range('B73:P73').Copy()|Out-Null;$s.Range('B75:P75').PasteSpecial(-4122)|Out-Null;Put $s $p.summary;$s.Range('B27').Value2='美元促销利率市场调研 '+$p.as_of;$s.Range('E27').Value2=[double]([datetime]::Parse($p.as_of).ToOADate());$s.Range('E27').NumberFormat='yyyy-mm-dd';$s.Range('I29:I38').WrapText=$true;$s.Range('O69:P75').WrapText=$true
   foreach($r in @(69,70,71,72,73,75)){$s.Rows.Item($r).RowHeight=84}
   $s.Range('B69:P75').VerticalAlignment=-4108
   Format-FxNoticeRows $w $p
   $excel.CalculateFull();foreach($c in $p.summary){TestCell $s $c.address $c.expected}
   Format-FxSummary $s
   Picture $s 'B27:I38' 'fx-summary-preview'
   Picture $s 'B67:P75' 'other-fx-summary-preview'
   $s=$w.Worksheets.Item('Bank List');foreach($c in $p.coverage){Assign $s.Range([string]$c.address) $c.formula;$s.Range([string]$c.address).NumberFormat='0';TestCell $s $c.address $c.expected}
   foreach($h in $p.histories){foreach($i in $h.inserts){if($i.kind -eq 'tenor'){$s=$w.Worksheets.Item($h.sheet);Picture $s ($s.Cells.Item([int]$i.target_row,[int]$h.bank_col).Address($false,$false)+':'+$s.Cells.Item([int]$i.target_row+[int]$i.count-1,[int]$h.current_col+2).Address($false,$false)) ($i.currency+'-new-tenor-preview')}}}
  }else{
   $s=$w.Worksheets.Item('USD Rate + Other Currency Rates');$s.Copy([Type]::Missing,$w.Worksheets.Item($w.Worksheets.Count))|Out-Null;$temp=$w.Worksheets.Item($w.Worksheets.Count);$temp.Name='_fx_style_temp';$temp.UsedRange.UnMerge()|Out-Null
   if([int]$p.cny_delta -gt 0){$s.Rows.Item('30:'+([int]$p.cny_delta+29)).Insert()|Out-Null}
   if([int]$p.usd_delta -gt 0){$s.Rows.Item('22:'+([int]$p.usd_delta+21)).Insert()|Out-Null}
   foreach($t in $p.extra_titles){$s.Cells.Item([int]$t.row,1).Value2=[string]($t.currency+' Promo Rate '+$p.as_of);$s.Cells.Item([int]$t.row,1).Font.Bold=$true;foreach($c in @(1,5,9,13)){$temp.Range($temp.Cells.Item(3,$c),$temp.Cells.Item(3,$c+2)).Copy($s.Range($s.Cells.Item([int]$t.row+1,$c),$s.Cells.Item([int]$t.row+1,$c+2)))|Out-Null;$s.Cells.Item([int]$t.row+1,$c).Value2=@{1='1M';5='3M';9='6M';13='12M'}[$c]}}
   $rowHeights=@{}
   foreach($bl in $p.rainbow_blocks){
    $c=[int]$bl.col;$area=$s.Range($s.Cells.Item([int]$bl.start,$c),$s.Cells.Item([int]$bl.end,$c+2));$area.UnMerge()|Out-Null;$area.ClearContents()|Out-Null;$area.FormatConditions.Delete()|Out-Null
    foreach($g in $bl.groups){$row=[int]$g.target_row
     foreach($r in $g.rows){
      $sample=if($bl.currency -eq 'CNY'){25}else{4};$temp.Range($temp.Cells.Item($sample,$c),$temp.Cells.Item($sample,$c+2)).Copy($s.Range($s.Cells.Item($row,$c),$s.Cells.Item($row,$c+2)))|Out-Null
      $a=$s.Range($s.Cells.Item($row,$c),$s.Cells.Item($row,$c+2));$a.ClearContents()|Out-Null;$a.FormatConditions.Delete()|Out-Null;$a.Interior.Color=Color $bl.color;$a.Font.Size=10;$a.VerticalAlignment=-4108;$a.WrapText=$true
      Assign $s.Cells.Item($row,$c+1) $r.formula;$s.Cells.Item($row,$c+1).NumberFormat='0.0000%';$s.Cells.Item($row,$c+2).Value2=[string]$r.amount;$needed=[Math]::Min(400,[Math]::Max(84,[Math]::Ceiling($r.amount.Length/20.0)*17+28));if($rowHeights.ContainsKey($row)){$needed=[Math]::Max([double]$rowHeights[$row],[double]$needed)};$rowHeights[$row]=$needed;$s.Rows.Item($row).RowHeight=[double]$needed;$row++
     }
     if($row-[int]$g.target_row -gt 1){$s.Range($s.Cells.Item([int]$g.target_row,$c),$s.Cells.Item($row-1,$c)).Merge()|Out-Null};$s.Cells.Item([int]$g.target_row,$c).Value2=[string]$g.bank
    }
   }
   $temp.Delete();$s.Range('A1').Value2='外币促销 '+$p.as_of;$s.Range('A2').Value2='USD Promo Rate';$s.Range('A'+(23+[int]$p.usd_delta)).Value2='CNY Promo Rate（含CNH）'
   Put $s $p.mixed_cells;$offset=[int]$p.usd_delta+[int]$p.cny_delta;$s.Range('O'+(106+$offset)+':O'+(118+$offset)).WrapText=$true
   for($r=106+$offset;$r -le 118+$offset;$r++){$s.Rows.Item($r).RowHeight=150;$s.Range('N'+$r+':O'+$r).Font.Size=10;$s.Range('N'+$r+':O'+$r).WrapText=$true}
   $excel.CalculateFull()
   foreach($bl in $p.rainbow_blocks){foreach($g in $bl.groups){$r=[int]$g.target_row;foreach($x in $g.rows){TestCell $s $s.Cells.Item($r,[int]$bl.col+1).Address($false,$false) $x.expected;$r++}}}
   foreach($c in $p.mixed_cells){TestCell $s $c.address $c.expected}
   Picture $s 'I2:K12' 'usd-rainbow-promo-preview';Picture $s ('A'+(23+[int]$p.usd_delta)+':G'+(29+$offset)) 'cny-rainbow-promo-preview';Picture $s ('A'+(104+$offset)+':O'+(107+$offset)) 'mixed-fx-preview'
   foreach($t in $p.extra_titles){Picture $s ('A'+$t.row+':O'+([int]$t.row+3)) ($t.currency+'-extra-rainbow-preview')}
  }
  if($kind -eq 'report'){Format-OrdinaryMaybankBoard $w;$deltaResults=Restore-RateDeltas $w;$deltaResults|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $out 'delta-rebuild.json') -Encoding UTF8;$excel.CalculateFull()}
  $w.Save();$w.Close($false);$books=@($books|Where-Object {$_ -ne $w})
 }
 $checks|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $out 'native-checks.json') -Encoding UTF8;Write-Output ('Native FX checks passed: '+$checks.Count)
}catch{Write-Output $_.ScriptStackTrace;throw}finally{foreach($w in $books){try{$w.Close($false)}catch{}};if($null -ne $excel){$excel.Quit();[Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel)|Out-Null};[GC]::Collect();[GC]::WaitForPendingFinalizers()}
foreach($kind in @('report','rainbow')){if((Get-FileHash -LiteralPath $p.($kind+'_template')).Hash.ToLower() -ne $p.($kind+'_sha256')){throw 'Original changed'}}
