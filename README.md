# AutoComix

Serieläsare med CDisplayEx:s funktioner plus automatisk zoom ruta för ruta. Körs på Windows och Linux.
Hela funktionslistan och hur den motsvarar CDisplayEx finns i [FEATURES.md](FEATURES.md).

- Öppnar bildmappar, `.cbz/.zip`, `.cbr/.rar`, `.cb7/.7z` och `.pdf`. Krypterade arkiv ger en lösenordsfråga.
- Rutor hittas i bakgrunden med OpenCV (från cbxy) och en YOLO-modell via ONNX Runtime. Hybridlogiken finns i
  `panelview/geometry.py`. Närmaste sidor detekteras först och resultatet cachas
  (Windows `%LOCALAPPDATA%\AutoComix`, Linux `~/.local/share/AutoComix`).
- En `.cbxy` bredvid serien (t.ex. rättad i `cbxy-editor`) går före cachen.
- Läsriktning, sida och ruta sparas löpande per serie. Ctrl+L öppnar senaste serien där du var;
  Arkiv → Visningshistorik (Ctrl+Shift+H) visar de 20 senaste med position. Vid hård krasch skrivs `crash.log` i datamappen.
- Helskärm: menyraden visas när musen förs till överkanten.
- Storlek: Ctrl+Shift+Upp/Ned (eller Inställningar → Visning) ändrar text, listor, menyer och dialoger.
  Avståndsläge (Shift+F): sidräknaren blir stor (3× som standard) och döljs efter 1 s utan tangent/mus,
  resten av gränssnittet blir 1,5× större. Allt ställbart under Storlek och avstånd.
- Förstoringsglas (M): Visa → Förstoringsglas väljer form – rektangel, kvadrat, rund (platta) eller lins (förvrängd).
  Medan glaset är på: Shift+hjul = storlek, Ctrl+hjul = förstoring.
- Animerade sidor (GIF, animerad WebP, APNG) spelas direkt, även inzoomat på en ruta. P = paus/spela,
  `.`/`,` = bildruta fram/bak, Ctrl+Upp/Ned = hastighet. Räknaren visar `▶ 3/40`. Bildspelet väntar tills
  animationen gått ett varv (Navigera → Animation). Max 256 MB per animation; större skalas ner.
- Varje ruta visas hel på en skärm, så stor som möjligt (längsta sidan i förhållande till skärmen styr).
- Andra skärmen (F9 växlar, eller Visa → Andra skärmen): **Spegling** visar samma ruta/sida i helskärm på den andra
  skärmen, anpassad till dess format. **Automatisk fördelning** visar liggande rutor/sidor på den liggande skärmen och
  stående på den stående; den andra skärmen behåller sin senaste bild. Båda styrs från huvudfönstret (tangenter,
  handkontroll) och läget sparas till nästa start. Har skärmarna samma orientering fungerar fördelningen som spegling.
  Hela sidor har en egen anpassning på andra skärmen (Shift+F9): skärm, bredd, höjd eller samma utsnitt som
  huvudfönstret – så huvudfönstret kan stå på "anpassa till bredd" och den stående skärmen visa hela sidan.
- Bläddraren (L): "Visa alla sidor" (P) visar arkivets sidor som miniatyrer direkt ur zip/cbz/pdf/mapp (rar/7z via
  7-Zip) utan uppackning på disk; dubbelklick öppnar på den sidan.
- Förloppslister: miniatyrer (bläddraren, T, Ctrl+T), rutdetektering för hela serien (tunn orange list + "rutor 12/40"
  i räknaren) och uppackning av rar/7z (dialog med procent).
- Redigeringsläget: Ctrl+Delete tar bort alla rutor på uppslaget, Ctrl+Z ångrar och Ctrl+Alt+Z gör om (flera steg).
- Esc lämnar helskärm/stänger paneler men avslutar inte programmet (Ctrl+Q avslutar). Går att ändra till
  "fråga först" eller "avsluta direkt"; ett Esc inom 1 s efter att helskärmen lämnats avslutar aldrig.

