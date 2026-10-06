param([Parameter(Mandatory=$true)][string]$PlanPath)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'quote_icon_formats.ps1')
$p=Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8|ConvertFrom-Json
$out=Split-Path -Parent ([IO.Path]::GetFullPath($PlanPath))
if($p.kind -ne 'board-batch' -or $p.mode -ne 'validation_only'){throw 'Batch copies only'}
foreach($kind in @('report','rainbow')){
 $target=[IO.Path]::GetFullPath($p.($kind+'_output'))
 if((Split-Path -Parent $target) -ne $out -or (Test-Path -LiteralPath $target)){throw 'New output path required'}
 if((Get-FileHash -LiteralPath $p.($kind+'_template')).Hash.ToLower() -ne $p.($kind+'_sha256')){throw 'Template changed'}
}
$excel=$null;$books=@();$checks=New-Object System.Collections.Generic.List[object]
function Check([string]$name,[bool]$pass){$checks.Add(@{name=$name;passed=$pass});if(-not $pass){throw ('Validation failed: '+$name)}}
function Assign($cell,$value){if($value -is [string] -and $value.StartsWith('=')){$cell.Formula=[string]$value}elseif($value -is [double] -or $value -is [int] -or $value -is [decimal]){$cell.Value2=[double]$value}else{$cell.Value2=[string]$value}}
function Eq($a,$b){if($b -is [string]){return [string]$a -ceq $b};return $null -ne $a -and [math]::Abs([double]$a-[double]$b) -lt 0.00000000001}
function PutCells($s,$rows){foreach($c in $rows){Assign $s.Range($c.address) $c.formula;if($c.formula -is [string] -and $c.formula.StartsWith('=')){$s.Range($c.address).NumberFormat='0.0000%'}}}
function CheckCells($s,$rows){foreach($c in $rows){Check ($s.Name+' '+$c.address) (Eq $s.Range($c.address).Value2 $c.expected)}}
function Picture($s,[string]$area,[string]$name){
 $ps=$s.PageSetup;$old=@{PrintArea=$ps.PrintArea;Orientation=$ps.Orientation;Zoom=$ps.Zoom;FitToPagesWide=$ps.FitToPagesWide;FitToPagesTall=$ps.FitToPagesTall;PrintTitleRows=$ps.PrintTitleRows;PrintTitleColumns=$ps.PrintTitleColumns}
 try{$ps.PrintArea=$area;$ps.Orientation=2;$ps.Zoom=$false;$ps.FitToPagesWide=1;$ps.FitToPagesTall=1;$ps.PrintTitleRows='';$ps.PrintTitleColumns='';$s.ExportAsFixedFormat(0,(Join-Path $out ($name+'.pdf')),0,$true,$false)}
 finally{$ps.PrintArea=[string]$old.PrintArea;$ps.Orientation=[int]$old.Orientation;$ps.FitToPagesWide=[int]$old.FitToPagesWide;$ps.FitToPagesTall=[int]$old.FitToPagesTall;$ps.Zoom=$old.Zoom;$ps.PrintTitleRows=[string]$old.PrintTitleRows;$ps.PrintTitleColumns=[string]$old.PrintTitleColumns}
}
try{
 $excel=New-Object -ComObject Excel.Application;$excel.Visible=$false;$excel.DisplayAlerts=$false;$excel.EnableEvents=$false;$excel.AutomationSecurity=3;$excel.AskToUpdateLinks=$false;$excel.ScreenUpdating=$false
 $inputs=$excel.Workbooks.Open((Join-Path $out 'board-inputs.xlsx'),0,$true);$books+=,$inputs
 foreach($kind in @('report','rainbow')){
  $w=$excel.Workbooks.Open($p.($kind+'_template'),0,$true);$books+=,$w;$w.SaveAs($p.($kind+'_output'),51)
  $inputs.Worksheets.Item(1).Copy([Type]::Missing,$w.Worksheets.Item($w.Worksheets.Count))|Out-Null
  if($kind -eq 'report'){
   foreach($name in @('SGD挂牌','AUD挂牌','NZD挂牌','CAD挂牌','HKD挂牌','EUR挂牌','GBP挂牌')){
    $s=$w.Worksheets.Item($name);$area=if($name -eq 'SGD挂牌'){'A24:S33'}else{'B27:N36'};Picture $s $area ('before-'+$name)
    foreach($m in @($p.matrices|Where-Object {$_.sheet -eq $name})){
     $s.Cells.Item([int]$m.row,[int]$m.amount_col).Value2=[string]$m.amount;$s.Cells.Item([int]$m.row,[int]$m.amount_col).WrapText=$true
     $note=$s.Cells.Item([int]$m.row,[int]$m.note_col);if($note.MergeCells){$note.MergeArea.UnMerge()|Out-Null};$note.Value2=[string]$m.note;$note.WrapText=$true
     $s.Rows.Item([int]$m.row).RowHeight=56;PutCells $s $m.cells
    }
    $banklabel=(@($p.matrices|Where-Object {$_.sheet -eq $name}|Select-Object -ExpandProperty bank -Unique)-join '/')
    $s.Cells.Item(1, $(if($name -eq 'SGD挂牌'){1}else{2})).Value2=[string]($name+' '+$p.as_of+' '+$banklabel+'本批更新；其余保留历史')
    $excel.CalculateFull();foreach($m in @($p.matrices|Where-Object {$_.sheet -eq $name})){CheckCells $s $m.cells}
    Picture $s $area ('after-'+$name)
   }
   foreach($h in $p.histories){
    $s=$w.Worksheets.Item($h.sheet);$cc=[int]$h.current_col
    Picture $s $(if($h.currency -eq 'USD'){'B34:F40'}else{'A8:E14'}) ('before-'+$h.currency+'-history')
    if($h.insert){
     $merges=@();foreach($addr in $h.merges){$ma=$s.Range([string]$addr);$merges+=,@($ma.Row,$ma.Column,$ma.Rows.Count,$ma.Columns.Count)}
     $s.Columns.Item($cc).Insert()|Out-Null;$s.Columns.Item($cc+1).Copy()|Out-Null;$s.Columns.Item($cc).PasteSpecial(-4122)|Out-Null;$s.Columns.Item($cc).ColumnWidth=$s.Columns.Item($cc+1).ColumnWidth
     foreach($m in $merges){$left=[int]$m[1];$right=$left+[int]$m[3]-1;if($left -ge $cc){$left++};if($right -ge $cc){$right++};$s.Range($s.Cells.Item([int]$m[0],$left),$s.Cells.Item([int]$m[0]+[int]$m[2]-1,$right)).Merge()|Out-Null}
     for($r=1;$r -le [int]$h.max_row;$r++){$cell=$s.Cells.Item($r,$cc);if(-not $cell.MergeCells){$cell.Value2='-';$cell.NumberFormat='0.0000%'}}
    }
    foreach($r in $h.date_rows){$s.Cells.Item([int]$r,$cc).Value2=[double]([datetime]::Parse($p.as_of).ToOADate());$s.Cells.Item([int]$r,$cc).NumberFormat='yyyy-mm-dd'}
    PutCells $s $h.cells;Remove-QuoteIcons $s $cc
    $s.Cells.Item(1,$cc-2).Value2=[string]($h.currency+'挂牌 '+$p.as_of+'；本期覆盖见输入明细，其他本期填-')
    if($h.currency -eq 'USD'){
     $dc=251+$(if($h.insert){1}else{0});for($r=4;$r -le [int]$h.max_row;$r++){$cell=$s.Cells.Item($r,$dc);if($cell.HasFormula){$cell.Formula=('=IF(AND(ISNUMBER(D'+$r+'),ISNUMBER(E'+$r+')),D'+$r+'-E'+$r+',"-")')}}
    }
    $excel.CalculateFull();CheckCells $s $h.cells
    Picture $s $(if($h.currency -eq 'USD'){'B34:F40'}else{'A8:E14'}) ('after-'+$h.currency+'-history')
   }
   $s=$w.Worksheets.Item('最高报价汇总 ');PutCells $s $p.summary;$s.Range('B41').Value2='美元挂牌（BOC/HLB/SBI本期；其余未采集）';$s.Range('H41').Value2=[string]$p.as_of;$s.Range('H58').Value2=[string]$p.as_of
   $s.Range('K43').Value2=[string]$p.usd_minimum;$s.Range('L43').Value2='本期BOC；待复核';$s.Range('J60').Value2=[string]$p.cny_minimum;$s.Range('K60').Value2='本期仅BOC；待复核'
   $s.Range('J60:K60').WrapText=$true;$s.Rows.Item(60).RowHeight=48
   $excel.CalculateFull();CheckCells $s $p.summary;Picture $s 'B41:L64' 'after-board-summary'
  }else{
   foreach($name in @('SGD Board Rate','USD Rate + Other Currency Rates')){
    $s=$w.Worksheets.Item($name);Picture $s $(if($name -eq 'SGD Board Rate'){'G2:I28'}else{'E31:G64'}) ('before-'+$(if($name -eq 'SGD Board Rate'){'sgd'}else{'usd'})+'-rainbow')
    $s.Copy([Type]::Missing,$w.Worksheets.Item($w.Worksheets.Count))|Out-Null;$temp=$w.Worksheets.Item($w.Worksheets.Count);$temp.Name='_batch_style_temp'
    if($name -ne 'SGD Board Rate' -and [int]$p.rainbow_shift -gt 0){$s.Rows.Item(('65:'+([int]$p.rainbow_shift+64))).Insert()|Out-Null}
    foreach($block in @($p.rainbow_blocks|Where-Object {$_.sheet -eq $name})){
     $c=[int]$block.col;$area=$s.Range($s.Cells.Item([int]$block.start,$c),$s.Cells.Item([int]$block.end,$c+2));$area.UnMerge()|Out-Null;$area.ClearContents()|Out-Null
     foreach($g in $block.groups){$start=[int]$g.target_row;$i=0
      foreach($r in $g.rows){$dest=$start+$i;$source=[int]$r.source_row
       $temp.Range($temp.Cells.Item($source,$c+1),$temp.Cells.Item($source,$c+2)).Copy($s.Range($s.Cells.Item($dest,$c+1),$s.Cells.Item($dest,$c+2)))|Out-Null
       $sc=$temp.Cells.Item($source,$c).MergeArea.Cells.Item(1,1);$dc=$s.Cells.Item($dest,$c)
       $dc.Interior.Color=$sc.Interior.Color;$dc.Font.Name=$sc.Font.Name;$dc.Font.Size=$sc.Font.Size;$dc.Font.Bold=$sc.Font.Bold;$dc.Font.Color=$sc.Font.Color;$dc.HorizontalAlignment=$sc.HorizontalAlignment;$dc.VerticalAlignment=$sc.VerticalAlignment
       Assign $s.Cells.Item($dest,$c+1) $r.formula;$s.Cells.Item($dest,$c+1).NumberFormat='0.0000%';$s.Cells.Item($dest,$c+2).Value2=[string]$r.amount;$s.Cells.Item($dest,$c+2).WrapText=$true
       if($r.updated){$s.Rows.Item($dest).RowHeight=[math]::Max(48,[double]$s.Rows.Item($dest).RowHeight)};$i++
      }
      if($i -gt 1){$s.Range($s.Cells.Item($start,$c),$s.Cells.Item($start+$i-1,$c)).Merge()|Out-Null}
      $s.Cells.Item($start,$c).Value2=[string]$g.label;$bankarea=$s.Range($s.Cells.Item($start,$c),$s.Cells.Item($start+$i-1,$c));$bankarea.Borders.LineStyle=1;$bankarea.Borders.Weight=2
     }
    }
    $temp.Delete()
   }
   $s=$w.Worksheets.Item('USD Rate + Other Currency Rates');PutCells $s $p.rainbow_cells
   $s.Range('I'+(68+[int]$p.rainbow_shift)+':J'+(68+[int]$p.rainbow_shift)).WrapText=$true;$s.Rows.Item(68+[int]$p.rainbow_shift).RowHeight=60
   $s.Range('A31').Value2='USD Board Rates '+$p.as_of+' BOC/HLB/SBI；其余历史';$s.Range('A'+(66+[int]$p.rainbow_shift)).Value2='RMB Board Rate '+$p.as_of+' 本期仅BOC'
   $w.Worksheets.Item('SGD Board Rate').Range('A1').Value2='SGD挂牌 '+$p.as_of+' BOC/HLB/SBI更新；其余历史'
   $excel.CalculateFull();CheckCells $s $p.rainbow_cells
   foreach($b in $p.rainbow_blocks){$s=$w.Worksheets.Item($b.sheet);foreach($g in $b.groups){$n=[int]$g.target_row;foreach($r in $g.rows){Check ('Rainbow '+$b.tenor+' '+$n) (Eq $s.Cells.Item($n,[int]$b.col+1).Value2 $r.expected);$n++}}}
   Picture $w.Worksheets.Item('SGD Board Rate') 'G2:I32' 'after-sgd-rainbow';Picture $w.Worksheets.Item('USD Rate + Other Currency Rates') 'E31:G64' 'after-usd-rainbow'
   $sh=[int]$p.rainbow_shift;Picture $w.Worksheets.Item('USD Rate + Other Currency Rates') ('A'+(66+$sh)+':J'+(78+$sh)) 'after-cny-rainbow';Picture $w.Worksheets.Item('USD Rate + Other Currency Rates') ('A'+(80+$sh)+':O'+(95+$sh)) 'after-fx-rainbow'
  }
  $w.Save();$w.Close($false);$books=@($books|Where-Object {$_ -ne $w})
 }
 $checks|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $out 'native-checks.json') -Encoding UTF8
 Write-Output ('Native checks passed: '+$checks.Count)
}finally{foreach($w in $books){try{$w.Close($false)}catch{}};if($null -ne $excel){$excel.Quit();[Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel)|Out-Null};[GC]::Collect();[GC]::WaitForPendingFinalizers()}
foreach($kind in @('report','rainbow')){if((Get-FileHash -LiteralPath $p.($kind+'_template')).Hash.ToLower() -ne $p.($kind+'_sha256')){throw 'Source changed'}}
