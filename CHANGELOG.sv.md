# Ändringar

*[English](CHANGELOG.md) · Svenska*

Varje version har en tagg (`vX.Y.Z`) och, från 2.1.0, en release på GitHub med färdigbyggda filer.
Programmet hette PanelView fram till 2.15.0.

## 2.19.2
- Befintliga installationer behåller svenska. Före 2.19 fanns programmet bara på svenska, så *Automatiskt* hade bytt
  till engelska för alla med engelskt Windows. Nya installationer följer fortfarande systemets språk.
- Python-paketets mapp heter nu `autocomix` i stället för `panelview` (miljövariabeln för att testa en modell heter
  nu `AUTOCOMIX_MODEL`).
- Alla kommentarer och docstrings i koden är på engelska, så att fler kan läsa koden.
- Fjärrkontrollen för Unified Remote har engelska knappar om Windows inte är svenskt (`-Lang sv/en` väljer själv).
- Repots beskrivning på GitHub är på engelska och svenska.

## 2.19.1
- Ny inbyggd rutmodell, finjusterad på CoMix-datasetet och 287 sidor som utvecklaren rättat eller godkänt.
  Mätt på rättade sidor som modellerna inte tränats på (59 sidor), jämfört med modellen i 2.19.0:
  - hittade rutor 88 % → 98 %
  - felaktiga rutor 8 % → 6 %
  - helt rätta sidor 49 % → 73 %
- På CoMix-testsidorna (165) blir nu 86 % av sidorna helt rätt. Originalmodellen klarade 24 %.
- Alla seriers rutor detekteras om vid första starten, eftersom modellen har ändrats.
- Träningssidorna sprids inte av upphovsrättsskäl. Träningsskripten finns i `build_tools/`.
- Installationsskriptet för Unified Remote skriver in var `AutoComix.exe` ligger (`-Exe <sökväg>` för en annan plats).
  Förut fungerade knappen "Starta AutoComix" bara på utvecklarens dator.

## 2.19.0
- Stöd för engelska. Inställningar → Visning → Språk är en rullgardinslista.
- Programmet är översatt till de vanligaste språken: engelska, svenska, tyska, franska, spanska, italienska,
  portugisiska (Brasilien), polska, ryska, japanska, förenklad kinesiska och koreanska.
- Bara engelska och svenska är granskade av utvecklaren. Utvecklaren talar inte de övriga språken och kan inte
  garantera att allt stämmer. Rättelser tas gärna emot.
- *Automatiskt* (standard) följer systemets språk och faller tillbaka på engelska. Byter du språk startar programmet om
  på begäran, och samma serie öppnas igen.
- Qt:s egna texter (OK/Avbryt, färgväljaren, utskriftsdialogen) följer det valda språket.
- All dokumentation finns på engelska (`README.md`, `FEATURES.md`, `LICENSES.md`, `CHANGELOG.md`, `SOURCE.txt`) och
  på svenska (`*.sv.md`, `KÄLLKOD.txt`).
- Nya tester: `build_tools/i18n_smoke.py` bygger gränssnittet på alla språk, och `build_tools/i18n_check.py` hittar
  saknade översättningar och trasiga platshållare.

## 2.18.1
- Källkodslänkarna (Om-dialogen, KÄLLKOD.txt, LICENSES.md, README) pekar på github.com/SorbP/AutoComix efter att repot döpts om.
- Byggflödet på GitHub (Actions → Build) startas bara manuellt. Fältet *release* tar en tagg, och då byggs just den versionen för Windows och Linux och läggs upp som release.
- Byggflödet klarar alla gamla versioner, även från PanelView-tiden. Varje paket får licenstexterna från main, och filnamnen innehåller taggen, t.ex. `AutoComix-v2.18.1-windows-x64.zip`.
- Licensskriptet tål kommentarer och dubbletter i requirements.txt, vilket äldre versioner behöver.

## 2.18.0
- Öppnar du en serie med fler än 100 oskannade sidor frågar programmet om alla ska skannas nu eller 100 i taget. Valet kan sparas med "Kom ihåg valet".
- I satsläget skannas nästa sats i bakgrunden när du är 10 sidor från slutet av det skannade. Hoppar du långt bort startar en ny sats där du är, och bläddrar du bakåt läggs en sats bakåt till. Bakgrundstråden väntar mellan satserna i stället för att avslutas.
- Nya inställningar: *Många oskannade sidor* (fråga / skanna alla / i satser) och *Sidor per sats*.
- Tester: tests/test_batch.py och build_tools/batch_smoke.py.

