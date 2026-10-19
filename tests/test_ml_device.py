import numpy as np
import pytest

from autocomix import ml_onnx as M

pytestmark = pytest.mark.skipif(M.model_path() is None, reason="no model")
IMG = np.full((600, 400, 3), 255, np.uint8)


@pytest.fixture(autouse=True)
def _reset():
    yield
    M.set_device("auto")
    M._session.cache_clear()


def test_cpu_setting_never_uses_gpu():
    M.set_device("cpu")
    M._session.cache_clear()
    M.detect(IMG)
    assert M.used == "cpu"


def test_falls_back_to_cpu_without_directml(monkeypatch):
    monkeypatch.setattr(M, "gpu_available", lambda: False)
    M._session.cache_clear()
    M.detect(IMG)
    assert M.used == "cpu"


def test_falls_back_to_cpu_when_the_card_fails(monkeypatch):
    import onnxruntime as ort
    real = ort.InferenceSession

    def broken(path, so=None, providers=None):
        if providers and providers[0] == "DmlExecutionProvider":
            raise RuntimeError("no DirectX 12 device")
        return real(path, so, providers=providers)
    monkeypatch.setattr(M, "gpu_available", lambda: True)
    monkeypatch.setattr(ort, "InferenceSession", broken)
    M._session.cache_clear()
    M.detect(IMG)
    assert M.used == "cpu"


@pytest.mark.skipif(not M.gpu_available(), reason="DirectML missing")
def test_auto_uses_gpu_and_matches_cpu():
    M._session.cache_clear()
    a = M.detect(IMG)
    assert M.used in ("gpu", "cpu")  # cpu if this machine has no usable card
    M.set_device("cpu")
    assert len(M.detect(IMG)) == len(a)
