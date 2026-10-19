# Licenses

*English · [Svenska](LICENSES.sv.md)*

**AutoComix** – Copyright (C) 2026 Stefan Persson. Free software under the
[GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0). Source code: https://github.com/SorbP/AutoComix

The AGPL-3.0 was chosen because the panel model is trained with Ultralytics/YOLOv12 (AGPL-3.0); all other parts are
compatible with it. The built program folder contains the full license texts in `licenses/`
(collected by `build_tools/collect_licenses.py` during the build) and `SOURCE.txt` (Swedish: `KÄLLKOD.txt`).

## Models
- **models/panels_int8.onnx** – exported and quantized from
  [mosesb/best-comic-panel-detection](https://huggingface.co/mosesb/best-comic-panel-detection). Labelled Apache-2.0,
  but trained from a YOLOv12x checkpoint with Ultralytics (both AGPL-3.0); therefore distributed under the AGPL-3.0.
  Since 2.19.1 fine-tuned on CoMix and pages corrected by the developer (the training images are not distributed).
- **weights/yolo26n.pt** – Ultralytics YOLO26n, AGPL-3.0. Only a starting point for retraining, not built in.
- Retrained models (`build_tools/train_model.py`, Ultralytics) are AGPL-3.0. Training images are not distributed.

## Bundled libraries
| Package | License |
|---|---|
| Qt / PySide6 / shiboken6 | LGPL-3.0 (unmodified, separate files in the folder build) |
| py7zr, pybcj, pyppmd, inflate64, multivolumefile | LGPL-2.1 or later |
| cbxy 0.1.2 (the CV part in `autocomix/vendor/`) | MIT (`LICENSE_cbxy`) |
| OpenCV, the ONNX Runtime dependency flatbuffers, pypdfium2 (the Apache-2.0 part) | Apache-2.0 |
| ONNX Runtime, brotli, texttable | MIT |
| Pillow | MIT-CMU |
| NumPy, PDFium, protobuf, psutil, pycryptodomex | BSD-3 (and others, see each folder) |
| backports.zstd / Zstandard | PSF-2.0 / BSD |
| packaging | Apache-2.0 or BSD-2 |
| Python | PSF-2.0 |

PyInstaller's bootloader is GPL-2.0 with an exception that allows any license for the built program.
7-Zip (for rar/7z) is not built in; users install it themselves.
