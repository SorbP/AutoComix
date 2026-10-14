# PanelView

Serieläsare med CDisplayEx:s funktioner plus automatisk zoom ruta för ruta. Körs på Windows och Linux.
Hela funktionslistan och hur den motsvarar CDisplayEx finns i [FEATURES.md](FEATURES.md).

- Öppnar bildmappar, `.cbz/.zip`, `.cbr/.rar`, `.cb7/.7z` och `.pdf`. Krypterade arkiv ger en lösenordsfråga.
- Rutor hittas i bakgrunden med OpenCV (från cbxy) och en YOLO-modell via ONNX Runtime. Hybridlogiken finns i
  `panelview/geometry.py`. Närmaste sidor detekteras först och resultatet cachas
  (Windows `%LOCALAPPDATA%\PanelView`, Linux `~/.local/share/PanelView`).
- En `.cbxy` bredvid serien (t.ex. rättad i `cbxy-editor`) går före cachen.
- Läsriktning och senaste sida sparas per serie.

## Starta
- **Windows:** `dist\windows\PanelView.exe`. `.\install.ps1` lägger till skrivbordsikon, Startmenyn och
  **Öppna i PanelView** i högerklicksmenyn (`.\install.ps1 -Uninstall` tar bort dem).
- **Linux:** `dist/linux/PanelView` (lokalt bygge kräver glibc 2.39; CI-bygget på Ubuntu 22.04 kör på äldre distar).
- Startad utan fil öppnas ett tomt fönster: dra in en mapp, ett arkiv, en PDF eller en bild.
  Släpp på ikonen, eller ange en sökväg, så öppnas serien direkt i helskärm (`--window` för fönster).

## Viktigaste tangenterna
`H` visar alla genvägar i programmet, och Inställningar → Tangenter ändrar dem.
- `→`/`←`, mellanslag, hjul, klick i kanterna: nästa/föregående ruta (eller del/sida)
- Dubbelklick på en ruta: zooma dit, även där detekteringen missat. Igen = hela sidan.
- `Ctrl+T` miniatyrlist, `Ctrl+I` sidreglage, `Ctrl+H` bildspel (ruta för ruta), `T` miniatyröversikt
- `G` guidat läge, `V` helsida först, `D` svart runt rutan, `R` japanskt läge, `Shift+D` dubbelsida
- `1`–`4` anpassning (skärm, bredd, höjd, 100 %), `M` förstoringsglas, `A` färgkorrigering, `[` `]` rotera
- `L` bläddra bland serier med förhandsvisning, `Ctrl+L` senaste serien, `N`/`B` nästa/föregående fil
- `E` redigera rutor (dra = ny ruta, dra i kant/hörn = ändra storlek, Shift+dra = flytta, högerklick/Delete = ta bort,
  Ctrl+Z = ångra, Ctrl+R = automatiskt igen, `E` igen = klar)
- `F` helskärm, `Ctrl+B` bokmärke, högerklick = meny

## Bygga
```
uv venv -p 3.12 .venv
uv pip install -p .venv -r requirements.txt pyinstaller pillow pytest
.venv/Scripts/python -m pytest -q tests
.venv/Scripts/python -m PyInstaller PanelView.spec        # -> dist/PanelView(.exe)
```
PyInstaller bygger bara för den plattform den körs på. GitHub-flödet bygger båda
(Windows och Linux) och kör ett självtest (`--selftest=res.json`).

Modellen `models/panels_int8.onnx` är exporterad från `mosesb/best-comic-panel-detection` och kvantiserad till int8
(se `build_tools/compare_ml.py`: 95 av 100 originalrutor återfunna, fp32 98 av 100).

## Träna om rutmodellen på dina rättelser
1. Läs som vanligt. När en sida blir fel: tryck `E`, rita rätt rutor (dra), ta bort fel (högerklick), `E` igen.
   Rättelsen gäller direkt och sparas, och sidan + rutorna läggs som träningsexempel i `<datamapp>/training`.
2. När minst 30 sidor är rättade: `.venv-export/Scripts/python build_tools/train_model.py`
   (kräver ultralytics och PyTorch med CUDA för rimlig tid). Skriptet mäter träffsäkerheten före/efter
   på var femte rättad sida och installerar bara en bättre modell, i `<datamapp>/models/panels_int8.onnx`.
3. PanelView använder den nya modellen vid nästa start och detekterar om sidorna. Ingen ombyggnad behövs.
4. För att bygga in modellen i programmet: kopiera den till `models/`, bygg och tagga en ny version
   (`git tag v2.x.0 && git push origin v2.x.0`), så bygger GitHub nya filer under Releases.

## Tester
- `python -m pytest -q tests` – enhetstester.
- `python build_tools/smoke.py <serie>` – kör igenom hela gränssnittet utan skärm och sparar skärmbilder i `%TEMP%/pv_smoke`.