## 2.17.0
- Öppen källkod under GNU AGPL-3.0, eftersom den inbyggda rutmodellen är tränad med Ultralytics/YOLO (AGPL-3.0).
- Programmet byggs som en mapp i stället för en enda exe, så att LGPL-biblioteken (Qt/PySide6, py7zr m.fl.) ligger som separata filer som går att byta ut, som LGPL kräver.
- Programmappen innehåller LICENSE, LICENSES.md, standardlicenserna i licenses/, varje inbyggt pakets egna licensfiler och KÄLLKOD.txt. KÄLLKOD.txt säger var källkoden finns och hur biblioteken byts ut.
- Om-dialogen visar licens, upphovsrätt, länk till källkoden och modellens ursprung.
- `pillow` ligger nu i requirements.txt.

## 2.16.0
- Programmet heter nu **AutoComix**. Namnbytet gäller exe-filen, fönstertitlar, högerklicksmenyn ("Öppna i AutoComix"), genvägar och fjärrkontrollen.
- Datamappen PanelView döps om till AutoComix (eller kopieras), så historik, rättelser och träningsdata följer med.
- install.ps1 tar bort de gamla PanelView-posterna i registret och de gamla genvägarna.

## 2.15.0
- Bildspelet kan börja om från början när det når slutet. Det finns som Bildspel → "Börja om från början vid slutet" och under Inställningar.

## 2.14.0
- Sidorna kan sorteras efter ändringsdatum (Ctrl+D, eller under Inställningar). Det passar mappar och arkiv med slumpmässiga filnamn och fungerar även i zip, rar och 7z.
- Släpper du flera bilder ur samma mapp öppnas mappen från början.

## 2.13.0
- Bildspelets tid ändras i steg om 100 ms.
- Tiden ändras med Ctrl+Numpad +/− (förutom Alt+Upp/Ned).

## 2.12.1
- Rättat: andra skärmen klarade inte originalstorlek i visningstexten.
- Testskriptet second_smoke hänger inte längre när något går fel.

## 2.12.0
- Anpassningen gäller per fysisk skärm. 1–4 ovanför bokstäverna styr vänster skärm och numpaddens 1–4 höger skärm. Vid spegling har skärmarna egna värden.

## 2.11.0
- Läsordningen kan ändras per sida: tryck X och klicka rutorna i den ordning de ska läsas. Högerklick ångrar och Esc avbryter. Ordningen sparas per sida, och Shift+X ger automatisk ordning igen.
- Ny inställning Bild → "Läsordning: kolumn bredvid hög ruta först". Med den läses två staplade rutor bredvid en hög ruta som 4-6-5 i stället för 4-5-6.

## 2.10.0
- Fjärrkontroll i mobilen via Unified Remote (remote/installera_unified_remote.ps1).
  - Fliken *Läs*: nästa/föregående, sida, bildspel på/av, snabbare/långsammare.
  - Fliken *Mer*: första/sista sidan, filer, senaste serien, starta programmet, andra skärmen, zoom, helskärm.
- Alt+Upp/Ned ändrar bildspelets tid.

## 2.9.1
- Hela sidor har en egen anpassning på andra skärmen (Shift+F9): skärm, bredd, höjd eller samma utsnitt som huvudfönstret. Huvudfönstret kan alltså stå på "anpassa till bredd" medan den stående skärmen visar hela sidan.

## 2.9.0
- Stöd för en andra skärm (F9), i två lägen:
  - Spegling.
  - Automatisk fördelning: liggande rutor och sidor visas på den liggande skärmen och stående på den stående. Den andra skärmen behåller sin senaste bild.
- Båda styrs från huvudfönstret med tangenter och handkontroll, och läget sparas till nästa start.

