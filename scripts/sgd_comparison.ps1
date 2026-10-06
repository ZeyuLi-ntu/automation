function Restore-SGDTargetDeltas($workbook){
 $s=$workbook.Worksheets.Item('SGD促销')
 $header=$s.UsedRange.Find('当日最高报价变动',[Type]::Missing,-4163,1)
 if($null -eq $header){throw 'SGD comparison header missing'}
 $dc=[int]$header.Column;$last=$s.UsedRange.Row+$s.UsedRange.Rows.Count-1
 $data=$s.Range($s.Cells.Item(1,1),$s.Cells.Item($last,$dc-1)).Value2
 $results=@()
 for($r=1;$r -le $last;$r++){
  if([string]$data[$r,1] -notin @('UOB','Singapura Finance')){continue}
  $area=$s.Cells.Item($r,1).MergeArea;$end=$r+$area.Rows.Count-1;$previous=4;$found=$false
  for($c=4;$c -lt $dc;$c++){
   for($rr=$r;$rr -le $end;$rr++){if($data[$rr,$c] -is [double]){$previous=$c;$found=$true;break}}
   if($found){break}
  }
  $now=$s.Range($s.Cells.Item($r,3),$s.Cells.Item($end,3)).Address($false,$false)
  $prior=$s.Range($s.Cells.Item($r,$previous),$s.Cells.Item($end,$previous)).Address($false,$false)
  $target=$s.Range($s.Cells.Item($r,$dc),$s.Cells.Item($end,$dc))
  $target.UnMerge()|Out-Null;$target.ClearContents()|Out-Null
  if($end -gt $r){$target.Merge()|Out-Null}
  $cell=$s.Cells.Item($r,$dc)
  $cell.Formula='=IF(COUNT('+$now+')=0,"-",IF(COUNT('+$prior+')=0,"无上期数据",ROUND(MAX('+$now+')-MAX('+$prior+'),8)))'
  $cell.NumberFormat='0.00%';$cell.HorizontalAlignment=-4108;$cell.VerticalAlignment=-4108
  $target.FormatConditions.Delete()|Out-Null
  $rule=$target.FormatConditions.AddIconSetCondition();$rule.IconSet=$workbook.IconSets.Item(1)
  $rule.IconCriteria.Item(2).Type=0;$rule.IconCriteria.Item(2).Value=0;$rule.IconCriteria.Item(2).Operator=7
  $rule.IconCriteria.Item(2).Icon=-1
  $rule.IconCriteria.Item(3).Type=0;$rule.IconCriteria.Item(3).Value=0;$rule.IconCriteria.Item(3).Operator=5
  $results+=@{bank=[string]$data[$r,1];row=$r;end=$end;delta_column=$dc;previous_column=$previous;has_history=$found}
 }
 return $results
}
