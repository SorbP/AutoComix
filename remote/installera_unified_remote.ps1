# Kopierar AutoComix-fjärrkontrollen till Unified Remotes mapp för egna fjärrkontroller.
# Kör igen efter ändringar i remote\unified\AutoComix. Servern läser in den på nytt (annars: Reload remotes / starta om servern).
$src = Join-Path $PSScriptRoot "unified\AutoComix"
$dst = "C:\ProgramData\Unified Remote\Remotes\Custom\AutoComix"
$old = "C:\ProgramData\Unified Remote\Remotes\Custom\PanelView"  # hette PanelView före 2.16
if (Test-Path $old) { Remove-Item $old -Recurse -Force }
New-Item -ItemType Directory -Force $dst | Out-Null
Copy-Item "$src\*" $dst -Force
"Installerad i $dst"
