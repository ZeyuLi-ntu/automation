function Format-FxSummary($sheet){
 $sheet.Range('B37:I37').Copy()|Out-Null;$sheet.Range('B38:I38').PasteSpecial(-4122)|Out-Null
 $sheet.Range('C29:G38').NumberFormat='0.00%'
 $sheet.Range('H29:I38').WrapText=$true
 $sheet.Range('B29:I38').VerticalAlignment=-4108
 $sheet.Rows.Item(38).RowHeight=84
 $title=[string]$sheet.Range('B27').Value2
 $sheet.Range('B27').Value2=($title -replace '\s*20\d{2}-\d{2}-\d{2}\s*$','')
}
