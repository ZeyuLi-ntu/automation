# Rebuild comparison cells, including blank/new rows, using the latest two dates.
function Restore-RateDeltas($workbook,$names=@('USD促销','CNY促销','其他外币促销利率','USD挂牌','CNY挂牌')){
 $results=@()
 foreach($name in $names){
  $s=$workbook.Worksheets.Item($name);$bc=if($name.StartsWith('CNY')){1}else{2};$cc=$bc+2
  $header=$s.UsedRange.Find('当日增幅',[Type]::Missing,-4163,1)
  if($null -eq $header){$header=$s.UsedRange.Find('当日最高报价变动',[Type]::Missing,-4163,1)}
  if($null -eq $header){throw ('Comparison header missing: '+$name)}
  $dc=[int]$header.Column;$last=[int]$s.UsedRange.Row+[int]$s.UsedRange.Rows.Count-1
  # Snapshot bank groups before Excel changes any merged comparison ranges.
  $bankGroups=@{}
  if($name -like '*促销*'){
   for($rr=([int]$header.Row+1);$rr -le $last;$rr++){
    $area=$s.Cells.Item($rr,$bc).MergeArea
    $bankGroups[$rr]=@([int]$area.Row,([int]$area.Row+[int]$area.Rows.Count-1))
   }
  }
  $s.Columns.Item($dc).UnMerge()|Out-Null
  $data=$s.Range($s.Cells.Item(1,1),$s.Cells.Item($last,$cc+1)).Value2
  $ranges=$null;$count=0;$done=@{}
  for($r=([int]$header.Row+1);$r -le $last;$r++){
   $label=[string]$data[$r,($bc+1)];$bank=[string]$data[$r,$bc];$now=$data[$r,$cc];$before=$data[$r,($cc+1)]
   if($label -in @('金额','全部公开报价','金额要求','日期') -or $bank -in @('银行','Bank') -or $bank -match '^Tenor:'){continue}
   if(-not $label -or ($now -ne '-' -and $now -isnot [double] -and $before -isnot [double])){continue}
   $cell=$s.Cells.Item($r,$dc)
   if($name -like '*促销*'){
    $first=$bankGroups[$r][0];$end=$bankGroups[$r][1]
    if($done.ContainsKey($first)){continue};$done[$first]=$true
    $expressions=@()
    foreach($c in @($cc,($cc+1))){
     $all=@();$personal=@();$ordinary=@()
     for($rr=$first;$rr -le $end;$rr++){
      $ref='INDEX('+$rr+':'+$rr+',1,'+$c+')';$all+=,$ref
      $description=[string]$data[$rr,($bc+1)]
      $isPersonal=$description -match '(?i)(?:/|；|\()\s*personal(?:\s|/|；|\)|$)|\bPersonal Banking\b'
      if($isPersonal){$personal+=,$ref}
      # A legacy label may omit "personal". Exclude explicitly different
      # customer tiers when falling back to legacy ordinary-customer history.
      if($isPersonal -or $description -notmatch '(?i)\b(?:priority|premier|private|citigold|prestige)\b|卓越|私人|贵宾'){$ordinary+=,$ref}
     }
     $fallbackRows=$all
     if($personal.Count -gt 0){$fallbackRows=$ordinary}
     $fallback='IF(COUNT('+($fallbackRows -join ',')+')>0,MAX('+($fallbackRows -join ',')+'),"-")'
     if($personal.Count -gt 0){$fallback='IF(COUNT('+($personal -join ',')+')>0,MAX('+($personal -join ',')+'),'+$fallback+')'}
     $expressions+=,$fallback
    }
    $deltaArea=$s.Range($s.Cells.Item($first,$dc),$s.Cells.Item($end,$dc));$deltaArea.ClearContents()|Out-Null
    if($end -gt $first){$deltaArea.Merge()|Out-Null}
    $cell=$s.Cells.Item($first,$dc);$cell.Formula=('=IF(COUNT('+$expressions[0]+','+$expressions[1]+')=2,ROUND(('+ $expressions[0]+')-('+$expressions[1]+'),8),"-")')
   }else{
    $cell.Formula=('=IF(COUNT(INDEX('+$r+':'+$r+',1,'+$cc+'),INDEX('+$r+':'+$r+',1,'+($cc+1)+'))=2,ROUND(INDEX('+$r+':'+$r+',1,'+$cc+')-INDEX('+$r+':'+$r+',1,'+($cc+1)+'),8),"-")')
   }
   $cell.NumberFormat='0.00%'
   $cell.HorizontalAlignment=-4108;$cell.VerticalAlignment=-4108
   if($null -eq $ranges){$ranges=$cell}else{$ranges=$workbook.Application.Union($ranges,$cell)};$count++
  }
  if($null -ne $ranges){$ranges.FormatConditions.Delete()|Out-Null;$rule=$ranges.FormatConditions.AddIconSetCondition();$rule.IconSet=$workbook.IconSets.Item(1);$rule.IconCriteria.Item(2).Type=0;$rule.IconCriteria.Item(2).Value=0;$rule.IconCriteria.Item(2).Operator=7;$rule.IconCriteria.Item(2).Icon=-1;$rule.IconCriteria.Item(3).Type=0;$rule.IconCriteria.Item(3).Value=0;$rule.IconCriteria.Item(3).Operator=5}
  # Preserve the same grouping in the saved workbook for the next run.
  foreach($group in $bankGroups.Values){
   $first=$group[0];$end=$group[1]
   if($end -le $first){continue}
   $area=$s.Range($s.Cells.Item($first,$bc),$s.Cells.Item($end,$bc))
   if([int]$s.Cells.Item($first,$bc).MergeArea.Rows.Count -ne ($end-$first+1)){
    $area.UnMerge()|Out-Null;$area.Merge()|Out-Null
    $s.Cells.Item($first,$bc).Value2=[string]$data[$first,$bc]
   }
  }
  $results+=@{sheet=$name;column=$dc;rows=$count}
 }
 return $results
}
