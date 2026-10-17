# Kopierar PanelView-fjärrkontrollen till Unified Remotes mapp för egna fjärrkontroller.
# Kör igen efter ändringar i remote\unified\PanelView. Servern läser in den på nytt (annars: Reload remotes / starta om servern).
$src = Join-Path $PSScriptRoot "unified\PanelView"
$dst = "C:\ProgramData\Unified Remote\Remotes\Custom\PanelView"
New-Item -ItemType Directory -Force $dst | Out-Null
Copy-Item "$src\*" $dst -Force
"Installerad i $dst"
