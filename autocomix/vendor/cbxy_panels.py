"""From cbxy 0.1.2 (MIT, see LICENSE_cbxy). Only the import path changed."""
from dataclasses import asdict, dataclass

import cv2
import numpy as np


@dataclass
class Panel:
    """Axis-aligned panel box, normalized to [0, 1] of page size."""

    x: float
    y: float
    w: float
    h: float

    def to_pixels(self, width: int, height: int) -> tuple[int, int, int, int]:
        return (
            int(round(self.x * width)),
            int(round(self.y * height)),
            int(round(self.w * width)),
            int(round(self.h * height)),
        )


@dataclass
class DetectionResult:
    page: str
    width: int
    height: int
    panels: list[Panel]
    engine: str = "cv"

    def to_dict(self) -> dict:
        return {
            "page": self.page,
            "width": self.width,
            "height": self.height,
            "panels": [asdict(p) for p in self.panels],
        }


def reading_order_key(panel: Panel, row_tolerance: float = 0.08) -> tuple[int, float]:
    """Sort LTR / TTB by banded rows, then left-to-right within a row."""
    row = int(panel.y / row_tolerance)
    return (row, panel.x)


def containment(inner: Panel, outer: Panel) -> float:
    """Fraction of `inner` area that lies inside `outer`."""
    ix1, iy1 = inner.x, inner.y
    ix2, iy2 = inner.x + inner.w, inner.y + inner.h
    ox1, oy1 = outer.x, outer.y
    ox2, oy2 = outer.x + outer.w, outer.y + outer.h

    x1 = max(ix1, ox1)
    y1 = max(iy1, oy1)
    x2 = min(ix2, ox2)
    y2 = min(iy2, oy2)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    inner_area = max(inner.w * inner.h, 1e-9)
    return inter / inner_area


def iou(a: Panel, b: Panel) -> float:
    ax2, ay2 = a.x + a.w, a.y + a.h
    bx2, by2 = b.x + b.w, b.y + b.h
    x1 = max(a.x, b.x)
    y1 = max(a.y, b.y)
    x2 = min(ax2, bx2)
    y2 = min(ay2, by2)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    union = a.w * a.h + b.w * b.h - inter
    return inter / max(union, 1e-9)


def suppress_nested(panels: list[Panel], iou_thresh: float = 0.55) -> list[Panel]:
    """Drop boxes mostly contained in a larger panel."""
    if not panels:
        return panels

    kept: list[Panel] = []
    by_area = sorted(panels, key=lambda p: p.w * p.h, reverse=True)
    for candidate in by_area:
        if any(containment(candidate, parent) >= iou_thresh for parent in kept):
            continue
        kept.append(candidate)
    return kept


def nms(panels: list[Panel], iou_thresh: float = 0.65) -> list[Panel]:
    """Drop near-duplicate overlaps; keep nested splash/inset pairs."""
    if not panels:
        return panels
    kept: list[Panel] = []
    for candidate in sorted(panels, key=lambda p: p.w * p.h, reverse=True):
        if any(iou(candidate, other) >= iou_thresh for other in kept):
            continue
        kept.append(candidate)
    return kept


def draw_panels(
    image: np.ndarray,
    panels: list[Panel],
    *,
    color: tuple[int, int, int] = (0, 80, 255),
    thickness: int = 4,
) -> np.ndarray:
    """Return a BGR copy of `image` with numbered panel boxes drawn."""
    out = image.copy()
    h, w = out.shape[:2]
    for i, panel in enumerate(panels, start=1):
        x, y, bw, bh = panel.to_pixels(w, h)
        cv2.rectangle(out, (x, y), (x + bw, y + bh), color, thickness)
        label = str(i)
        (tw, th), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 1.2, 2)
        pad = 6
        cv2.rectangle(
            out,
            (x, y),
            (x + tw + pad * 2, y + th + baseline + pad * 2),
            color,
            -1,
        )
        cv2.putText(
            out,
            label,
            (x + pad, y + th + pad),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.2,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
    return out
