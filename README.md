# AutoComix

*English · [Svenska](README.sv.md)*

Comic reader with the features of CDisplayEx plus automatic panel-by-panel zoom. Runs on Windows and Linux.
The full feature list and how it maps to CDisplayEx is in [FEATURES.md](FEATURES.md).

- Opens image folders, `.cbz/.zip`, `.cbr/.rar`, `.cb7/.7z` and `.pdf`. Encrypted archives ask for a password.
- Panels are found in the background with OpenCV (from cbxy) and a YOLO model via ONNX Runtime (on Windows on the graphics card via DirectML, with the processor as fallback).
  The hybrid logic is in
  `autocomix/geometry.py`. The nearest pages are detected first and the result is cached
  (Windows `%LOCALAPPDATA%\AutoComix`, Linux `~/.local/share/AutoComix`).
- More than 100 unscanned pages (adjustable): asks whether to scan all now or 100 at a time; the next 100 are scanned
  when you are 10 pages from the end of the scanned ones (Settings → Many unscanned pages / Pages per batch).
- A `.cbxy` next to the comic (e.g. corrected in `cbxy-editor`) takes precedence over the cache.
- Reading direction, page and panel are saved continuously per comic. Ctrl+L opens the last comic where you were;
  File → Viewing history (Ctrl+Shift+H) shows the last 20 with position. After a hard crash `crash.log` is written in
  the data folder.
- Full screen: the menu bar appears when the mouse is moved to the top edge.
- Size: Ctrl+Shift+Up/Down (or Settings → Display) changes text, lists, menus and dialogs.
  Distance mode (Shift+F): the page counter becomes large (3× by default) and hides after 1 s without key/mouse,
  the rest of the interface becomes 1.5× larger. Everything is adjustable under Size and distance.
- Magnifier (M): View → Magnifier picks the shape – rectangle, square, round (flat) or lens (distorted).
  While the glass is on: Shift+wheel = size, Ctrl+wheel = magnification.
- Animated pages (GIF, animated WebP, APNG) play directly, even zoomed in on a panel. P = pause/play,
  `.`/`,` = frame forward/back, Ctrl+Up/Down = speed. The counter shows `▶ 3/40`. The slideshow waits until
  the animation has played once (Navigate → Animation). Max 256 MB per animation; larger ones are scaled down.
- Each panel is shown whole on one screen, as large as possible (the longest side relative to the screen decides).
- Second screen (F9 cycles, or View → Second screen): **Mirror** shows the same panel/page full screen on the other
  screen, fitted to its format. **Automatic distribution** shows landscape panels/pages on the landscape screen and
  portrait ones on the portrait screen; the other screen keeps its last image. Both are controlled from the main window
  (keys, gamepad) and the mode is kept until the next start. If both screens have the same orientation, distribution
  works like mirroring. Whole pages have their own fit on the second screen (Shift+F9): screen, width, height or the
  same view as the main window – so the main window can be on "fit to width" while the portrait screen shows the whole
  page.
- The browser (L): "Show all pages" (P) shows the archive's pages as thumbnails directly from zip/cbz/pdf/folder
  (rar/7z via 7-Zip) without extracting to disk; double-click opens at that page.
- Progress bars: thumbnails (browser, T, Ctrl+T), panel detection for the whole comic (thin orange bar + "panels 12/40"
  in the counter) and extraction of rar/7z (dialog with percent).
- Edit mode: Ctrl+Delete deletes all panels on the spread, Ctrl+Z undoes and Ctrl+Alt+Z redoes (several steps).
- Languages: English, Swedish, German, French, Spanish, Italian, Portuguese (Brazil), Polish, Russian, Japanese,
  Simplified Chinese and Korean (Settings → Display → Language; *Automatic* follows the system language, otherwise
  English). Only English and Swedish have been reviewed by the developer; the other translations may contain errors.
- Esc leaves full screen/closes panels but does not exit the program (Ctrl+Q exits). Can be changed to
  "ask first" or "exit right away"; an Esc within 1 s of leaving full screen never exits.

## Starting
- **Windows:** `dist\windows\AutoComix\AutoComix.exe` (the whole folder belongs to the program). `.\install.ps1` adds a
  desktop icon, a Start menu entry and **Open in AutoComix** to the right-click menu (`.\install.ps1 -Uninstall`
  removes them).
- **Linux:** `dist/linux/AutoComix/AutoComix` (a local build needs glibc 2.39; the CI build on Ubuntu 22.04 runs on
  older distributions).
- Started without a file, an empty window opens: drop a folder, an archive, a PDF or an image on it.
  Drop on the icon, or give a path, and the comic opens directly in full screen (`--window` for a window).

## Most important keys
`H` shows all shortcuts in the program, and Settings → Keys changes them.
- `→`/`←`, space, wheel, click on the edges: next/previous panel (or part/page)
- Double-click on a panel: zoom there, even where detection missed it. Again = whole page.
- Settings → Reading → "Turn panels that get larger turned": a tall panel on a landscape screen (or a wide one on a
  portrait screen) is turned 90° so it fills the screen. Off by default.
- `Ctrl+T` thumbnail bar, `Ctrl+I` page slider, `Ctrl+H` slideshow (panel by panel), `T` thumbnail overview
- `G` guided mode, `V` whole page first, `D` black around the panel, `R` manga mode, `Shift+D` double page
- `1`–`4` fit (screen, width, height, 100 %), `M` magnifier, `A` color correction, `[` `]` rotate
- `L` browse comics with preview, `Ctrl+L` last comic, `N`/`B` next/previous file
- `E` edit panels (drag outside = new panel, drag in a panel = move, drag an edge/corner = resize,
  Shift+drag = new panel even on top of a panel, right-click/Delete = delete, K = page is correct (training data),
  Ctrl+Z = undo, Ctrl+R = automatic again, `E` again = done)
