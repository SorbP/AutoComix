"""Rutdetektering i bakgrundstråd: CV + ML per sida, närmast aktuell sida först."""
import threading
from dataclasses import asdict

import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal

cv2.setNumThreads(1)  # OpenCV:s egen trådpool låser sig i bakgrundstråd tillsammans med Qt (sågs i morphologyEx)


def detect_bytes(data, ml_ok=True):
    """(cv_rutor, ml_rutor, ml_fungerade) för en sidas bildbytes."""
    from .vendor.cbxy_cv import detect_panels
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)  # imdecode klarar å/α i sökvägar
    if img is None:
        return [], [], ml_ok
    cv = [asdict(p) for p in detect_panels(img, min_area_frac=0.03, gutter_threshold=230)]
    ml = []
    if ml_ok:
        try:
            from . import ml_onnx
            ml = ml_onnx.detect(img, conf=0.2, min_area_frac=0.02)
        except Exception:  # modell/onnxruntime saknas => kör bara CV
            ml_ok = False
    return cv, ml + _leftovers(img, cv, ml), ml_ok


def _leftovers(img, cv, ml):
    """CV-block som ML delar i flera rutor: det som blir kvar av blocket (innehåll utanför ML-rutorna)
    blir egna rutor, så att rutor som ML missat (t.ex. två små rutor bredvid en stor) inte försvinner."""
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
        for m in inner:  # ML-rutorna (med marginal, så att deras ramlinjer inte blir kvar) räknas bort
            mx0, my0 = int(m["x"] * W) - x0 - pad, int(m["y"] * H) - y0 - pad
            mx1, my1 = int((m["x"] + m["w"]) * W) - x0 + pad, int((m["y"] + m["h"]) * H) - y0 + pad
            ink[max(my0, 0):max(my1, 0), max(mx0, 0):max(mx1, 0)] = 0
        k = max(3, W // 150) | 1
        ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((k, k), np.uint8))  # bort med tunna linjerester
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

    def set_focus(self, i):
        self.focus = i
        self._wake.set()

    def stop(self):
        self._stop.set()
        self._wake.set()
        self.wait(5000)

    def _todo(self):
        n = len(self.comic.pages)
        todo = [i for i in range(n) if self.cache.get(self.comic.pages[i]) is None]
        # Närmast framför aktuell sida först, sidor bakåt får lägre prioritet.
        return sorted(todo, key=lambda i: (i - self.focus) if i >= self.focus else n + self.focus - i)

    def run(self):
        n = len(self.comic.pages)
        while not self._stop.is_set():
            todo = self._todo()
            self.progress.emit(n - len(todo), n)
            if not todo:
                break
            i = todo[0]
            try:
                cv, ml, self.ml_ok = detect_bytes(self.comic.read(i), self.ml_ok)
            except Exception:
                cv, ml = [], []
            self.cache.put(self.comic.pages[i], cv, ml)
            self.pageDone.emit(i)
        self.cache.save()
