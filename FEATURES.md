# Features: CDisplayEx → AutoComix

*English · [Svenska](FEATURES.sv.md)*

Source for the CDisplayEx features: the program's own menu texts (the translation files `*.mo` in the installation
folder) and `release_notes.txt` (1.5–1.10.33). No code is copied; everything is written from scratch on top of
AutoComix's panel zoom.

| CDisplayEx | AutoComix | Shortcut |
|---|---|---|
| Load files / Open folder | File browser with folder tree, file list and preview (also zip/pdf/rar/7z), Open file, Open folder, drag and drop | L, Ctrl+O, Ctrl+Shift+O |
| Open recent, Clear history, history on/off, clear on close | File → Open recent, Settings → History | |
| Resume last file (at the last page) | Resume last (page + panel), viewing history of 20 | Ctrl+L |
| Load next/previous file, automatically next file at the end, extra mouse buttons | Next/Previous file, auto-next (press again at the end), mouse back/forward buttons | N, B |
| Next/previous page, first/last page, forward/back two pages | Arrows/space (panel, part or page), PgUp/PgDn (spread), Home/End | |
| Japanese mode (right→left, whole interface mirrored) | Manga mode: arrows, click zones, spreads, progress bar and thumbnail bar are mirrored; saved per comic | R |
| Double page, landscape page = spread, cover, shadow, splitting | Double page, landscape pages are shown alone, the cover alone, shadow in the spine | Shift+D |
| Fit to screen, Over/Under width, Over/Under height | Fit to screen with four options: shrink wider, enlarge narrower, shrink taller, enlarge shorter; 1–4 = left screen, numpad 1–4 = right screen | 1, Num 1 |
| Fit landscape/portrait | Fit to width / height (the page is shown in several steps with overlap) | 2, 3, Num 2, Num 3 |
| Zoom 100/125/150/200/400 %, zoom in/out, keep zoom | Original size and zoom levels in the menu, free zoom with Ctrl+wheel, pan by dragging | 4, Num 4, +, −, 0 |
| Magnifier (adjustable size) | Magnifier: toggle with M or hold the middle button; shapes rectangle, square, round (flat) and lens (round with distortion); Shift+wheel = size, Ctrl+wheel = magnification | M |
| – | Interface size (text, lists, menus, dialogs) 50–400 %; distance mode: large page counter that hides after 1 s without activity, the rest of the interface 1.5× | Ctrl+Shift+Up/Down, Shift+F |
| Thumbnails / slider (Ctrl+T, Ctrl+I) | Thumbnail bar at the bottom, navigable with arrows and Enter; page slider; plus a thumbnail overview in a grid | Ctrl+T, Ctrl+I, T |
| Automatic slideshow with interval (Ctrl+H) | Slideshow that goes panel by panel in guided mode, otherwise part/page; the time changes in steps of 100 ms | Ctrl+H, S, Alt+Up/Down, Ctrl+Num +/− |
| Animated GIF (simple playback) | Animated GIF, WebP and APNG: played with the right delays (0–10 ms = 100 ms as in browsers), restart when the page is shown, pause, frame by frame, speed 0.25–4x, the slideshow waits one loop; panel zoom and panel detection work on animated pages | P, . ,, Ctrl+Up/Down |
| Rotate (all images) | Rotate left/right, the panels rotate along | [ ] |
| Automatic color correction, RGB gamma, vibrance | Automatic color correction (white balance + contrast), gamma, vibrance | A |
| Background color, automatic background color | Background color or automatic (the page's edge color) | |
| Resize algorithm (Nearest/Linear/Lanczos) | Scaling: fast, smooth, best | |
| Smooth scrolling | Animated transition, adjustable time | |
| Named bookmarks | Add/manage/rename; the last 15 in the menu | Ctrl+B, Ctrl+Shift+B |
| Save to file / clipboard, Print | Save page as, Copy page, Print | Ctrl+S, Ctrl+C, Ctrl+P |
| Configurable shortcuts (primary + secondary) | Settings → Keys, two shortcuts per function | |
| Page cache in the background | Spreads before/after are loaded in background threads | |
| Sorting (alphabetical), subfolders | Natural, alphabetical or by date modified (random file names; also zip/rar/7z), images in subfolders are included; several images dropped from the same folder open the folder from the start | Ctrl+D |
| Formats: JPEG, PNG, GIF, WebP, TIFF, BMP, CBZ/CBR/CB7, PDF, encrypted archives | The same (PDF via pdfium, CB7 via py7zr, CBR via 7z/unrar/tar), password prompt | |
| Toolbar in full screen, hide information | Menu bar (Ctrl+M), right-click menu everywhere, information bar (I), page number, progress bar | |
| Hide the mouse pointer | The mouse pointer is hidden after 2 s in full screen | |
| Language selection | Twelve languages (Settings → Display → Language), automatically from the system language | |
| Check for updates, Leap Motion, DjVu, Explorer thumbnails | Not included (outdated/platform specific) | |

## Beyond CDisplayEx
- Second screen (F9: off/mirror/landscape–portrait distribution). The fit applies per physical screen (left = smallest x): 1–4 above the letters = left screen, numpad 1–4 = right screen, with separate values when mirroring. Shift+F9 switches the second screen's fit (also "same view as the main window").
- Guided mode: the panels are found automatically (OpenCV + YOLO model) and shown one at a time, centered with black around them.
- Double-clicking a panel zooms there even if detection missed it.
- Automatic turning (optional): panels that fill the screen better turned 90° are turned.
- Panel detection on the graphics card (DirectML, Windows) with the processor as fallback.
- Edit mode (E): draw/delete panels, saved per page and used as training data for a retrained model. K = the page is correct (also saved as training data).
- Reading order row by row (left→right, top to bottom), reading direction from ComicInfo.xml; changeable per page (X).
- Scanning in batches for large comics (more than 100 unscanned pages).
- Corrected panels from `cbxy-editor` (`.cbxy` next to the comic) take precedence over automatic detection.
- Remote control on the phone via Unified Remote.
- Executable for Windows and Linux (PyInstaller, self-test in CI).
