# Adds "Open in AutoComix" ("Öppna i AutoComix" in Swedish Windows) to the right-click menu (folders + comic archives) and a Start menu shortcut.
# Does not need admin (HKCU). Remove with: .\install.ps1 -Uninstall
param([switch]$Uninstall)
$exe = Join-Path $PSScriptRoot 'dist\windows\AutoComix\AutoComix.exe'
if (Test-Path $exe) {            # prebuilt .exe (pyinstaller AutoComix.spec)
    $pyw = $exe; $app = $null
    $cmd = "`"$exe`" `"%1`""
} else {                         # otherwise straight from the source code
    $pyw = (Get-Command pythonw.exe -ErrorAction Stop).Source
    $app = Join-Path $PSScriptRoot 'AutoComix.pyw'
    $cmd = "`"$pyw`" `"$app`" `"%1`""
}
$keys = @('HKCU:\Software\Classes\Directory\shell\AutoComix') +
        ('.cbz', '.cbr', '.cb7', '.zip', '.rar', '.7z', '.pdf' | % { "HKCU:\Software\Classes\SystemFileAssociations\$_\shell\AutoComix" })
$lnks = @((Join-Path ([Environment]::GetFolderPath('Programs')) 'AutoComix.lnk'),
          (Join-Path ([Environment]::GetFolderPath('Desktop')) 'AutoComix.lnk'))  # drop comics/images on the desktop icon

# The program was called PanelView before 2.16: old right-click entries and shortcuts are always removed.
$old = @('HKCU:\Software\Classes\Directory\shell\PanelView') +
       ('.cbz', '.cbr', '.cb7', '.zip', '.rar', '.7z', '.pdf' | % { "HKCU:\Software\Classes\SystemFileAssociations\$_\shell\PanelView" })
$old | % { if (Test-Path $_) { Remove-Item $_ -Recurse -Force } }
$lnks | % { $o = $_ -replace 'AutoComix\.lnk$', 'PanelView.lnk'; if (Test-Path $o) { Remove-Item $o -Force } }

if ($Uninstall) {
    $keys | % { if (Test-Path $_) { Remove-Item $_ -Recurse -Force } }
    $lnks | % { if (Test-Path $_) { Remove-Item $_ -Force } }
    if ((Get-UICulture).TwoLetterISOLanguageName -eq 'sv') { 'AutoComix avinstallerad.' } else { 'AutoComix uninstalled.' }
    return
}
$sv = (Get-UICulture).TwoLetterISOLanguageName -eq 'sv'  # the menu text in Swedish only in Swedish Windows
$label = if ($sv) { 'Öppna i AutoComix' } else { 'Open in AutoComix' }
foreach ($k in $keys) {
    New-Item -Path "$k\command" -Force | Out-Null
    Set-ItemProperty -Path $k -Name '(default)' -Value $label
    Set-ItemProperty -Path $k -Name 'Icon' -Value $pyw
    Set-ItemProperty -Path "$k\command" -Name '(default)' -Value $cmd
}
foreach ($lnk in $lnks) {
    $s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
    $s.TargetPath = $pyw; if ($app) { $s.Arguments = "`"$app`"" }; $s.WorkingDirectory = $PSScriptRoot; $s.Save()
}
if ($sv) { "AutoComix installerad: skrivbordsikon + Startmenyn, högerklick på mapp/arkiv -> '$label'." }
else { "AutoComix installed: desktop icon + Start menu, right-click a folder/archive -> '$label'." }
