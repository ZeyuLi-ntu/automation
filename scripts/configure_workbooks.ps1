$ErrorActionPreference='Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$env:PYTHONUTF8='1'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$project=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $project
$cfg=Get-Content 'config/input-workbooks.local.json' -Raw -Encoding UTF8|ConvertFrom-Json
$latest=Get-Content 'outputs/latest-fx-promo.json' -Raw -Encoding UTF8|ConvertFrom-Json
$plan=Get-Content (Join-Path $latest.output 'table-validation-plan.json') -Raw -Encoding UTF8|ConvertFrom-Json
$form=New-Object Windows.Forms.Form
$form.Text='选择要处理的Excel';$form.Size=New-Object Drawing.Size(790,285);$form.StartPosition='CenterScreen';$form.FormBorderStyle='FixedDialog';$form.MaximizeBox=$false
$auto=New-Object Windows.Forms.CheckBox;$auto.Text='沿用上次完整输出（取消勾选后，可指定新文件）';$auto.SetBounds(20,15,730,28);$auto.Checked=($cfg.mode -ne 'selected');$form.Controls.Add($auto)
$boxes=@{}
foreach($item in @(@('report','调研表',55),@('rainbow','彩虹表',105))){
 $key=$item[0];$y=[int]$item[2]
 $label=New-Object Windows.Forms.Label;$label.Text=$item[1];$label.SetBounds(20,$y,65,25);$form.Controls.Add($label)
 $box=New-Object Windows.Forms.TextBox;$box.SetBounds(90,$y,590,25);$box.Text=if($cfg.$key){$cfg.$key}else{$plan.($key+'_output')};$form.Controls.Add($box);$boxes[$key]=$box
 $browse=New-Object Windows.Forms.Button;$browse.Text='选择…';$browse.SetBounds(690,($y-2),65,28);$browse.Tag=$box
 $browse.Add_Click({$dialog=New-Object Windows.Forms.OpenFileDialog;$dialog.Filter='Excel文件 (*.xlsx)|*.xlsx';$dialog.CheckFileExists=$true;if($dialog.ShowDialog() -eq 'OK'){$this.Tag.Text=$dialog.FileName;$auto.Checked=$false};$dialog.Dispose()});$form.Controls.Add($browse)
}
$note=New-Object Windows.Forms.Label;$note.Text='请选择与现有模板相同格式的文件。程序另存结果，原文件不覆盖。';$note.SetBounds(20,150,730,25);$form.Controls.Add($note)
$save=New-Object Windows.Forms.Button;$save.Text='保存设置';$save.SetBounds(565,190,90,30);$form.Controls.Add($save)
$cancel=New-Object Windows.Forms.Button;$cancel.Text='取消';$cancel.SetBounds(665,190,90,30);$cancel.Add_Click({$form.Close()});$form.Controls.Add($cancel)
$save.Add_Click({
 $mode=if($auto.Checked){'latest'}else{'selected'}
 $message=(& (Join-Path $project '.venv/Scripts/python.exe') -X utf8 -m scripts.configure_workbooks --mode $mode --report $boxes['report'].Text --rainbow $boxes['rainbow'].Text 2>&1|Out-String)
 if($LASTEXITCODE -eq 0){[Windows.Forms.MessageBox]::Show($message,'已保存')|Out-Null;$form.Close()}else{[Windows.Forms.MessageBox]::Show($message,'请检查文件')|Out-Null}
})
$form.ShowDialog()|Out-Null;$form.Dispose()
