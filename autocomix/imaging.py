"""Image processing before display: rotation, color correction, double page, edge color.

Everything works on QImage <-> numpy (RGB) and runs in the loading thread, so the display stays fast.
"""
import numpy as np
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QTransform


def to_rgb(img):
    img = img.convertToFormat(QImage.Format.Format_RGB888)
    w, h, bpl = img.width(), img.height(), img.bytesPerLine()
    return np.frombuffer(img.constBits(), np.uint8, bpl * h).reshape(h, bpl)[:, :w * 3].reshape(h, w, 3).copy()


def from_rgb(a):
    a = np.ascontiguousarray(a)
    h, w = a.shape[:2]
    return QImage(a.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()


def auto_levels(a, clip=0.005):
    """Automatic color correction: stretch each channel between the 0.5 % and 99.5 % percentiles (white balance + contrast)."""
    out = np.empty_like(a)
    for c in range(3):
        lo, hi = np.percentile(a[:, :, c], (clip * 100, 100 - clip * 100))
        if hi - lo < 16:  # nearly single-colored channel: leave it alone
            out[:, :, c] = a[:, :, c]
            continue
        out[:, :, c] = np.clip((a[:, :, c].astype(np.float32) - lo) * (255.0 / (hi - lo)), 0, 255)
    return out


def gamma(a, g):
    if abs(g - 1.0) < 0.01:
        return a
    lut = np.clip(((np.arange(256) / 255.0) ** (1.0 / g)) * 255.0, 0, 255).astype(np.uint8)
    return lut[a]


def vibrance(a, v):
    """Saturation that affects unsaturated colors most (v 0 = off, 1 = strong)."""
    if v <= 0:
        return a
    f = a.astype(np.float32)
    mx, mn = f.max(2, keepdims=True), f.min(2, keepdims=True)
    sat = (mx - mn) / 255.0
    avg = f.mean(2, keepdims=True)
    amt = v * (1.0 - sat)
    return np.clip(avg + (f - avg) * (1.0 + amt), 0, 255).astype(np.uint8)


def process(img, rotation=0, auto=False, g=1.0, vib=0.0):
    """Rotation (degrees, multiple of 90) and color adjustments. Grayscale images skip the color step."""
    if img.isNull():
        return img
    if auto or abs(g - 1.0) >= 0.01 or vib > 0:
        a = to_rgb(img)
        if auto:
            a = auto_levels(a)
        a = gamma(a, g)
        if vib > 0 and not img.isGrayscale():
            a = vibrance(a, vib)
        img = from_rgb(a)
    if rotation % 360:
        img = img.transformed(QTransform().rotate(rotation), Qt.TransformationMode.SmoothTransformation)
    return img


def edge_color(img):
    """The average color along the image edge, for the automatic background color."""
    if img.isNull():
        return QColor(12, 12, 12)
    small = img.scaled(64, 64, Qt.AspectRatioMode.IgnoreAspectRatio).convertToFormat(QImage.Format.Format_RGB888)
    a = to_rgb(small)
    edge = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    r, g, b = np.median(edge, 0).astype(int)
    return QColor(int(r), int(g), int(b))


def spread(imgs, shadow=True, gap=0):
    """Puts pages side by side (already in display order), same height. Returns (image, rectangles per page)."""
    imgs = [i for i in imgs if i is not None and not i.isNull()]
    if len(imgs) == 1:
        return imgs[0], [QRectF(0, 0, imgs[0].width(), imgs[0].height())]
    h = max(i.height() for i in imgs)
    scaled = [i if i.height() == h else i.scaledToHeight(h, Qt.TransformationMode.SmoothTransformation) for i in imgs]
    w = sum(i.width() for i in scaled) + gap * (len(scaled) - 1)
    out = QImage(w, h, QImage.Format.Format_RGB32)
    out.fill(QColor(0, 0, 0))
    p = QPainter(out)
    x, rects = 0, []
    for i in scaled:
        p.drawImage(x, 0, i)
        rects.append(QRectF(x, 0, i.width(), h))
        x += i.width() + gap
    if shadow:  # mjuk skugga i bokryggen
        from PySide6.QtGui import QLinearGradient
        mid = rects[0].right()
        sw = max(8, w // 60)
        gr = QLinearGradient(mid - sw, 0, mid + sw, 0)
        gr.setColorAt(0, QColor(0, 0, 0, 0))
        gr.setColorAt(0.5, QColor(0, 0, 0, 110))
        gr.setColorAt(1, QColor(0, 0, 0, 0))
        p.fillRect(QRectF(mid - sw, 0, 2 * sw, h), gr)
    p.end()
    return out, rects
