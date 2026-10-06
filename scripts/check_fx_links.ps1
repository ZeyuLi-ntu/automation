param([Parameter(Mandatory=$true)][string]$PlanPath)
$ErrorActionPreference='Stop'
$p=Get-Content -Raw -Encoding UTF8 -LiteralPath $PlanPath|ConvertFrom-Json
$out=Split-Path (Resolve-Path $PlanPath)
$excel=$null;$w=$null;$results=@()
try{
 $excel=New-Object -ComObject Excel.Application;$excel.Visible=$false;$excel.DisplayAlerts=$false;$excel.EnableEvents=$false;$excel.AutomationSecurity=3;$excel.AskToUpdateLinks=$false
 foreach($kind in @('report','rainbow')){
  $path=$p.($kind+'_output');$hash=(Get-FileHash -LiteralPath $path).Hash
  $w=$excel.Workbooks.Open($path,0,$true)
  foreach($bank in @('SCB','DBS')){
   $offer=$p.details|Where-Object {$_.bank -eq $bank -and $_.insertable -and $_.audience -eq 'personal'}|Select-Object -First 1
   $inputRow=[int]$offer.input_row;$s=$w.Worksheets.Item($p.input_sheet);$driver=$s.Cells.Item($inputRow,$(if($bank -eq 'DBS'){19}else{9}));$old=[double]$driver.Value2
   $expected=[double]$s.Cells.Item($inputRow,9).Value2+0.0001;$driver.Value2=$old+0.0001;$excel.CalculateFull()
   if([math]::Abs([double]$s.Cells.Item($inputRow,9).Value2-$expected) -gt 0.00000001){throw 'Input calculation failed'}
   $count=0;$token='!I'+$inputRow+'(?![0-9])'
   if($kind -eq 'report'){
    foreach($h in $p.histories){foreach($i in $h.inserts){$skip=if($i.kind -eq 'tenor'){2}else{0};for($j=0;$j -lt $i.rows.Count;$j++){if($i.rows[$j].formula -match $token){$got=[double]$w.Worksheets.Item($h.sheet).Cells.Item([int]$i.target_row+$skip+$j,[int]$h.current_col).Value2;if([math]::Abs($got-$expected) -gt 0.00000001){throw 'Research linkage failed'};$count++}}}}
   }else{
    foreach($b in $p.rainbow_blocks){foreach($g in $b.groups){for($j=0;$j -lt $g.rows.Count;$j++){if($g.rows[$j].formula -match $token){$got=[double]$w.Worksheets.Item('USD Rate + Other Currency Rates').Cells.Item([int]$g.target_row+$j,[int]$b.col+1).Value2;if([math]::Abs($got-$expected) -gt 0.00000001){throw 'Rainbow linkage failed'};$count++}}}}
   }
   if($count -lt 1){throw 'No linked cells checked'}
   $results+=@{workbook=$kind;bank=$bank;linked_cells=$count;passed=$true};$driver.Value2=$old;$excel.CalculateFull()
  }
  $w.Close($false);$w=$null;if((Get-FileHash -LiteralPath $path).Hash -ne $hash){throw 'Validation modified output'}
 }
 $results|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $out 'formula-link-checks.json') -Encoding UTF8
 Write-Output 'Four native formula propagation checks passed; files unchanged.'
}finally{if($null -ne $w){$w.Close($false)};if($null -ne $excel){$excel.Quit();[Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel)|Out-Null};[GC]::Collect();[GC]::WaitForPendingFinalizers()}
