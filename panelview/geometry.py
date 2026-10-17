"""Rutlogik: slå ihop CV/ML, ta bort dubbletter, helsida-regler, läsordning.

Rutor är dicts {x, y, w, h} normaliserade till 0..1 av sidan.
"""

FULL = {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}
CONTAIN = 0.75    # andel av mindre rutan inuti större => "inuti"
FULL_ANY = 0.80   # en ruta så stor => visa hela sidan
FULL_SINGLE = 0.50  # ensam ruta så stor => visa hela sidan
IOU_BAD = 0.30    # kvarvarande överlapp => opålitligt => helsida
GAP_MAX = 0.30    # ML-ruta räknas som ny om max så mycket ligger i CV-rutor
MIN_AREA = 0.03
OVERLAP = 0.15    # läsordning: så stor andel av sin höjd/bredd får en ruta överlappa grannen och ändå räknas skild


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
    """Stor ruta med >=2 rutor inuti tas bort; annars tas den inneslutna mindre bort."""
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
    """CV om den ser ren ut (+ ML-rutor i luckor), annars ML, annars CV."""
    if cv_good(cv):
        out = []
        for c in cv:  # CV slår ofta ihop rutor utan tydlig marginal: dela upp där ML ser flera rutor inuti
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
    """Grupperar rutor i rader efter överkanten: en ruta hör till raden om dess överkant ligger i övre halvan
    av radens lägsta ruta (tål sneda/förskjutna rader). En hög ruta hör till raden där den börjar."""
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
    """Delar rutorna där ingen ruta korsar en linje tvärs över axeln a ('y' = rader, 'x' = kolumner).
    En ruta får sticka in OVERLAP i grannen (sneda/förskjutna rutor) utan att linjen räknas som bruten."""
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
    """Läsordning. Egen ordning (n, från ordningsläget) går först. Standard: rad för rad, uppifrån och ned, inom
    raden vänster→höger (höger→vänster i japanskt läge).
    xy: XY-snitt – dela i rader där ett mellanrum går tvärs över, annars i kolumner, och upprepa inuti varje del.
    Då läses en staplad kolumn bredvid en hög ruta (4 över 6, 5 hög till höger) som 4-6-5 i stället för 4-5-6."""
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
    """Rensade rutor i läsordning, eller [] om hela sidan ska visas."""
    ps = dedupe([clip(p) for p in ps if p["w"] > 0 and p["h"] > 0])
    if not ps or any(area(p) >= FULL_ANY for p in ps):
        return []
    if len(ps) == 1 and area(ps[0]) >= FULL_SINGLE:
        return []
    if any(iou(a, b) > IOU_BAD for i, a in enumerate(ps) for b in ps[i + 1:]):
        return []
    return order(ps, rtl, xy)


def panel_at(gray, x, y):
    """Ruta under punkten (x, y i pixlar) direkt ur bilden, för dubbelklick när detekteringen missat.

    1) Ramlinjer: långa raka mörka linjer (morfologisk öppning) blir väggar, fyll från punkten.
    2) Mellanrum: färgen tas från sidkanten, sammanhängande yta som inte är mellanrum runt punkten.
    Returnerar normaliserad ruta (0.02-0.8 av sidan) eller None.
    """
    import cv2
    import numpy as np
    H, W = gray.shape
    x, y = int(min(max(x, 0), W - 1)), int(min(max(y, 0), H - 1))

    def comp(free, conn):
        n, lab, st, _ = cv2.connectedComponentsWithStats(free.astype(np.uint8), conn)
        ys, xs = np.nonzero(lab[max(0, y - 6):y + 7, max(0, x - 6):x + 7])  # klick på en linje: närmaste yta
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
