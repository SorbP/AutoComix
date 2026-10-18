"""Rutdetektering en sats i taget (detect_batch): fönstret lo..hi och att bakgrundstråden väntar mellan satserna."""
import time

from panelview import detector as D


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
    det.set_focus(90)  # 10 sidor från kanten: nästa sats
    assert (det.lo, det.hi) == (0, 200)


def test_jump_outside_window_starts_new_batch():
    det = make(1000)
    det.set_focus(600)
    assert (det.lo, det.hi) == (590, 700)
    assert det._todo()[0][0] == 600  # aktuell sida först
    det.set_focus(595)  # bakåt nära början av fönstret: satsen bakåt läggs till
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
        assert len(det.cache.d) == 100 and det.isRunning()  # första satsen klar, tråden väntar
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
        assert len(det.cache.d) == 250 and not det.isRunning()  # allt skannat: tråden avslutas
    finally:
        det.stop()