## 2.8.0
- Gränssnittets storlek kan ställas in mellan 50 och 400 %. Det gäller text, listor, menyer och dialoger (Ctrl+Shift+Upp/Ned, eller under Inställningar).
- Avståndsläge (Shift+F): sidräknaren blir stor (3×) och döljs efter 1 s utan aktivitet, och resten av gränssnittet blir 1,5× större. Allt går att ställa in, och automatisk döljning fungerar även utan avståndsläget.
- Förstoringsglaset har fyra former: rektangel, kvadrat, rund och lins (mjuk fisheye). Shift+hjul ändrar storleken och Ctrl+hjul förstoringen.

## 2.7.0
- Animerade sidor i GIF, animerad WebP och APNG.
  - Fördröjningarna följer webbläsarna (0–10 ms räknas som 100 ms), och animationen startar om när sidan visas.
  - Paus/spela (P, Ctrl+Space), bildruta fram/bak (. ,), hastighet 0,25–4× (Ctrl+Upp/Ned).
  - Bildspelet kan vänta tills animationen gått ett varv.
  - Rutzoom och rutdetektering fungerar på animerade sidor.
- Varje animation får använda högst 256 MB, och bildrutor hålls bara för de närmaste uppslagen.

## 2.6.0
- Visningshistorik: sida och ruta sparas löpande per serie. Ctrl+L återupptar den senaste och Ctrl+Shift+H visar de 20 senaste.
- Vid en hård krasch skrivs crash.log i datamappen.
- Esc lämnar helskärm och stänger paneler men avslutar inte programmet. Det är valbart (aldrig / fråga / direkt), och ett Esc inom 1 s efter helskärm avslutar aldrig.
- I helskärm visas menyraden vid överkanten.
- Filbläddraren har "Visa alla sidor" (P), som visar sidrutnätet direkt ur arkivet utan uppackning. 7z strömmas.
- Förloppslister för miniatyrer, rutdetektering och uppackning.
- Redigeringsläget fick ångra/gör om i flera steg (Ctrl+Z / Ctrl+Alt+Z) och Ctrl+Delete.
- Varje ruta visas hel och så stor som möjligt på skärmen.

## 2.3.3
- Diskretare visning: räknaren "s. 6/24 · ruta 2/7" står nere till höger, kvitton visas som en tidsbegränsad rad och informationsraden syns bara med I eller i redigeringsläget.
- Nytt träningsflöde (build_tools/):
  - comix_to_yolo.py konverterar CoMix-datasetet.
  - eval_pages.py mäter hela kedjan: hittade rutor, felaktiga rutor och helt rätt sidor.
  - train_model.py tränar med extern data, sparar historik och installerar bara en modell som blir bättre.
  - starta_modelltraning.bat startar träningen.

## 2.3.2
- I redigeringsläget flyttar du en ruta genom att dra i den. Shift+dra ritar en ny ruta, även ovanpå en befintlig.
- **K = sidan är rätt**: sidans rutor sparas som godkänt träningsexempel. Även korrekta sidor behövs i träningen.

## 2.3.1
- Rutor kan ändras i storlek och flyttas i redigeringsläget.
- Muspekaren syns hela tiden.

## 2.3.0
- Redigeringsläge för rutor (E): rita rätt rutor och ta bort fel.
  - Rättelsen gäller direkt, sparas per sida och blir ett träningsexempel i datamappen.
  - Ctrl+Z ångrar och Ctrl+R ger automatiska rutor igen.
- Filbläddrare med mappträd, fillista och förhandsvisning, även av zip, pdf, rar och 7z (L).
- Sidräknare. B = föregående fil, och dubbelsida flyttade till Shift+D.

## 2.2.0
- Strikt läsordning rad för rad.
- Svarta mellanrum och ramlinjer känns igen som gränser mellan rutor.
- Rutcachen görs om automatiskt när detekteringen har ändrats.
- macOS-bygget är borttaget; programmet byggs för Windows och Linux.
- Syntetiska testsidor (build_tools/synthetic_pages.py).

## 2.1.0
- Första releasen. Version 2.0 var serieläsaren med CDisplayEx:s funktioner och rutdetektering med OpenCV plus en YOLO-modell (ONNX, int8).
- Läsordning med XY-cut.
- Fler rutor hittas: modellen delar block som OpenCV slagit ihop.
- Miniatyrlisten ligger kvar vid rutstegning.
- Bildspelets tid anges i ms.
- Högerklicksmeny.
- Läsriktningen läses ur ComicInfo.xml.
