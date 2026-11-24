"""Image info: size, format and metadata (Stable Diffusion / ComfyUI parameters in PNG text chunks, EXIF UserComment)
for the current page, plus "Open in Explorer"."""
import io
import json
import subprocess
import sys
from pathlib import Path

from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QHBoxLayout, QPlainTextEdit, QPushButton, QVBoxLayout

from .i18n import tr


def open_in_explorer(path):
    """Shows the file selected in the system file manager (Windows Explorer: explorer /select,)."""
    p = Path(path)
    if sys.platform == "win32":
        # explorer wants /select,"path" as written; a list argument would be quoted as a whole
        subprocess.Popen(f'explorer /select,"{p}"' if p.is_file() else f'explorer "{p}"')
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(p)])
    else:
        subprocess.Popen(["xdg-open", str(p if p.is_dir() else p.parent)])


def _size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def _exif_comment(raw):
    """EXIF UserComment (A1111 writes the parameters there in JPG/WebP): 8 bytes charset, then the text."""
    if not isinstance(raw, bytes):
        return str(raw)
    head, body = raw[:8], raw[8:]
    if head.startswith(b"UNICODE"):
        for enc in ("utf-16-be", "utf-16-le"):
            try:
                t = body.decode(enc)
                if t.isprintable() or "\n" in t:
                    return t
            except UnicodeDecodeError:
                pass
    return body.decode("utf-8", "replace") if head[:5] in (b"ASCII", b"\x00\x00\x00\x00\x00") else raw.decode("utf-8", "replace")


def metadata(data):
    """[(key, text)] from the image bytes: PNG text chunks, EXIF (UserComment, software, camera ...), XMP."""
    from PIL import ExifTags, Image
    out = []
    try:
        im = Image.open(io.BytesIO(data))
    except Exception as e:
        return {"error": str(e)}, out
    info = {"format": im.format, "mode": im.mode, "size": im.size, "frames": getattr(im, "n_frames", 1),
            "dpi": im.info.get("dpi")}
    for k, v in im.info.items():
        if k in ("dpi", "exif", "icc_profile", "transparency", "gamma", "duration", "loop", "background",
                 "interlace", "progressive", "progression", "jfif", "jfif_version", "jfif_unit", "jfif_density"):
            continue
        if isinstance(v, bytes):
            v = v.decode("utf-8", "replace")
        if isinstance(v, str) and v[:1] in "{[":  # ComfyUI prompt/workflow: indented JSON
            try:
                v = json.dumps(json.loads(v), indent=1, ensure_ascii=False)
            except ValueError:
                pass
        out.append((str(k), str(v)))
    try:
        ex = im.getexif()
        tags = dict(ex)
        try:
            tags.update(ex.get_ifd(0x8769))  # Exif IFD: UserComment, date, exposure ...
        except Exception:
            pass
        for t, v in tags.items():
            name = ExifTags.TAGS.get(t, hex(t))
            if name in ("ExifOffset", "GPSInfo", "MakerNote") or (isinstance(v, bytes) and name != "UserComment"):
                continue
            out.append(("EXIF " + name, _exif_comment(v) if name == "UserComment" else str(v)))
    except Exception:
        pass
    return info, out


class ImageInfoDialog(QDialog):
    """All data about the page: file, size, format and metadata. Buttons: copy, show in the browser, Explorer."""

    def __init__(self, parent, viewer, show_in_folder=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Bildinfo"))
        self.resize(760, 640)
        v = viewer
        data, name = v.current_image()
        disk = v.current_file()
        info, meta = metadata(data or b"")
        lines = [f"{tr('Namn')}: {name}",
                 f"{tr('Fil')}: {disk}",
                 f"{tr('Sida')}: {v.page + 1} / {len(v.comic.pages)}"]
        if v.comic.path != Path(disk):
            lines.append(f"{tr('I')}: {v.comic.path}")
        if "error" in info:
            lines.append(f"{tr('Fel')}: {info['error']}")
        else:
            w, h = info["size"]
            lines += [f"{tr('Mått')}: {w} × {h} px", f"{tr('Format')}: {info['format']} ({info['mode']})",
                      f"{tr('Storlek')}: {_size(len(data))}"]
            if info["frames"] > 1:
                lines.append(f"{tr('Bildrutor')}: {info['frames']}")
            if info["dpi"]:
                lines.append(f"DPI: {info['dpi'][0]:.0f} × {info['dpi'][1]:.0f}")
        lines.append("")
        lines += [f"[{k}]\n{t}\n" for k, t in meta] if meta else [tr("Ingen metadata i bilden.")]
        self.text = QPlainTextEdit("\n".join(lines), readOnly=True)
        self.text.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)

        copy = QPushButton(tr("Kopiera allt"))
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.text.toPlainText()))
        row = QHBoxLayout()
        row.addWidget(copy)
        if show_in_folder:
            b = QPushButton(tr("Visa fil i mapp"))
            b.clicked.connect(lambda: (self.accept(), show_in_folder()))
            row.addWidget(b)
        ex = QPushButton(tr("Öppna i Utforskaren"))
        ex.clicked.connect(lambda: open_in_explorer(disk))
        row.addWidget(ex)
        row.addStretch()
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        row.addWidget(bb)
        lay = QVBoxLayout(self)
        lay.addWidget(self.text, 1)
        lay.addLayout(row)
