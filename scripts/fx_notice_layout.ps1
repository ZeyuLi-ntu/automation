function Format-FxNoticeRows($workbook,$plan){
 $s=$workbook.Worksheets.Item('最高报价汇总 ')
 foreach($c in $plan.summary){
  if([string]$c.expected -like '*公告期*'){
   $cell=$s.Range([string]$c.address);$cell.WrapText=$true;$cell.Font.Size=10;$cell.VerticalAlignment=-4108
   $noticeRow=$s.Rows.Item([int]$cell.Row);$noticeHeight=[double]$noticeRow.RowHeight
   if($noticeHeight -lt 156){$noticeHeight=156.0}
   $noticeRow.RowHeight=[double]$noticeHeight
  }
 }
}
