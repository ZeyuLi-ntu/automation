param([Parameter(Mandatory=$true)][string]$PlanPath)
$ErrorActionPreference='Stop'
$out=Split-Path -Parent ([IO.Path]::GetFullPath($PlanPath))
$p=Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8 | ConvertFrom-Json
$samples=Get-Content -LiteralPath (Join-Path $out 'style-samples.json') -Raw -Encoding UTF8 | ConvertFrom-Json
function Signature($cell) {
    $f=$cell.Font;$fill=$cell.Interior
    $values=@($f.Name,$f.Size,$f.Bold,$f.Italic,$f.Underline,$f.Strikethrough,$f.Color,
      $fill.Pattern,$fill.Color,$cell.NumberFormat,$cell.HorizontalAlignment,$cell.VerticalAlignment,
      $cell.WrapText,$cell.ShrinkToFit,$cell.IndentLevel,$cell.Orientation,$cell.Locked,$cell.FormulaHidden)
    foreach($i in @(7,8,9,10)) {
        $edge=$cell.Borders.Item($i);$values+=($edge.LineStyle)
        if ($edge.LineStyle -ne -4142) {$values+=($edge.Weight);$values+=($edge.Color)}
    }
    return (($values | ForEach-Object {if($null -eq $_ -or $_ -is [DBNull]){'<mixed>'} elseif($_.GetType().IsEnum){[int]$_} else {$_}}) | ConvertTo-Json -Compress)
}
$excel=$null;$a=$null;$b=$null;$results=New-Object System.Collections.Generic.List[object]
try {
    $excel=New-Object -ComObject Excel.Application
    $excel.Visible=$false;$excel.DisplayAlerts=$false;$excel.EnableEvents=$false;$excel.AutomationSecurity=3;$excel.AskToUpdateLinks=$false
    foreach($kind in @('report','rainbow')) {
        $a=$excel.Workbooks.Open($p.($kind+'_template'),0,$true)
        $b=$excel.Workbooks.Open($p.($kind+'_output'),0,$true)
        foreach($s in @($samples | Where-Object {$_.kind -eq $kind})) {
            $left=Signature $a.Worksheets.Item($s.sheet).Range($s.source)
            $right=Signature $b.Worksheets.Item($s.sheet).Range($s.target)
            $results.Add(@{kind=$kind;sheet=$s.sheet;source=$s.source;target=$s.target;represented_cells=$s.represented_cells;passed=($left -eq $right);before=$left;after=$right})
        }
        $a.Close($false);$b.Close($false);$a=$null;$b=$null
    }
    ConvertTo-Json -InputObject @($results.ToArray()) -Depth 6 | Set-Content -LiteralPath (Join-Path $out 'native-style-checks.json') -Encoding UTF8
    @{report=(Get-FileHash -LiteralPath $p.report_output -Algorithm SHA256).Hash.ToLower();rainbow=(Get-FileHash -LiteralPath $p.rainbow_output -Algorithm SHA256).Hash.ToLower()} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'native-style-hashes.json') -Encoding UTF8
    $failed=@($results | Where-Object {-not $_.passed})
    Write-Output ('样式组合：'+$results.Count+'；实际显示属性不一致：'+$failed.Count)
    if ($failed.Count) {$failed | Select-Object -First 5 | ConvertTo-Json -Depth 5;throw 'Native style validation failed'}
} finally {
    foreach($book in @($a,$b)) {if($null -ne $book){$book.Close($false)}}
    if($null -ne $excel){$excel.Quit();[Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel) | Out-Null}
    [GC]::Collect();[GC]::WaitForPendingFinalizers()
}
