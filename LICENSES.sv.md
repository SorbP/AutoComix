# Licenser

*[English](LICENSES.md) · Svenska*

**AutoComix** – Copyright (C) 2026 Stefan Persson. Fri programvara under
[GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0). Källkod: https://github.com/SorbP/AutoComix

AGPL-3.0 är vald för att rutmodellen är tränad med Ultralytics/YOLOv12 (AGPL-3.0); alla övriga delar är
förenliga med den. Den byggda programmappen innehåller de fullständiga licenstexterna i `licenses/`
(samlas in av `build_tools/collect_licenses.py` vid bygget) och `KÄLLKOD.txt` (engelska: `SOURCE.txt`).

## Modeller
- **models/panels_int8.onnx** – exporterad och kvantiserad från
  [mosesb/best-comic-panel-detection](https://huggingface.co/mosesb/best-comic-panel-detection). Märkt Apache-2.0,
  men tränad från en YOLOv12x-checkpoint med Ultralytics (båda AGPL-3.0); sprids därför under AGPL-3.0.
  Sedan 2.19.1 finjusterad på CoMix och sidor som utvecklaren rättat (träningsbilderna sprids inte).
- **weights/yolo26n.pt** – Ultralytics YOLO26n, AGPL-3.0. Bara utgångspunkt för omträning, byggs inte in.
- Omtränade modeller (`build_tools/train_model.py`, Ultralytics) är AGPL-3.0. Träningsbilder sprids inte.

## Inbyggda bibliotek
| Paket | Licens |
|---|---|
| Qt / PySide6 / shiboken6 | LGPL-3.0 (omodifierade, separata filer i mappbygget) |
| py7zr, pybcj, pyppmd, inflate64, multivolumefile | LGPL-2.1 eller senare |
| cbxy 0.1.2 (CV-delen i `panelview/vendor/`) | MIT (`LICENSE_cbxy`) |
| OpenCV, ONNX Runtime-beroendet flatbuffers, pypdfium2 (Apache-2.0-delen) | Apache-2.0 |
| ONNX Runtime, brotli, texttable | MIT |
| Pillow | MIT-CMU |
| NumPy, PDFium, protobuf, psutil, pycryptodomex | BSD-3 (m.fl., se respektive mapp) |
| backports.zstd / Zstandard | PSF-2.0 / BSD |
| packaging | Apache-2.0 eller BSD-2 |
| Python | PSF-2.0 |

PyInstallers startprogram är GPL-2.0 med undantag som tillåter valfri licens för det byggda programmet.
7-Zip (för rar/7z) byggs inte in; användaren installerar det själv.
