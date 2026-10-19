"""Panel logic: merge CV/ML, remove duplicates, whole-page rules, reading order.

Panels are dicts {x, y, w, h} normalized to 0..1 of the page.
"""

FULL = {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}
CONTAIN = 0.75    # share of the smaller panel inside the larger => "inside"
FULL_ANY = 0.80   # one panel this large => show the whole page
FULL_SINGLE = 0.50  # a single panel this large => show the whole page
IOU_BAD = 0.30    # remaining overlap => unreliable => whole page
GAP_MAX = 0.30    # an ML panel counts as new if at most this much lies in CV panels
MIN_AREA = 0.03
OVERLAP = 0.15    # reading order: a panel may overlap its neighbour by this share of its height/width and still count as separate


def area(p):
    return p["w"] * p["h"]


def inter(a, b):
    w = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
    h = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
    return max(w, 0.0) * max(h, 0.0)


def iou(a, b):
    i = inter(a, b)
    return i / ((area(a) + area(b) - i) or 1.0)


def clip(p):
    if p["x"] >= 0 and p["y"] >= 0 and p["x"] + p["w"] <= 1 and p["y"] + p["h"] <= 1:
        return p
    x, y = max(p["x"], 0.0), max(p["y"], 0.0)
    return {"x": x, "y": y, "w": min(p["x"] + p["w"], 1.0) - x, "h": min(p["y"] + p["h"], 1.0) - y}


def dedupe(ps):
    """A large panel with >=2 panels inside is removed; otherwise the enclosed smaller one is removed."""
    ps = list(ps)
    changed = True
    while changed:
        changed = False
        for big in sorted(ps, key=area, reverse=True):
            inside = [s for s in ps if s is not big and area(s) < area(big)
                      and inter(s, big) / area(s) >= CONTAIN]
            if inside:
                if len(inside) >= 2:
                    ps.remove(big)
                else:
                    ps.remove(inside[0])
                changed = True
                break
    return ps


def cv_good(c):
    return (len(c) >= 2 and all(area(p) < 0.70 for p in c)
            and not any(iou(a, b) > 0.20 for i, a in enumerate(c) for b in c[i + 1:]))


def merge(cv, ml):
    """CV if it looks clean (+ ML panels in gaps), otherwise ML, otherwise CV."""
    if cv_good(cv):
        out = []
        for c in cv:  # CV often merges panels without a clear margin: split where ML sees several panels inside
            inner = [m for m in ml if inter(m, c) / area(m) >= CONTAIN]
            if len(inner) >= 2 and sum(area(m) for m in inner) / area(c) >= 0.35:
                out += inner
            else:
                out.append(c)
        extra = [p for p in ml if p not in out and area(p) >= MIN_AREA
                 and sum(inter(p, q) for q in out) / area(p) <= GAP_MAX]
        return out + extra
    return ml or cv


def rows(ps):
    """Groups panels into rows by their top edge: a panel belongs to the row if its top edge is in the upper half
    of the row's lowest panel (tolerates slanted/offset rows). A tall panel belongs to the row where it starts."""
    ps = sorted(ps, key=lambda p: (p["y"], p["x"]))
    out = []
    for p in ps:
        if out:
            r = out[-1]
            top = min(q["y"] for q in r)
            if p["y"] < top + 0.5 * min(q["h"] for q in r):
                r.append(p)
                continue
        out.append([p])
    return out


def _cut(ps, a, size):
    """Splits the panels where no panel crosses a line across axis a ('y' = rows, 'x' = columns).
    A panel may reach OVERLAP into its neighbour (slanted/offset panels) without the line counting as broken."""
    spans = sorted(((p[a] + OVERLAP * p[size], p[a] + (1 - OVERLAP) * p[size], p) for p in ps), key=lambda t: t[0])
    out, end = [], 0.0
    for s, e, p in spans:
        if out and s < end:
            out[-1].append(p)
            end = max(end, e)
        else:
            out.append([p])
            end = e
    return out


def order(ps, rtl, xy=False):
    """Reading order. A custom order (n, from order mode) comes first. Default: row by row, top to bottom, within
    the row left→right (right→left in manga mode).
    xy: XY cut – split into rows where a gutter runs all the way across, otherwise into columns, and repeat inside each part.
    Then a stacked column beside a tall panel (4 above 6, 5 tall on the right) is read as 4-6-5 instead of 4-5-6."""
    if ps and all("n" in p for p in ps):
        return sorted(ps, key=lambda p: p["n"])
    if xy and len(ps) > 1:
        parts = _cut(ps, "y", "h")
        if len(parts) == 1:
            parts = _cut(ps, "x", "w")
            if rtl:
                parts.reverse()
        if len(parts) > 1:
            return [q for part in parts for q in order(part, rtl, xy)]
    out = []
    for r in rows(ps):
        out += sorted(r, key=lambda p: -(p["x"] + p["w"]) if rtl else p["x"])
    return out


def finalize(ps, rtl=False, xy=False):
    """Cleaned panels in reading order, or [] if the whole page should be shown."""
    ps = dedupe([clip(p) for p in ps if p["w"] > 0 and p["h"] > 0])
    if not ps or any(area(p) >= FULL_ANY for p in ps):
        return []
    if len(ps) == 1 and area(ps[0]) >= FULL_SINGLE:
        return []
    if any(iou(a, b) > IOU_BAD for i, a in enumerate(ps) for b in ps[i + 1:]):
        return []
    return order(ps, rtl, xy)


def panel_at(gray, x, y):
    """The panel under the point (x, y in pixels) straight from the image, for double-clicks where detection missed.

    1) Frame lines: long straight dark lines (morphological opening) become walls, fill from the point.
    2) Gutters: the color is taken from the page edge, the connected non-gutter area around the point.
    Returns a normalized panel (0.02-0.8 of the page) or None.
    """
    import cv2
    import numpy as np
    H, W = gray.shape
    x, y = int(min(max(x, 0), W - 1)), int(min(max(y, 0), H - 1))

    def comp(free, conn):
        n, lab, st, _ = cv2.connectedComponentsWithStats(free.astype(np.uint8), conn)
        ys, xs = np.nonzero(lab[max(0, y - 6):y + 7, max(0, x - 6):x + 7])  # click on a line: nearest area
        if lab[y, x]:
            return st[lab[y, x]]
        if len(xs):
            return st[lab[max(0, y - 6) + ys[0], max(0, x - 6) + xs[0]]]
        return None

    dark = (gray < 110).astype(np.uint8)
    lines = cv2.morphologyEx(dark, cv2.MORPH_OPEN, np.ones((1, max(W // 10, 20)), np.uint8))
    lines |= cv2.morphologyEx(dark, cv2.MORPH_OPEN, np.ones((max(H // 10, 20), 1), np.uint8))
    lines = cv2.dilate(lines, np.ones((5, 5), np.uint8))
    k = max(3, W // 150) | 1
    border = np.concatenate([gray[:3].ravel(), gray[-3:].ravel(), gray[:, :3].ravel(), gray[:, -3:].ravel()])
    ink = (np.abs(gray.astype(np.int16) - float(np.median(border))) > 28).astype(np.uint8)
    ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    for st in (comp(lines == 0, 4), comp(ink > 0, 8)):
        if st is None:
            continue
        bx, by, bw, bh, _a = st
        p = {"x": bx / W, "y": by / H, "w": bw / W, "h": bh / H}
        if 0.02 <= area(p) <= 0.8:
            return p
    return None
