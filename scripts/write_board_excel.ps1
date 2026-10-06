param([Parameter(Mandatory=$true)][string]$PlanPath)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'quote_icon_formats.ps1')
$p=Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8|ConvertFrom-Json
$out=Split-Path -Parent ([IO.Path]::GetFullPath($PlanPath))
if($p.kind -ne 'board-pilot' -or $p.mode -ne 'validation_only'){throw 'Pilot copies only'}
foreach($kind in @('report','rainbow')){
 $target=[IO.Path]::GetFullPath($p.($kind+'_output'))
 if((Split-Path -Parent $target) -ne $out -or (Test-Path -LiteralPath $target)){throw 'New output path required'}
 if((Get-FileHash -LiteralPath $p.($kind+'_template')).Hash.ToLower() -ne $p.($kind+'_sha256')){throw 'Template changed'}
}
$excel=$null;$books=@();$checks=New-Object System.Collections.Generic.List[object]
function Check([string]$name,[bool]$pass){$checks.Add(@{name=$name;passed=$pass});if(-not $pass){throw ('Validation failed: '+$name)}}
function Assign($cell,$value){if($value -is [string] -and $value.StartsWith('=')){$cell.Formula=[string]$value}elseif($value -is [double] -or $value -is [int] -or $value -is [decimal]){$cell.Value2=[double]$value}else{$cell.Value2=[string]$value}}
function Eq($a,$b){if($b -is [string]){return [string]$a -ceq $b};return $null -ne $a -and [math]::Abs([double]$a-[double]$b) -lt 0.00000000001}
function Picture($s,[string]$area,[string]$name){
 $ps=$s.PageSetup;$old=@{PrintArea=$ps.PrintArea;Orientation=$ps.Orientation;Zoom=$ps.Zoom;FitToPagesWide=$ps.FitToPagesWide;FitToPagesTall=$ps.FitToPagesTall;PrintTitleRows=$ps.PrintTitleRows;PrintTitleColumns=$ps.PrintTitleColumns}
 try{$ps.PrintArea=$area;$ps.Orientation=2;$ps.Zoom=$false;$ps.FitToPagesWide=1;$ps.FitToPagesTall=1;$ps.PrintTitleRows='';$ps.PrintTitleColumns='';$s.ExportAsFixedFormat(0,(Join-Path $out ($name+'.pdf')),0,$true,$false)}
 finally{$ps.PrintArea=[string]$old.PrintArea;$ps.Orientation=[int]$old.Orientation;$ps.FitToPagesWide=[int]$old.FitToPagesWide;$ps.FitToPagesTall=[int]$old.FitToPagesTall;$ps.Zoom=$old.Zoom;$ps.PrintTitleRows=[string]$old.PrintTitleRows;$ps.PrintTitleColumns=[string]$old.PrintTitleColumns}
}
try{
 $excel=New-Object -ComObject Excel.Application;$excel.Visible=$false;$excel.DisplayAlerts=$false;$excel.EnableEvents=$false;$excel.AutomationSecurity=3;$excel.AskToUpdateLinks=$false;$excel.ScreenUpdating=$false
 $inputs=$excel.Workbooks.Open((Join-Path $out 'board-inputs.xlsx'),0,$true);$books+=,$inputs
 foreach($kind in @('report','rainbow')){
  $w=$excel.Workbooks.Open($p.($kind+'_template'),0,$true);$books+=,$w
  $w.SaveAs($p.($kind+'_output'),51)
  $inputs.Worksheets.Item(1).Copy([Type]::Missing,$w.Worksheets.Item($w.Worksheets.Count))
  if($kind -eq 'report'){
   $s=$w.Worksheets.Item('SGD挂牌');Picture $s 'A45:S54' 'before-sgd-matrix'
   $s.Range('S48').MergeArea.UnMerge()|Out-Null
   $s.Rows.Item(49).Insert()|Out-Null;$s.Range('A48:S48').Copy($s.Range('A49:S49'))|Out-Null;$s.Range('A48:A49').Merge()|Out-Null;$s.Range('A48').Value2='HLB';$s.Range('S46:S47').Merge()|Out-Null
   foreach($m in $p.matrix){$s.Cells.Item([int]$m.row,2).Value2=[string]$m.amount;$s.Cells.Item([int]$m.row,19).Value2=[string]$m.note;$s.Cells.Item([int]$m.row,19).WrapText=$true;$s.Rows.Item([int]$m.row).RowHeight=62
    foreach($c in $m.cells){Assign $s.Range($c.address) $c.formula;$s.Range($c.address).NumberFormat='0.00%'}
   }
   $s.Range('A1').Value2=[string]('新元挂牌利率（HLB/SBI '+$p.as_of+'试点；其余银行保留历史）')
   $s.Range('B48:B49').WrapText=$true
   $s=$w.Worksheets.Item('USD挂牌');Picture $s 'B66:F72' 'before-usd-history'
   $s.Columns.Item(4).Insert()|Out-Null;$s.Columns.Item(5).Copy()|Out-Null;$s.Columns.Item(4).PasteSpecial(-4122)|Out-Null
   $s.Columns.Item(4).ColumnWidth=$s.Columns.Item(5).ColumnWidth
   foreach($title in @(1)+@($p.usd_date_rows|ForEach-Object {[int]$_-1})){$s.Range($s.Cells.Item([int]$title,2),$s.Cells.Item([int]$title,252)).Merge()|Out-Null}
   for($r=1;$r -le 248;$r++){
    $cell=$s.Cells.Item($r,4)
    if(-not $cell.MergeCells){$cell.Value2='-';$cell.NumberFormat='0.0000%'}
   }
   foreach($r in $p.usd_date_rows){$s.Cells.Item([int]$r,4).Value2=[double]([datetime]::Parse($p.as_of).ToOADate());$s.Cells.Item([int]$r,4).NumberFormat='yyyy-mm-dd'}
   $s.Range('B1').Value2=[string]('美元挂牌利率（HLB/SBI '+$p.as_of+'试点；本期未采集或单位待核填-）')
   foreach($m in $p.usd_rows){Assign $s.Cells.Item([int]$m.row,4) $m.formula;$s.Cells.Item([int]$m.row,3).Value2=[string]$m.amount;$s.Cells.Item([int]$m.row,3).WrapText=$true;$s.Rows.Item([int]$m.row).RowHeight=42;$s.Cells.Item([int]$m.row,252).Value2=[string]$m.note}
   Remove-QuoteIcons $s 4
   # Rebind each existing change column to the two newest date columns.
   for($n=4;$n -le 248;$n++){$cell=$s.Cells.Item($n,251);if($cell.HasFormula){$cell.Formula=('=IF(AND(ISNUMBER(D'+$n+'),ISNUMBER(E'+$n+')),D'+$n+'-E'+$n+',"-")')}}
   $sum=$w.Worksheets.Item('最高报价汇总 ');$sum.Range('B41').Value2=[string]('美元挂牌（本期仅HLB/SBI，待复核）');$sum.Range('H41').Value2=[string]$p.as_of
   # Inserting D causes native Excel to move old summary links to E: explicitly use current D.
   for($r=43;$r -le 55;$r++){for($c=3;$c -le 10;$c++){$cell=$sum.Cells.Item($r,$c);if($cell.HasFormula){$cell.Formula=([string]$cell.Formula -replace '(USD挂牌!?|''USD挂牌''!)\$?E','${1}D')}}}
   $sum.Range('K50').Value2='USD ≥5,000 且<1,000,000';$sum.Range('L50').Value2=if($p.pending_units -contains 'SBI/USD'){'年化单位待核，暂不插入数值'}else{'见本期复核明细'};$sum.Range('L52').Value2='证据 '+$p.as_of+'；待人工复核'
   $excel.CalculateFull()
   foreach($m in $p.matrix){foreach($c in $m.cells){Check ('SGD '+$c.address) (Eq $w.Worksheets.Item('SGD挂牌').Range($c.address).Value2 $c.expected)}}
   foreach($m in $p.usd_rows){Check ('USD D'+$m.row) (Eq $s.Cells.Item([int]$m.row,4).Value2 $m.expected)}
   Picture $w.Worksheets.Item('SGD挂牌') 'A45:S55' 'after-sgd-matrix';Picture $s 'B66:F72' 'after-usd-history';Picture $sum 'B41:L55' 'after-usd-summary'
  }else{
   Picture $w.Worksheets.Item('SGD Board Rate') 'G2:I27' 'before-sgd-rainbow';Picture $w.Worksheets.Item('USD Rate + Other Currency Rates') 'E31:G64' 'before-usd-rainbow'
   foreach($name in @('SGD Board Rate','USD Rate + Other Currency Rates')){
    $s=$w.Worksheets.Item($name);$s.Copy([Type]::Missing,$w.Worksheets.Item($w.Worksheets.Count));$temp=$w.Worksheets.Item($w.Worksheets.Count);$temp.Name='_board_style_temp'
    foreach($block in @($p.rainbow_blocks|Where-Object {$_.sheet -eq $name})){
     $c=[int]$block.col;$area=$s.Range($s.Cells.Item([int]$block.start,$c),$s.Cells.Item([int]$block.end,$c+2));$area.UnMerge()|Out-Null;$area.ClearContents()|Out-Null
     foreach($g in $block.groups){$start=[int]$g.target_row;$i=0
      foreach($r in $g.rows){$dest=$start+$i;$source=[int]$r.source_row
       # Copy each bank's rate/condition styling independently of merged bank labels.
       $temp.Range($temp.Cells.Item($source,$c+1),$temp.Cells.Item($source,$c+2)).Copy($s.Range($s.Cells.Item($dest,$c+1),$s.Cells.Item($dest,$c+2)))|Out-Null
       $sc=$temp.Cells.Item($source,$c).MergeArea.Cells.Item(1,1);$dc=$s.Cells.Item($dest,$c)
       $dc.Interior.Color=$sc.Interior.Color;$dc.Font.Name=$sc.Font.Name;$dc.Font.Size=$sc.Font.Size;$dc.Font.Bold=$sc.Font.Bold;$dc.Font.Color=$sc.Font.Color;$dc.HorizontalAlignment=$sc.HorizontalAlignment;$dc.VerticalAlignment=$sc.VerticalAlignment
       Assign $s.Cells.Item($dest,$c+1) $r.formula;$s.Cells.Item($dest,$c+1).NumberFormat=if($block.currency -eq 'USD'){'0.0000%'}else{'0.00%'}
       $s.Cells.Item($dest,$c+2).Value2=[string]$r.amount;$s.Cells.Item($dest,$c+2).WrapText=$true
       if($r.updated){$s.Rows.Item($dest).RowHeight=[math]::Max(42,[double]$s.Rows.Item($dest).RowHeight)}
       $i++
      }
      $s.Range($s.Cells.Item($start,$c),$s.Cells.Item($start+$i-1,$c)).UnMerge()|Out-Null
      if($i -gt 1){$s.Range($s.Cells.Item($start,$c),$s.Cells.Item($start+$i-1,$c)).Merge()|Out-Null}
      $s.Cells.Item($start,$c).Value2=[string]$g.label
      $bankarea=$s.Range($s.Cells.Item($start,$c),$s.Cells.Item($start+$i-1,$c));$bankarea.Borders.LineStyle=1;$bankarea.Borders.Weight=2
     }
    }
    $temp.Delete()
   }
   $w.Worksheets.Item('SGD Board Rate').Range('A1').Value2=[string]('HLB/SBI '+$p.as_of+' 试点；其他银行为历史样本，排序非全市场本期排名')
   $w.Worksheets.Item('USD Rate + Other Currency Rates').Range('A31').Value2=[string]('USD Board Rates：HLB/SBI '+$p.as_of+'试点；其余历史；未核实填-')
   $excel.CalculateFull()
   foreach($b in $p.rainbow_blocks){$s=$w.Worksheets.Item($b.sheet);foreach($g in $b.groups){$n=[int]$g.target_row;foreach($r in $g.rows){Check ('Rainbow '+$b.sheet+' '+$b.tenor+' '+$n) (Eq $s.Cells.Item($n,[int]$b.col+1).Value2 $r.expected);$n++}}}
   Picture $w.Worksheets.Item('SGD Board Rate') 'G2:I28' 'after-sgd-rainbow';Picture $w.Worksheets.Item('USD Rate + Other Currency Rates') 'E31:G64' 'after-usd-rainbow'
  }
  $w.Save();$w.Close($false);$books=@($books|Where-Object {$_ -ne $w})
 }
 $checks|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $out 'native-checks.json') -Encoding UTF8
 Write-Output ('Native checks passed: '+$checks.Count)
}finally{foreach($w in $books){try{$w.Close($false)}catch{}};if($null -ne $excel){$excel.Quit();[Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel)|Out-Null};[GC]::Collect();[GC]::WaitForPendingFinalizers()}
foreach($kind in @('report','rainbow')){if((Get-FileHash -LiteralPath $p.($kind+'_template')).Hash.ToLower() -ne $p.($kind+'_sha256')){throw 'Source changed'}}