- `X` change the reading order on the page: click the panels in the order they should be read (the last one is placed
  last automatically, right-click undoes, Esc cancels). Saved per page. `Shift+X` = automatic order again.
  Image → "Reading order: column beside a tall panel first" reads e.g. two stacked panels beside a tall one as 4-6-5
  instead of row by row (4-5-6) in all comics.
- `Alt+Up`/`Alt+Down` slideshow: longer/shorter time per step
- `F9` second screen: off → mirror → automatic distribution, `Shift+F9` second screen fit
- `F` full screen, `I` information bar (otherwise only the counter in the bottom right), `Ctrl+B` bookmark,
  right-click = menu

## Remote control on your phone (Unified Remote)
`remote\installera_unified_remote.ps1` copies `remote\unified\AutoComix` to Unified Remote's folder for custom
remotes and writes in where `AutoComix.exe` is (`-Exe <path>` if it is not in `dist\windows\AutoComix`). Restart the server (tray icon → Restart), and **AutoComix** is listed among the remotes on the phone.
The *Read* tab (*Läs* in Swedish): next/previous, page, slideshow on/off and faster/slower. The *More* tab (*Mer*): first/last page,
files, last comic, start AutoComix, second screen, zoom, full screen. The buttons send keys and switch to the
AutoComix window first. The buttons are in English unless Windows is Swedish (`-Lang sv/en` chooses).

## Building
```
uv venv -p 3.12 .venv
uv pip install -p .venv -r requirements.txt pyinstaller pillow pytest
.venv/Scripts/python -m pytest -q tests
.venv/Scripts/python -m PyInstaller AutoComix.spec        # -> dist/AutoComix/ (folder with AutoComix(.exe), _internal/, licenses/)
```
PyInstaller only builds for the platform it runs on. The GitHub workflow builds both
(Windows and Linux) and runs a self-test (`--selftest=res.json`).

Changes per version: [CHANGELOG.md](CHANGELOG.md).

The model `models/panels_int8.onnx` is exported from `mosesb/best-comic-panel-detection`, fine-tuned with
`build_tools/train_model.py` on the CoMix dataset and about 290 pages corrected by the developer, and quantized to int8.
The training pages are not distributed for copyright reasons (they are pages from published comics); the training
scripts are in `build_tools/`, so anyone can retrain on their own corrections.

## Retraining the panel model on your corrections
1. Read as usual. When a page is wrong: press `E`, draw the correct panels (drag), delete wrong ones (right-click),
   `E` again. The correction applies immediately and is saved, and the page + panels are added as a training example
   in `<data folder>/training`. `K` saves a page that is already correct as a training example.
2. When at least 30 pages are corrected: `.venv-export/Scripts/python build_tools/train_model.py`
   (needs ultralytics and PyTorch with CUDA, i.e. an NVIDIA graphics card, for a reasonable time; about 1–1.5 hours on
   an RTX 3090). The script measures the accuracy before/after on every fifth corrected page and only installs a
   better model, in `<data folder>/models/panels_int8.onnx`.
3. AutoComix uses the new model at the next start and detects the pages again. No rebuild is needed.
4. To build the model into the program: copy it to `models/`, build and tag a new version
   and run Actions → Build → Run workflow with the tag (e.g. `v2.x.0`) in the release field, and GitHub builds new
   files under Releases. Every version is tagged, but only manually started builds create releases (from 2.17.0, the
   folder build).

## Tests
- `python -m pytest -q tests` – unit tests.
- `python build_tools/anim_smoke.py` – animated pages: decoding GIF/WebP/APNG, playback, pause, step, speed, slideshow.
- `python build_tools/ui_smoke.py` – interface size, distance mode, magnifier shapes.
- `python build_tools/order_smoke.py` – reading order: order mode (X), Shift+X, XY order.
- `python build_tools/second_smoke.py` – second screen: mirror, landscape/portrait distribution, F9.
- `python build_tools/resume_smoke.py` – Ctrl+L, history, Esc, menu bar in full screen, zoom per panel, page grid.
- `python build_tools/batch_smoke.py` – scanning in batches (more than 100 pages).
- `python build_tools/turn_smoke.py` – turning panels that fill the screen better turned.
- `python build_tools/i18n_smoke.py` – the interface in every language; `python build_tools/i18n_check.py` – missing or
  broken translations.
- `python build_tools/smoke.py <comic>` – runs through the whole interface without a screen and saves screenshots in
  `%TEMP%/pv_smoke`.

Set `PYTHONIOENCODING=utf-8` if the console cannot print Swedish characters.

## Translations
The texts are written in Swedish in the code as `tr("…")` and translated in `autocomix/lang/<code>.json` (Swedish text
→ translation; `{name}` are placeholders that must be kept). New language: add the code to `LANGUAGES` in
`autocomix/i18n.py` and a JSON file, then run `build_tools/i18n_check.py`. Corrections of the translations are welcome. Code comments are in English.

## License
AutoComix is free software: Copyright (C) 2026 Stefan Persson, licensed under the
[GNU Affero General Public License v3.0](LICENSE). You may use, modify and distribute the program,
also commercially, as long as the source code is provided under the same license. Third-party licenses and
the origin of the models: [LICENSES.md](LICENSES.md).
