# Copies the AutoComix remote to Unified Remote's folder for custom remotes and writes in where AutoComix.exe is
# (the "Start AutoComix" button). -Exe gives the path if the program is somewhere else.
# The buttons are Swedish in Swedish Windows, otherwise English (remote\layout_en.xml); -Lang sv/en chooses explicitly.
# Run again after changes in remote\unified\AutoComix. The server reloads it (otherwise: Reload remotes / restart the server).
param([string]$Exe, [string]$Lang)
$src = Join-Path $PSScriptRoot "unified\AutoComix"
$dst = "C:\ProgramData\Unified Remote\Remotes\Custom\AutoComix"
$old = "C:\ProgramData\Unified Remote\Remotes\Custom\PanelView"  # called PanelView before 2.16
if (-not $Exe) {
    $Exe = @((Join-Path $PSScriptRoot "..\dist\windows\AutoComix\AutoComix.exe"),
             (Join-Path $PSScriptRoot "..\AutoComix.exe")) | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $Exe) { throw "Hittar inte AutoComix.exe / AutoComix.exe not found – ange -Exe <sökväg/path>" }
$Exe = (Resolve-Path $Exe).Path
if (Test-Path $old) { Remove-Item $old -Recurse -Force }
New-Item -ItemType Directory -Force $dst | Out-Null
Copy-Item "$src\*" $dst -Force
if (-not $Lang) { $Lang = (Get-UICulture).TwoLetterISOLanguageName }
if ($Lang -ne 'sv') { Copy-Item (Join-Path $PSScriptRoot "layout_en.xml") (Join-Path $dst "layout.xml") -Force }
$lua = Join-Path $dst "remote.lua"
$text = [IO.File]::ReadAllText($lua).Replace("@@EXE@@", $Exe.Replace("\", "\\"))
[IO.File]::WriteAllText($lua, $text, (New-Object Text.UTF8Encoding $false))  # without BOM, like the original
"Installerad / installed: $dst  ($Exe)"