## Starta
- **Windows:** `dist\windows\AutoComix.exe`. `.\install.ps1` lägger till skrivbordsikon, Startmenyn och
  **Öppna i AutoComix** i högerklicksmenyn (`.\install.ps1 -Uninstall` tar bort dem).
- **Linux:** `dist/linux/AutoComix` (lokalt bygge kräver glibc 2.39; CI-bygget på Ubuntu 22.04 kör på äldre distar).
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
- `E` redigera rutor (dra utanför = ny ruta, dra i ruta = flytta, dra i kant/hörn = ändra storlek,
  Shift+dra = ny ruta även ovanpå en ruta, högerklick/Delete = ta bort, K = sidan är rätt (träningsdata),
  Ctrl+Z = ångra, Ctrl+R = automatiskt igen, `E` igen = klar)
- `X` ändra läsordningen på sidan: klicka rutorna i den ordning de ska läsas (den sista hamnar sist av sig själv,
  högerklick ångrar, Esc avbryter). Sparas per sida. `Shift+X` = automatisk ordning igen.
  Bild → "Läsordning: kolumn bredvid hög ruta först" läser t.ex. två staplade rutor bredvid en hög som 4-6-5
  i stället för rad för rad (4-5-6) i alla serier.
- `Alt+Upp`/`Alt+Ned` bildspel: längre/kortare tid per steg
- `F9` andra skärmen: av → spegling → automatisk fördelning, `Shift+F9` andra skärmens anpassning
- `F` helskärm, `I` informationsrad (annars bara räknaren nere till höger), `Ctrl+B` bokmärke, högerklick = meny

## Fjärrkontroll i mobilen (Unified Remote)
`remote\installera_unified_remote.ps1` kopierar `remote\unified\AutoComix` till Unified Remotes mapp för egna
fjärrkontroller. Ladda om servern (ikonen i aktivitetsfältet → Restart), så finns **AutoComix** under fjärrkontrollerna
i mobilen. Fliken *Läs*: nästa/föregående, sida, bildspel på/av och snabbare/långsammare. Fliken *Mer*: första/sista
sidan, filer, senaste serien, starta AutoComix, andra skärmen, zoom, helskärm. Knapparna skickar tangenter och växlar
först till AutoComix-fönstret.

## Bygga
```
uv venv -p 3.12 .venv
uv pip install -p .venv -r requirements.txt pyinstaller pillow pytest
.venv/Scripts/python -m pytest -q tests
.venv/Scripts/python -m PyInstaller AutoComix.spec        # -> dist/AutoComix(.exe)
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
3. AutoComix använder den nya modellen vid nästa start och detekterar om sidorna. Ingen ombyggnad behövs.
4. För att bygga in modellen i programmet: kopiera den till `models/`, bygg och tagga en ny version
   (`git tag v2.x.0 && git push origin v2.x.0`), så bygger GitHub nya filer under Releases.

## Tester
- `python -m pytest -q tests` – enhetstester.
- `python build_tools/anim_smoke.py` – animerade sidor: avkodning GIF/WebP/APNG, uppspelning, paus, steg, hastighet, bildspel.
- `python build_tools/ui_smoke.py` – gränssnittets storlek, avståndsläge, förstoringsglasets former.
- `python build_tools/order_smoke.py` – läsordning: ordningsläget (X), Shift+X, XY-ordning.
- `python build_tools/second_smoke.py` – andra skärmen: spegling, fördelning liggande/stående, F9.
- `python build_tools/resume_smoke.py` – Ctrl+L, historik, Esc, menyrad i helskärm, zoom per ruta, sidrutnät.
- `python build_tools/smoke.py <serie>` – kör igenom hela gränssnittet utan skärm och sparar skärmbilder i `%TEMP%/pv_smoke`.
