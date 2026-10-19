# Kopierar AutoComix-fjärrkontrollen till Unified Remotes mapp för egna fjärrkontroller och skriver in var
# AutoComix.exe ligger (knappen "Starta AutoComix"). -Exe anger sökvägen om programmet ligger någon annanstans.
# Kör igen efter ändringar i remote\unified\AutoComix. Servern läser in den på nytt (annars: Reload remotes / starta om servern).
param([string]$Exe)
$src = Join-Path $PSScriptRoot "unified\AutoComix"
$dst = "C:\ProgramData\Unified Remote\Remotes\Custom\AutoComix"
$old = "C:\ProgramData\Unified Remote\Remotes\Custom\PanelView"  # hette PanelView före 2.16
if (-not $Exe) {
    $Exe = @((Join-Path $PSScriptRoot "..\dist\windows\AutoComix\AutoComix.exe"),
             (Join-Path $PSScriptRoot "..\AutoComix.exe")) | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $Exe) { throw "Hittar inte AutoComix.exe / AutoComix.exe not found – ange -Exe <sökväg/path>" }
$Exe = (Resolve-Path $Exe).Path
if (Test-Path $old) { Remove-Item $old -Recurse -Force }
New-Item -ItemType Directory -Force $dst | Out-Null
Copy-Item "$src\*" $dst -Force
$lua = Join-Path $dst "remote.lua"
$text = [IO.File]::ReadAllText($lua).Replace("@@EXE@@", $Exe.Replace("\", "\\"))
[IO.File]::WriteAllText($lua, $text, (New-Object Text.UTF8Encoding $false))  # utan BOM, som originalet
"Installerad / installed: $dst  ($Exe)"
