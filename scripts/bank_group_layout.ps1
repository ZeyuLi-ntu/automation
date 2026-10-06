function Restore-CleanupBankMerges($workbook,$plan){
 foreach($history in $plan.sheets){
  $sheet=$workbook.Worksheets.Item([string]$history.sheet);$bankColumn=[int]$history.bank_col
  foreach($bank in $history.bank_merges){
   $first=[int]$bank.start;$last=[int]$bank.end
   $area=$sheet.Range($sheet.Cells.Item($first,$bankColumn),$sheet.Cells.Item($last,$bankColumn))
   $area.UnMerge()|Out-Null
   if($last -gt $first){$area.Merge()|Out-Null}
   $sheet.Cells.Item($first,$bankColumn).Value2=[string]$bank.label
   $area.VerticalAlignment=-4108
   if([int]$sheet.Cells.Item($first,$bankColumn).MergeArea.Rows.Count -ne ($last-$first+1)){throw ('Bank group merge failed: '+$history.sheet+' '+$bank.label)}
  }
 }
}

function Format-OrdinaryMaybankBoard($workbook){
 foreach($sheet in $workbook.Worksheets){
  if(-not $sheet.Name.EndsWith('挂牌') -or $sheet.Name -eq 'SGD挂牌'){continue}
  $bankColumn=2;if($sheet.Name -eq 'CNY挂牌'){$bankColumn=1}
  $last=$sheet.UsedRange.Row+$sheet.UsedRange.Rows.Count-1
  $values=$sheet.Range($sheet.Cells.Item(1,$bankColumn),$sheet.Cells.Item($last,$bankColumn+1)).Value2
  $bank=''
  for($r=1;$r -le $last;$r++){
   if($null -ne $values[$r,1] -and [string]$values[$r,1] -ne ''){$bank=[string]$values[$r,1]}
   if($bank -eq 'Maybank' -and [string]$values[$r,2] -like '*外币定存挂牌*'){
    $label=$sheet.Cells.Item($r,$bankColumn+1)
    $label.WrapText=$true;$label.VerticalAlignment=-4108
    $sheet.Rows.Item($r).RowHeight=60
    $sheet.Range($sheet.Cells.Item($r,$bankColumn+2),$sheet.Cells.Item($r,$sheet.UsedRange.Column+$sheet.UsedRange.Columns.Count-1)).VerticalAlignment=-4108
   }
  }
 }
}
