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
            ml = ml_onnx.detect(img, conf=0.25, min_area_frac=0.02)
        except Exception:  # modell/onnxruntime saknas => kör bara CV
            ml_ok = False
    return cv, ml, ml_ok


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
