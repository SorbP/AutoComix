"""Panel detection one batch at a time (detect_batch): the window lo..hi and that the background thread waits between batches."""
import time

from autocomix import detector as D


class FakeComic:
    def __init__(self, n):
        self.pages = [f"p{i:04d}.png" for i in range(n)]

    def read(self, i):
        return b""


class FakeCache:
    def __init__(self):
        self.d = {}

    def get(self, name):
        return self.d.get(name)

    def put(self, name, cv, ml):
        self.d[name] = (cv, ml)

    def save(self):
        pass


def make(n, focus=0, batch=100):
    det = D.Detector(FakeComic(n), FakeCache())
    det.set_focus(focus)
    det.set_batch(batch)
    return det


def test_window_from_start():
    det = make(500)
    todo, left = det._todo()
    assert (det.lo, det.hi) == (0, 100) and todo == list(range(100)) and left == 500


def test_extends_near_end_of_batch():
    det = make(500)
    det.set_focus(85)
    assert det.hi == 100
    det.set_focus(90)  # 10 pages from the edge: next batch
    assert (det.lo, det.hi) == (0, 200)


def test_jump_outside_window_starts_new_batch():
    det = make(1000)
    det.set_focus(600)
    assert (det.lo, det.hi) == (590, 700)
    assert det._todo()[0][0] == 600  # current page first
    det.set_focus(595)  # backwards near the start of the window: the batch backwards is added
    assert det.lo == 490


def test_no_batch_scans_everything():
    det = D.Detector(FakeComic(300), FakeCache())
    assert len(det._todo()[0]) == 300


def test_thread_waits_between_batches(monkeypatch):
    monkeypatch.setattr(D, "detect_bytes", lambda data, ml_ok=True: ([], [], ml_ok))
    det = make(250)
    det.start()
    try:
        t0 = time.monotonic()
        while len(det.cache.d) < 100 and time.monotonic() - t0 < 10:
            time.sleep(0.01)
        time.sleep(0.2)
        assert len(det.cache.d) == 100 and det.isRunning()  # first batch done, the thread waits
        det.set_focus(95)
        t0 = time.monotonic()
        while len(det.cache.d) < 200 and time.monotonic() - t0 < 10:
            time.sleep(0.01)
        time.sleep(0.2)
        assert len(det.cache.d) == 200
        det.set_focus(195)
        t0 = time.monotonic()
        while det.isRunning() and time.monotonic() - t0 < 10:
            time.sleep(0.01)
        assert len(det.cache.d) == 250 and not det.isRunning()  # everything scanned: the thread exits
    finally:
        det.stop()
