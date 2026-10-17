"""Animerade sidor (GIF, animerad WebP, APNG): avkodning till färdiga bildrutor + fördröjningar.

Qt avkodar GIF och WebP (rutorna kommer färdigkomponerade, med disposal/transparens hanterat).
APNG stöds inte av Qt (bara första rutan), där används Pillow om det finns.
Alla rutor hålls i minnet; över MAX_BYTES skalas rutorna ner så att animationen ändå får plats.
"""
import io
import math

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize
from PySide6.QtGui import QImage, QImageReader

MAX_BYTES = 256 * 1024 * 1024  # per animation (RGB32 = 4 byte/pixel)
MAX_FRAMES = 2000


def norm_delay(ms):
    """Samma tolkning som webbläsarna: 0–10 ms betyder 'ospecificerat' och spelas som 100 ms."""
    ms = int(ms or 0)
    return 100 if ms <= 10 else ms


def kind(data):
    """'gif' / 'webp' / 'apng' om bytesen KAN vara animerade (billig koll av filhuvudet), annars None."""
    if not data or len(data) < 16:
        return None
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp" if b"ANIM" in data[12:4096] else None
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        i = data.find(b"IDAT", 8, 1 << 20)
        return "apng" if b"acTL" in data[8:i if i > 0 else 1 << 16] else None
    return None


def decode(data):
    """(bildrutor, fördröjningar i ms) för en animerad bild, eller None om den inte är animerad."""
    k = kind(data)
    if k is None:
        return None
    out = _decode_pillow(data) if k == "apng" else _decode_qt(data)
    if out is None or len(out[0]) < 2:
        return None
    return out


def _decode_qt(data):
    buf = QBuffer()
    buf.setData(QByteArray(data))
    buf.open(QIODevice.OpenModeFlag.ReadOnly)
    r = QImageReader(buf)
    if not r.supportsAnimation():
        return None
    n = r.imageCount()
    size = r.size()
    if n > 1 and size.isValid():  # antal kända: skala ner redan vid avkodningen om det inte ryms
        f = _fit(size.width(), size.height(), n)
        if f < 1:
            r.setScaledSize(QSize(max(1, int(size.width() * f)), max(1, int(size.height() * f))))
    frames, delays = [], []
    while len(frames) < MAX_FRAMES:
        img = r.read()
        if img.isNull():
            break
        frames.append(img.convertToFormat(QImage.Format.Format_RGB32))
        delays.append(norm_delay(r.nextImageDelay()))
        if not r.canRead():
            break
    return _shrink(frames), delays


def _decode_pillow(data):
    try:
        from PIL import Image, ImageSequence
    except ImportError:
        return None
    try:
        im = Image.open(io.BytesIO(data))
        if not getattr(im, "is_animated", False):
            return None
        f = _fit(im.width, im.height, getattr(im, "n_frames", 1))
        frames, delays = [], []
        for fr in ImageSequence.Iterator(im):
            if len(frames) >= MAX_FRAMES:
                break
            rgba = fr.convert("RGBA")
            if f < 1:
                rgba = rgba.resize((max(1, int(im.width * f)), max(1, int(im.height * f))), Image.LANCZOS)
            q = QImage(rgba.tobytes(), rgba.width, rgba.height, 4 * rgba.width, QImage.Format.Format_RGBA8888)
            frames.append(q.convertToFormat(QImage.Format.Format_RGB32))  # convert kopierar ut ur Pillow-bufferten
            delays.append(norm_delay(fr.info.get("duration", im.info.get("duration", 0))))
        return frames, delays
    except Exception:
        return None


def _fit(w, h, n):
    """Skalfaktor (<= 1) så att n rutor à w x h ryms i MAX_BYTES."""
    need = w * h * 4 * max(1, n)
    return 1.0 if need <= MAX_BYTES else math.sqrt(MAX_BYTES / need)


def _shrink(frames):
    """Antal okänt i förväg och det blev för stort: skala ner i efterhand."""
    if not frames:
        return frames
    f = _fit(frames[0].width(), frames[0].height(), len(frames))
    if f >= 1:
        return frames
    from PySide6.QtCore import Qt
    w, h = max(1, int(frames[0].width() * f)), max(1, int(frames[0].height() * f))
    return [fr.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
            for fr in frames]


def first_frame(data):
    """Första rutan som QImage (för t.ex. rutdetektering när OpenCV inte kan läsa formatet)."""
    return QImage.fromData(data)
