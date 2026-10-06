function Format-BoardHistoryRows($sheet,$history){
 $bc=[int]$history.bank_col;$cc=[int]$history.current_col
 foreach($group in $history.inserts){
  for($j=0;$j -lt [int]$group.count;$j++){
   $row=[int]$group.target_row+$j;$text=[string]$group.rows[$j].amount
   $sheet.Rows.Item($row).RowHeight=[Math]::Max(48,[Math]::Ceiling($text.Length/36.0)*18+12)
   $sheet.Range($sheet.Cells.Item($row,$bc+1),$sheet.Cells.Item($row,$cc)).VerticalAlignment=-4108
  }
  $sheet.Cells.Item([int]$group.target_anchor,$bc).MergeArea.VerticalAlignment=-4108
 }
}
