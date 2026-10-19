"""Panel detection in a background thread: CV + ML per page, nearest the current page first."""
import threading
from dataclasses import asdict

import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal

cv2.setNumThreads(1)  # OpenCV's own thread pool deadlocks in a background thread together with Qt (seen in morphologyEx)


def detect_bytes(data, ml_ok=True):
    """(cv_panels, ml_panels, ml_worked) for a page's image bytes."""
    from .vendor.cbxy_cv import detect_panels
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)  # imdecode handles å/α in paths
    if img is None:  # GIF etc. that OpenCV cannot read: first frame via Qt
        from PySide6.QtGui import QImage
        from .imaging import to_rgb
        q = QImage.fromData(data)
        if q.isNull():
            return [], [], ml_ok
        img = cv2.cvtColor(to_rgb(q), cv2.COLOR_RGB2BGR)
    cv = _cv_best(img, detect_panels)
    ml = []
    if ml_ok:
        try:
            from . import ml_onnx
            ml = ml_onnx.detect(img, conf=0.2, min_area_frac=0.02)
        except Exception:  # model/onnxruntime missing => run CV only
            ml_ok = False
    return cv, ml + _leftovers(img, cv, ml), ml_ok


def _cv_best(img, detect_panels):
    """CV with white gutters, and once more where black lines count as gutters (comics with black
    frame lines/gutters, e.g. American ones). The clean result with the most panels wins."""
    from . import geometry as G
    runs = [[asdict(p) for p in detect_panels(img, min_area_frac=0.03, gutter_threshold=230)]]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    dark = gray < 45
    if dark.mean() > 0.01:
        k = max(9, img.shape[1] // 90) | 1  # wide gutters: CV otherwise closes gaps under ~10 px
        lines = cv2.morphologyEx(dark.astype(np.uint8), cv2.MORPH_OPEN, np.ones((1, img.shape[1] // 12), np.uint8))
        lines |= cv2.morphologyEx(dark.astype(np.uint8), cv2.MORPH_OPEN, np.ones((img.shape[0] // 12, 1), np.uint8))
        lines = cv2.dilate(lines, np.ones((k, k), np.uint8))  # only long straight dark lines, not dark areas in the picture
        alt = img.copy()
        alt[lines > 0] = 255
        runs.append([asdict(p) for p in detect_panels(alt, min_area_frac=0.03, gutter_threshold=230)])
    good = [r for r in runs if G.cv_good(r)]
    return max(good, key=len) if good else runs[0]


def _leftovers(img, cv, ml):
    """CV blocks that ML splits into several panels: what is left of the block (content outside the ML panels)
    becomes panels of its own, so panels ML missed (e.g. two small panels beside a large one) do not disappear."""
    from . import geometry as G
    H, W = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    out = []
    for c in cv:
        inner = [m for m in ml if G.inter(m, c) / G.area(m) >= G.CONTAIN]
        if len(inner) < 2:
            continue
        x0, y0 = int(c["x"] * W), int(c["y"] * H)
        x1, y1 = int((c["x"] + c["w"]) * W), int((c["y"] + c["h"]) * H)
        ink = (gray[y0:y1, x0:x1] < 230).astype(np.uint8)
        pad = max(6, W // 120)
        for m in inner:  # the ML panels (with a margin, so their frame lines are not left behind) are subtracted
            mx0, my0 = int(m["x"] * W) - x0 - pad, int(m["y"] * H) - y0 - pad
            mx1, my1 = int((m["x"] + m["w"]) * W) - x0 + pad, int((m["y"] + m["h"]) * H) - y0 + pad
            ink[max(my0, 0):max(my1, 0), max(mx0, 0):max(mx1, 0)] = 0
        k = max(3, W // 150) | 1
        ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((k, k), np.uint8))  # remove thin line remnants
        ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, np.ones((3 * k, 3 * k), np.uint8))
        n, lab, st, _ = cv2.connectedComponentsWithStats(ink, 8)
        for j in range(1, n):
            x, y, w, h, a = st[j]
            q = {"x": (x0 + x) / W, "y": (y0 + y) / H, "w": w / W, "h": h / H}
            if G.area(q) >= G.MIN_AREA and a / (w * h) >= 0.5 and all(G.inter(q, m) / G.area(q) < 0.3 for m in ml + out):
                out.append(q)
    return out


class Detector(QThread):
    pageDone = Signal(int)
    progress = Signal(int, int)  # klara, totalt

    def __init__(self, comic, cache):
        super().__init__()
        self.comic, self.cache = comic, cache
        self.focus = 0
        self._stop = threading.Event()
        self._wake = threading.Event()
        self.ml_ok = True
        self.batch = 0  # >0: only scan pages lo..hi-1, the next batch when the reader is 10 pages from the edge
        self.lo = self.hi = 0

    def set_batch(self, n):
        self.batch = int(n)
        self.lo, self.hi = max(0, self.focus - 10), self.focus + self.batch

    def set_focus(self, i):
        self.focus = i
        if self.batch:
            if i < self.lo or i >= self.hi:  # jump outside the window: new batch from that page
                self.lo, self.hi = max(0, i - 10), i + self.batch
            else:
                if i >= self.hi - 10:
                    self.hi += self.batch
                if self.lo and i < self.lo + 10:
                    self.lo = max(0, self.lo - self.batch)
        self._wake.set()

    def stop(self):
        self._stop.set()
        self._wake.set()
        self.wait(5000)

    def _todo(self):
        """(pages to scan now in priority order, number of unscanned pages in total)."""
        n = len(self.comic.pages)
        left = [i for i in range(n) if self.cache.get(self.comic.pages[i]) is None]
        todo = [i for i in left if self.lo <= i < self.hi] if self.batch else left
        # Nearest ahead of the current page first, pages behind get lower priority.
        return sorted(todo, key=lambda i: (i - self.focus) if i >= self.focus else n + self.focus - i), len(left)

    def run(self):
        n = len(self.comic.pages)
        while not self._stop.is_set():
            self._wake.clear()
            todo, left = self._todo()
            self.progress.emit(n - left, n)
            if not todo:
                if not left:
                    break
                self.cache.save()  # batch done: wait until the reader approaches the next one
                self._wake.wait()
                continue
            i = todo[0]
            try:
                cv, ml, self.ml_ok = detect_bytes(self.comic.read(i), self.ml_ok)
            except Exception:
                cv, ml = [], []
            self.cache.put(self.comic.pages[i], cv, ml)
            self.pageDone.emit(i)
        self.cache.save()
