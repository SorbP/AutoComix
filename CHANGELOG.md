# Changes

*English · [Svenska](CHANGELOG.sv.md)*

Every version has a tag (`vX.Y.Z`) and, from 2.1.0, a release on GitHub with ready-built files.
The program was called PanelView up to 2.15.0.

## 2.19.0
- Added English language support. Settings → Display → Language is a drop-down list.
- The program is translated into the most common languages: English, Swedish, German, French, Spanish, Italian,
  Portuguese (Brazil), Polish, Russian, Japanese, Simplified Chinese and Korean.
- Only English and Swedish have been reviewed by the developer. The developer doesn't speak the other languages and
  cannot guarantee that they are correct. Corrections are welcome.
- *Automatic* (the default) follows the system language and falls back to English. Changing the language restarts the
  program on request, and the same comic opens again.
- Qt's own texts (OK/Cancel, color picker, print dialog) follow the chosen language.
- All documentation exists in English (`README.md`, `FEATURES.md`, `LICENSES.md`, `CHANGELOG.md`, `SOURCE.txt`) and in
  Swedish (`*.sv.md`, `KÄLLKOD.txt`).
- New tests: `build_tools/i18n_smoke.py` builds the interface in every language, and `build_tools/i18n_check.py` finds
  missing translations and broken placeholders.

## 2.18.1
- The source code links (About dialog, KÄLLKOD.txt, LICENSES.md, README) point to github.com/SorbP/AutoComix after the
  repository was renamed.
- The build workflow on GitHub (Actions → Build) is only started manually. The *release* field takes a tag, and that
  version is then built for Windows and Linux and published as a release.
- The build workflow handles all old versions, also from the PanelView days. Every package gets the license texts from
  main, and the file names contain the tag, e.g. `AutoComix-v2.18.1-windows-x64.zip`.
- The license script tolerates comments and duplicates in requirements.txt, which older versions need.

## 2.18.0
- When you open a comic with more than 100 unscanned pages, the program asks whether to scan all of them now or 100 at
  a time. The choice can be saved with "Remember the choice".
- In batch mode the next batch is scanned in the background when you are 10 pages from the end of the scanned pages.
  If you jump far away, a new batch starts where you are, and if you page backwards a batch backwards is added. The
  background thread waits between batches instead of exiting.
- New settings: *Many unscanned pages* (ask / scan all / in batches) and *Pages per batch*.
- Tests: tests/test_batch.py and build_tools/batch_smoke.py.

## 2.17.0
- Open source under the GNU AGPL-3.0, because the built-in panel model is trained with Ultralytics/YOLO (AGPL-3.0).
- The program is built as a folder instead of a single exe. That way the LGPL libraries (Qt/PySide6, py7zr and others)
  are separate files that can be replaced, as the LGPL requires.
- The program folder contains LICENSE, LICENSES.md, the standard licenses in licenses/, every bundled package's own
  license files and KÄLLKOD.txt. KÄLLKOD.txt says where the source code is and how the libraries are replaced.
- The About dialog shows the license, copyright, a link to the source code and the model's origin.
- `pillow` is now in requirements.txt.

