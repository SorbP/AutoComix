# Funktioner: CDisplayEx → PanelView

Källa för CDisplayEx-funktionerna: programmets egna menytexter (översättningsfilerna `*.mo` i installationsmappen)
och `release_notes.txt` (1.5–1.10.33). Ingen kod är kopierad; allt är nyskrivet ovanpå PanelViews rutzoom.

| CDisplayEx | PanelView | Genväg |
|---|---|---|
| Ladda filer / Öppna mapp | Filbläddrare med mappträd, fillista och förhandsvisning (även zip/pdf/rar/7z), Öppna fil, Öppna mapp, dra och släpp | L, Ctrl+O, Ctrl+Shift+O |
| Öppna senaste, Rensa historik, historik på/av, rensa vid stängning | Arkiv → Öppna senaste, Inställningar → Historik | |
| Återuppta senaste fil (till senaste sida) | Återuppta senaste (sida + ruta), visningshistorik 20 st | Ctrl+L |
| Ladda nästa/föregående fil, automatiskt nästa fil vid slut, extra musknappar | Nästa/Föregående fil, auto-nästa (tryck igen vid slutet), musknapp bakåt/framåt | N, B |
| Nästa/föregående sida, första/sista sidan, framåt/bakåt två sidor | Pilar/mellanslag (ruta, del eller sida), PgUp/PgDn (uppslag), Home/End | |
| Japanskt läge (höger→vänster, hela gränssnittet speglat) | Japanskt läge: pilar, klickzoner, uppslag, förloppslist och miniatyrlist speglas; sparas per serie | R |
| Dubbel sida, liggande sida = uppslag, omslag, skugga, delning | Dubbelsida, liggande sidor visas ensamma, omslaget ensamt, skugga i bokryggen | Shift+D |
| Anpassa till skärm, Över/Under bredd, Över/Under höjd | Anpassa till skärm med fyra val: krymp bredare, förstora smalare, krymp högre, förstora lägre; 1–4 = vänster skärm, numpaddens 1–4 = höger skärm | 1, Num 1 |
| Anpassa liggande/stående | Anpassa till bredd / höjd (sidan visas i flera steg med överlapp) | 2, 3, Num 2, Num 3 |
| Zoom 100/125/150/200/400 %, zooma in/ut, behåll zoom | Originalstorlek och zoomnivåer i menyn, fri zoom med Ctrl+hjul, panorera genom att dra | 4, Num 4, +, −, 0 |
| Förstorare (storlek inställbar) | Förstoringsglas: växla med M eller håll mittenknappen; former rektangel, kvadrat, rund (platta) och lins (rund med förvrängning); Shift+hjul = storlek, Ctrl+hjul = förstoring | M |
| – | Gränssnittets storlek (text, listor, menyer, dialoger) 50–400 %; avståndsläge: stor sidräknare som döljs efter 1 s utan aktivitet, resten av gränssnittet 1,5× | Ctrl+Shift+Upp/Ned, Shift+F |
| Miniatyrer / reglage (Ctrl+T, Ctrl+I) | Miniatyrlist längst ner, navigerbar med pilar och Enter; sidreglage; dessutom miniatyröversikt i rutnät | Ctrl+T, Ctrl+I, T |
| Automatiskt bildspel med intervall (Ctrl+H) | Bildspel som går ruta för ruta i guidat läge, annars del/sida; tiden ändras i steg om 100 ms | Ctrl+H, S, Alt+Upp/Ned, Ctrl+Num +/− |
| Animerade GIF (enkel uppspelning) | Animerad GIF, WebP och APNG: spelas med rätt fördröjningar (0–10 ms = 100 ms som i webbläsare), startar om när sidan visas, paus, bildruta för bildruta, hastighet 0,25–4x, bildspelet väntar ett varv; rutzoom och rutdetektering fungerar på animerade sidor | P, . ,, Ctrl+Upp/Ned |
| Rotera (alla bilder) | Rotera vänster/höger, rutorna roteras med | [ ] |
| Automatisk färgkorrigering, RGB-gamma, vibrance | Automatisk färgkorrigering (vitbalans + kontrast), gamma, lyster | A |
| Bakgrundsfärg, automatisk bakgrundsfärg | Bakgrundsfärg eller automatisk (sidans kantfärg) | |
| Storleksalgoritm (Närmaste/Linjär/Lanczos) | Skalning: snabb, jämn, bästa | |
| Mjuk rullning | Animerad övergång, inställbar tid | |
| Bokmärken med namn | Lägg till/hantera/byt namn; senaste 15 i menyn | Ctrl+B, Ctrl+Shift+B |
| Spara till fil / urklipp, Skriv ut | Spara sida som, Kopiera sida, Skriv ut | Ctrl+S, Ctrl+C, Ctrl+P |
| Konfigurerbara genvägar (primära + sekundära) | Inställningar → Tangenter, två genvägar per funktion | |
| Sidcache i bakgrunden | Uppslag före/efter laddas i bakgrundstrådar | |
| Sortering (alfabetisk), undermappar | Naturlig eller alfabetisk sortering, bilder i undermappar tas med | |
| Format: JPEG, PNG, GIF, WebP, TIFF, BMP, CBZ/CBR/CB7, PDF, krypterade arkiv | Samma (PDF via pdfium, CB7 via py7zr, CBR via 7z/unrar/tar), lösenordsfråga | |
| Verktygsfält i helskärm, dölj information | Menyrad (Ctrl+M), högerklicksmeny överallt, informationsrad (I), sidnummer, förloppslist | |
| Dölj muspekaren | Muspekaren göms efter 2 s i helskärm | |
| Kontrollera uppdateringar, Leap Motion, DjVu, utforskarmenyns miniatyrer, språkval | Inte med (föråldrat/plattformsspecifikt). Gränssnittet är på svenska | |

## Utöver CDisplayEx
- Andra skärmen (F9: av/spegling/fördelning liggande–stående). Anpassningen gäller per fysisk skärm (vänster = minst x): 1–4 ovanför bokstäverna = vänster skärm, numpaddens 1–4 = höger skärm, med egna värden vid spegling. Shift+F9 växlar andra skärmens anpassning (även "samma utsnitt som huvudfönstret").
- Guidat läge: rutorna hittas automatiskt (OpenCV + YOLO-modell) och visas en i taget, centrerade med svart runt.
- Dubbelklick på en ruta zoomar dit även om detekteringen missat den.
- Redigeringsläge (E): rita/ta bort rutor, sparas per sida och blir träningsdata för en omtränad modell.
- Läsordning rad för rad (vänster→höger, uppifrån och ned), läsriktning ur ComicInfo.xml.
- Rättade rutor från `cbxy-editor` (`.cbxy` bredvid serien) används före den automatiska detekteringen.
- Körbar fil för Windows och Linux (PyInstaller, självtest i CI).
