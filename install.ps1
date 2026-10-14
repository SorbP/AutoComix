# Lägger till "Öppna i PanelView" i högerklicksmenyn (mappar + seriearkiv) och en Startmeny-genväg.
# Kräver inte admin (HKCU). Ta bort med: .\install.ps1 -Uninstall
param([switch]$Uninstall)
$exe = Join-Path $PSScriptRoot 'dist\windows\PanelView.exe'
if (Test-Path $exe) {            # färdigbyggd .exe (pyinstaller PanelView.spec)
    $pyw = $exe; $app = $null
    $cmd = "`"$exe`" `"%1`""
} else {                         # annars direkt från källkoden
    $pyw = (Get-Command pythonw.exe -ErrorAction Stop).Source
    $app = Join-Path $PSScriptRoot 'PanelView.pyw'
    $cmd = "`"$pyw`" `"$app`" `"%1`""
}
$keys = @('HKCU:\Software\Classes\Directory\shell\PanelView') +
        ('.cbz', '.cbr', '.cb7', '.zip', '.rar', '.7z', '.pdf' | % { "HKCU:\Software\Classes\SystemFileAssociations\$_\shell\PanelView" })
$lnks = @((Join-Path ([Environment]::GetFolderPath('Programs')) 'PanelView.lnk'),
          (Join-Path ([Environment]::GetFolderPath('Desktop')) 'PanelView.lnk'))  # dra serier/bilder på skrivbordsikonen

if ($Uninstall) {
    $keys | % { if (Test-Path $_) { Remove-Item $_ -Recurse -Force } }
    $lnks | % { if (Test-Path $_) { Remove-Item $_ -Force } }
    'PanelView avinstallerad.'
    return
}
foreach ($k in $keys) {
    New-Item -Path "$k\command" -Force | Out-Null
    Set-ItemProperty -Path $k -Name '(default)' -Value 'Öppna i PanelView'
    Set-ItemProperty -Path $k -Name 'Icon' -Value $pyw
    Set-ItemProperty -Path "$k\command" -Name '(default)' -Value $cmd
}
foreach ($lnk in $lnks) {
    $s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
    $s.TargetPath = $pyw; if ($app) { $s.Arguments = "`"$app`"" }; $s.WorkingDirectory = $PSScriptRoot; $s.Save()
}
"PanelView installerad: skrivbordsikon + Startmenyn, högerklick på mapp/arkiv -> 'Öppna i PanelView'."
