@echo off
setlocal

:: Show GUI dialog via PowerShell and capture selection
for /f "delims=" %%i in ('powershell -NoProfile -Command ^
    "Add-Type -AssemblyName System.Windows.Forms;" ^
    "$form = New-Object System.Windows.Forms.Form;" ^
    "$form.Text = 'Infoglut Launcher';" ^
    "$form.Size = New-Object System.Drawing.Size(300, 200);" ^
    "$form.StartPosition = 'CenterScreen';" ^
    "$form.FormBorderStyle = 'FixedDialog';" ^
    "$form.MaximizeBox = $false;" ^
    "$label = New-Object System.Windows.Forms.Label;" ^
    "$label.Text = 'How many Projectors would you like to launch?';" ^
    "$label.Location = New-Object System.Drawing.Point(20, 15);" ^
    "$label.Size = New-Object System.Drawing.Size(260, 35);" ^
    "$form.Controls.Add($label);" ^
    "$list = New-Object System.Windows.Forms.ListBox;" ^
    "$list.Location = New-Object System.Drawing.Point(20, 55);" ^
    "$list.Size = New-Object System.Drawing.Size(250, 50);" ^
    "[void]$list.Items.Add('1');" ^
    "[void]$list.Items.Add('2');" ^
    "$list.SelectedIndex = 0;" ^
    "$form.Controls.Add($list);" ^
    "$btnConfirm = New-Object System.Windows.Forms.Button;" ^
    "$btnConfirm.Text = 'Confirm';" ^
    "$btnConfirm.Location = New-Object System.Drawing.Point(160, 120);" ^
    "$btnConfirm.Size = New-Object System.Drawing.Size(80, 28);" ^
    "$btnConfirm.Add_Click({ $form.DialogResult = 'OK'; $form.Close() });" ^
    "$form.Controls.Add($btnConfirm);" ^
    "$btnCancel = New-Object System.Windows.Forms.Button;" ^
    "$btnCancel.Text = 'Cancel';" ^
    "$btnCancel.Location = New-Object System.Drawing.Point(70, 120);" ^
    "$btnCancel.Size = New-Object System.Drawing.Size(80, 28);" ^
    "$btnCancel.Add_Click({ $form.DialogResult = 'Cancel'; $form.Close() });" ^
    "$form.Controls.Add($btnCancel);" ^
    "$form.AcceptButton = $btnConfirm;" ^
    "$form.CancelButton = $btnCancel;" ^
    "$result = $form.ShowDialog();" ^
    "if ($result -eq 'OK') { Write-Output $list.SelectedItem } else { Write-Output 'cancel' }"^
') do set PROJ_COUNT=%%i

:: Exit if user cancelled
if /i "%PROJ_COUNT%"=="cancel" exit /b
if "%PROJ_COUNT%"=="" exit /b

:: Launch based on selection
if "%PROJ_COUNT%"=="2" (
    start "Projector 1" cmd /k "cd /d %~dp0 && python projector.py 12345"
    start "Projector 2" cmd /k "cd /d %~dp0 && python projector.py 12346"
    start "Server"      cmd /k "cd /d %~dp0 && python server.py 2"
) else (
    start "Projector 1" cmd /k "cd /d %~dp0 && python projector.py 12345"
    start "Server"      cmd /k "cd /d %~dp0 && python server.py 1"
)
start "Tunnel" cmd /k "cd /d %~dp0 && python tunnel_qr.py"
