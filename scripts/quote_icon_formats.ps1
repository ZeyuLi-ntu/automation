# Remove only icon-set coverage from the current quote column. A rule may also
# cover history or the daily comparison, so preserve those parts of AppliesTo.
function Remove-QuoteIcons($sheet,[int]$column=3) {
    $conditions=$sheet.Columns.Item($column).FormatConditions
    for($i=$conditions.Count;$i -ge 1;$i--) {
        $rule=$conditions.Item($i)
        if($rule.Type -ne 6){continue}
        $remaining=$null
        foreach($area in $rule.AppliesTo.Areas) {
            $first=[int]$area.Column;$last=$first+[int]$area.Columns.Count-1
            $top=[int]$area.Row;$bottom=$top+[int]$area.Rows.Count-1
            $parts=@()
            if($column -lt $first -or $column -gt $last){$parts+=,$area}
            else {
                if($first -lt $column){$parts+=,$sheet.Range($sheet.Cells.Item($top,$first),$sheet.Cells.Item($bottom,($column-1)))}
                if($last -gt $column){$parts+=,$sheet.Range($sheet.Cells.Item($top,($column+1)),$sheet.Cells.Item($bottom,$last))}
            }
            foreach($part in $parts){if($null -eq $remaining){$remaining=$part}else{$remaining=$sheet.Application.Union($remaining,$part)}}
        }
        if($null -eq $remaining){$rule.Delete()}else{$rule.ModifyAppliesToRange($remaining)}
    }
}