## 2.16.0
- The program is now called **AutoComix**. The rename covers the exe file, window titles, the right-click menu ("Open
  in AutoComix"), shortcuts and the remote control.
- The PanelView data folder is renamed to AutoComix (or copied), so history, corrections and training data come along.
- install.ps1 removes the old PanelView entries in the registry and the old shortcuts.

## 2.15.0
- The slideshow can start over from the beginning when it reaches the end. It's under Slideshow → "Start over from the
  beginning at the end" and in Settings.

## 2.14.0
- Pages can be sorted by date modified (Ctrl+D, or in Settings). This suits folders and archives with random file
  names, and it also works in zip, rar and 7z.
- If you drop several images from the same folder, the folder opens from the start.

## 2.13.0
- The slideshow time changes in steps of 100 ms.
- The time also changes with Ctrl+Numpad +/− (besides Alt+Up/Down).

## 2.12.1
- Fixed: the second screen did not handle original size in the on-screen text.
- The second_smoke test script no longer hangs when something fails.

## 2.12.0
- The fit applies per physical screen. 1–4 above the letters control the left screen and numpad 1–4 the right screen.
  When mirroring, the screens have separate values.

## 2.11.0
- The reading order can be changed per page: press X and click the panels in the order they should be read.
  Right-click undoes and Esc cancels. The order is saved per page, and Shift+X gives the automatic order again.
- New setting Image → "Reading order: column beside a tall panel first". With it, two stacked panels beside a tall
  panel are read as 4-6-5 instead of 4-5-6.

## 2.10.0
- Remote control on the phone via Unified Remote (remote/installera_unified_remote.ps1).
  - The *Läs* tab: next/previous, page, slideshow on/off, faster/slower.
  - The *Mer* tab: first/last page, files, last comic, start the program, second screen, zoom, full screen.
- Alt+Up/Down changes the slideshow time.

## 2.9.1
- Whole pages have their own fit on the second screen (Shift+F9): screen, width, height or the same view as the main
  window. So the main window can be on "fit to width" while the portrait screen shows the whole page.

## 2.9.0
- Support for a second screen (F9), in two modes:
  - Mirroring.
  - Automatic distribution: landscape panels and pages are shown on the landscape screen and portrait ones on the
    portrait screen. The other screen keeps its last image.
- Both are controlled from the main window with keys and gamepad, and the mode is kept until the next start.

## 2.8.0
- The interface size can be set between 50 and 400 %. It applies to text, lists, menus and dialogs
  (Ctrl+Shift+Up/Down, or in Settings).
- Distance mode (Shift+F): the page counter becomes large (3×) and hides after 1 s without activity, and the rest of
  the interface becomes 1.5× larger. Everything is adjustable, and auto-hiding also works without distance mode.
- The magnifier has four shapes: rectangle, square, round and lens (soft fisheye). Shift+wheel changes the size and
  Ctrl+wheel the magnification.

## 2.7.0
- Animated pages in GIF, animated WebP and APNG.
  - The delays follow the browsers (0–10 ms counts as 100 ms), and the animation restarts when the page is shown.
  - Pause/play (P, Ctrl+Space), frame forward/back (. ,), speed 0.25–4× (Ctrl+Up/Down).
  - The slideshow can wait until the animation has played once.
  - Panel zoom and panel detection work on animated pages.
- Each animation may use at most 256 MB, and frames are only kept for the nearest spreads.

## 2.6.0
- Viewing history: page and panel are saved continuously per comic. Ctrl+L resumes the last one and Ctrl+Shift+H shows
  the last 20.
- After a hard crash, crash.log is written in the data folder.
- Esc leaves full screen and closes panels but does not exit the program. It's configurable (never / ask / directly),
  and an Esc within 1 s after full screen never exits.
- In full screen the menu bar appears at the top edge.
- The file browser has "Show all pages" (P), which shows the page grid directly from the archive without extracting.
  7z is streamed.
- Progress bars for thumbnails, panel detection and extraction.
- Edit mode got multi-step undo/redo (Ctrl+Z / Ctrl+Alt+Z) and Ctrl+Delete.
- Each panel is shown whole and as large as possible on the screen.

## 2.3.3
- More discreet display: the counter "p. 6/24 · panel 2/7" is in the bottom right, receipts are shown as a timed line
  and the information bar only shows with I or in edit mode.
- New training workflow (build_tools/):
  - comix_to_yolo.py converts the CoMix dataset.
  - eval_pages.py measures the whole chain: found panels, wrong panels and fully correct pages.
  - train_model.py trains with external data, keeps a history and only installs a model that gets better.
  - starta_modelltraning.bat starts the training.

## 2.3.2
- In edit mode you move a panel by dragging it. Shift+drag draws a new panel, even on top of an existing one.
- **K = the page is correct**: the page's panels are saved as an approved training example. Correct pages are needed in
  the training too.

## 2.3.1
- Panels can be resized and moved in edit mode.
- The mouse pointer is visible all the time.

## 2.3.0
- Edit mode for panels (E): draw correct panels and delete wrong ones.
  - The correction applies immediately, is saved per page and becomes a training example in the data folder.
  - Ctrl+Z undoes and Ctrl+R gives automatic panels again.
- File browser with folder tree, file list and preview, also of zip, pdf, rar and 7z (L).
- Page counter. B = previous file, and double page moved to Shift+D.

## 2.2.0
- Strict reading order row by row.
- Black gutters and frame lines are recognized as borders between panels.
- The panel cache is rebuilt automatically when the detection has changed.
- The macOS build is removed; the program is built for Windows and Linux.
- Synthetic test pages (build_tools/synthetic_pages.py).

## 2.1.0
- First release. Version 2.0 was the comic reader with the features of CDisplayEx and panel detection with OpenCV plus
  a YOLO model (ONNX, int8).
- Reading order with XY-cut.
- More panels are found: the model splits blocks that OpenCV merged.
- The thumbnail bar stays when stepping through panels.
- The slideshow time is given in ms.
- Right-click menu.
- The reading direction is read from ComicInfo.xml.
