"""Från cbxy 0.1.2 (MIT, se LICENSE_cbxy). Endast import-sökvägen ändrad."""
import cv2
import numpy as np

from .cbxy_panels import Panel, reading_order_key, suppress_nested


def detect_panels(
    image: np.ndarray,
    *,
    min_area_frac: float = 0.03,
    max_area_frac: float = 0.85,
    gutter_threshold: int = 230,
    close_kernel: int = 5,
) -> list[Panel]:
    """
    Detect panels on a traditional comic page with light gutters.

    Pipeline:
      grayscale → threshold gutters → close gaps → find contours →
      filter by area / aspect → normalize → reading order.
    """
    if image.ndim == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    h, w = gray.shape[:2]
    page_area = float(h * w)

    # White (or near-white) pixels become gutters / page background.
    _, binary = cv2.threshold(gray, gutter_threshold, 255, cv2.THRESH_BINARY)

    # Panel interiors are dark relative to gutters; invert so panels are white blobs.
    panels_mask = cv2.bitwise_not(binary)

    # Close thin cracks inside panels (halftone holes, speech-bubble edges).
    k = max(3, close_kernel | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
    panels_mask = cv2.morphologyEx(panels_mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    # Knock out the outer page margin so we don't treat the whole page as one panel.
    # Flood-fill from corners on the *gutter* mask, then invert result.
    gutters = binary.copy()
    ff_mask = np.zeros((h + 2, w + 2), np.uint8)
    for seed in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        if gutters[seed[1], seed[0]] > 0:
            cv2.floodFill(gutters, ff_mask, seed, 128)

    # Connected components that aren't page background.
    # Use the closed inverted mask intersected away from flooded margin.
    background = gutters == 128
    content = panels_mask.copy()
    content[background] = 0

    contours, _ = cv2.findContours(content, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    panels: list[Panel] = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_area_frac * page_area or area > max_area_frac * page_area:
            continue

        x, y, bw, bh = cv2.boundingRect(contour)
        aspect = bw / max(bh, 1)
        if aspect < 0.15 or aspect > 8.0:
            continue
        # Reject very thin strips that are usually leftover gutter artifacts.
        if bw < 0.08 * w or bh < 0.05 * h:
            continue

        panels.append(
            Panel(
                x=x / w,
                y=y / h,
                w=bw / w,
                h=bh / h,
            )
        )

    panels.sort(key=reading_order_key)

    # Merge nested / near-duplicate boxes (speech bubbles caught as mini-panels).
    panels = suppress_nested(panels)
    panels.sort(key=reading_order_key)
    return panels
