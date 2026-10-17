import zipfile

import pytest

from panelview import geometry as G
from panelview.comic import Comic, pick_images


def P(x, y, w, h):
    return {"x": x, "y": y, "w": w, "h": h}


GRID = [P(0, 0, .45, .3), P(.5, 0, .45, .3), P(0, .35, .45, .3), P(.5, .35, .45, .3)]


def test_order_ltr_rtl():
    assert G.finalize(GRID, rtl=False) == [GRID[0], GRID[1], GRID[2], GRID[3]]
    assert G.finalize(GRID, rtl=True) == [GRID[1], GRID[0], GRID[3], GRID[2]]


def test_order_tall_panel_beside_stack():
    tall, top, bot, wide = P(0, 0, .4, .6), P(.45, 0, .5, .28), P(.45, .32, .5, .28), P(0, .65, .95, .3)
    assert G.finalize([wide, bot, top, tall], rtl=False) == [tall, top, bot, wide]
    assert G.finalize([wide, bot, top, tall], rtl=True) == [top, tall, bot, wide]


def test_order_strict_rows_stack_left_tall_right():
    # vänster: två staplade, höger: en hög. Rad för rad: övre vänster, höga högra, sedan nedre vänster.
    tl, bl, tall = P(0, 0, .45, .28), P(0, .32, .45, .28), P(.5, 0, .45, .6)
    assert G.finalize([bl, tall, tl]) == [tl, tall, bl]


def test_order_xy_stack_left_tall_right():
    # samma layout med XY-ordning: den staplade vänsterkolumnen först (4-6-5)
    tl, bl, tall = P(0, 0, .45, .28), P(0, .32, .45, .28), P(.5, 0, .45, .6)
    assert G.finalize([bl, tall, tl], xy=True) == [tl, bl, tall]
    assert G.finalize([bl, tall, tl], rtl=True, xy=True) == [tall, tl, bl]
    assert G.finalize(GRID, xy=True) == GRID  # vanligt rutnät: samma som rad för rad


def test_order_manual_n_wins():
    a, b, c = dict(P(0, 0, .45, .28), n=2), dict(P(0, .32, .45, .28), n=0), dict(P(.5, 0, .45, .6), n=1)
    assert G.order([a, b, c], rtl=False) == [b, c, a]
    assert G.order([a, b, c], rtl=True, xy=True) == [b, c, a]


def test_order_z_grid_3x3():
    g = [P(c * .33, r * .33, .3, .3) for r in range(3) for c in range(3)]
    shuffled = [g[i] for i in (8, 3, 0, 5, 1, 7, 2, 6, 4)]
    assert G.finalize(shuffled) == g


def test_order_staggered_row():
    a, b, c = P(0, 0, .45, .4), P(.5, .05, .45, .35), P(0, .5, .95, .4)
    assert G.finalize([c, b, a]) == [a, b, c]


def test_big_box_with_two_inside_is_dropped():
    big = P(0, 0, .6, .6)
    out = G.finalize([big, P(.05, .05, .2, .2), P(.3, .3, .2, .2)])
    assert big not in out and len(out) == 2


def test_small_box_inside_single_big_is_dropped():
    out = G.finalize([P(0, 0, .45, .45), P(.1, .1, .2, .2), P(.5, .5, .4, .4)])
    assert out == [P(0, 0, .45, .45), P(.5, .5, .4, .4)]


@pytest.mark.parametrize("ps", [
    [],                                   # inget hittat
    [P(0, 0, .95, .9)],                   # en nästan helsida
    [P(0, 0, .8, .7)],                    # ensam ruta > 50 %
    [P(0, 0, .5, .5), P(.1, .1, .5, .5)],  # kraftigt överlapp
])
def test_full_page_fallbacks(ps):
    assert G.finalize(ps) == []


def test_merge_prefers_clean_cv_and_fills_gaps_with_ml():
    cv = GRID[:2]
    ml = [P(0, 0, .45, .3), P(0, .7, .9, .25)]  # dubblett + ny ruta i lucka
    assert G.merge(cv, ml) == cv + [ml[1]]


def test_merge_splits_cv_box_that_contains_several_ml_panels():
    cv = [P(0, 0, .95, .3), P(0, .35, .95, .3)]
    ml = [P(0, .35, .45, .3), P(.5, .35, .45, .3), P(0, 0, .95, .3)]
    out = G.merge(cv, ml)
    assert P(0, .35, .95, .3) not in out and P(0, .35, .45, .3) in out and P(.5, .35, .45, .3) in out


def test_merge_falls_back_to_ml_when_cv_collapses():
    ml = GRID
    assert G.merge([P(0, 0, 1, 1)], ml) == ml
    assert G.merge([], []) == []


def test_clip_out_of_range():
    assert G.clip(P(-.1, -.1, .5, 1.5)) == P(0, 0, .4, 1.0)


def test_pick_images_dedupes_formats_and_sorts_naturally():
    names = ["p_10.webp", "p_10.png", "p_2.webp", "p_1.png", "Thumbs.db", "__MACOSX/p_1.png"]
    assert pick_images(names) == ["p_1.png", "p_2.webp", "p_10.png"]


def test_comic_dir_and_cbz(tmp_path):
    d = tmp_path / "bok"
    d.mkdir()
    for n in ("2.jpg", "10.jpg", "1.jpg"):
        (d / n).write_bytes(n.encode())
    c = Comic(d)
    assert c.pages == ["1.jpg", "2.jpg", "10.jpg"] and c.read(2) == b"10.jpg"
    z = tmp_path / "bok.cbz"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("a/01.png", b"x")
        zf.writestr("a/02.png", b"y")
    c = Comic(z)
    assert c.pages == ["a/01.png", "a/02.png"] and c.read(1) == b"y"
    c.close()
    assert [p.name for p in Comic(d).siblings()] == ["bok", "bok.cbz"]


def test_sort_by_mtime_dir_and_zip(tmp_path):
    import os
    from PIL import Image
    from panelview.browser import PageSource
    d = tmp_path / "slump"
    d.mkdir()
    for i, n in enumerate(["zz.png", "aa.png", "mm.png"]):  # tillagda i ordningen zz, aa, mm
        Image.new("RGB", (8, 8)).save(d / n)
        os.utime(d / n, (1_600_000_000 + i * 60,) * 2)
    assert Comic(d).pages == ["aa.png", "mm.png", "zz.png"]
    assert Comic(d, sort="mtime").pages == ["zz.png", "aa.png", "mm.png"]
    assert PageSource(d, "mtime").names == ["zz.png", "aa.png", "mm.png"]
    z = tmp_path / "s.cbz"
    with zipfile.ZipFile(z, "w") as zf:
        for i, n in enumerate(["zz.png", "aa.png", "mm.png"]):
            zf.writestr(zipfile.ZipInfo(n, (2020, 1, 1, 12, i, 0)), (d / n).read_bytes())
    assert Comic(z, sort="mtime").pages == ["zz.png", "aa.png", "mm.png"]


def test_comicinfo_manga_hint(tmp_path):
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (10, 10)).save(buf, "PNG")
    z = tmp_path / "m.cbz"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("001.png", buf.getvalue())
        f.writestr("ComicInfo.xml", "<ComicInfo><Manga>YesAndRightToLeft</Manga></ComicInfo>")
    assert Comic(z).rtl_hint() is True


def test_order_random_row_layouts():
    """500 slumpade sidor med 1–4 rader, 1–4 rutor per rad, ojämna överkanter: alltid rad för rad."""
    import random
    rnd = random.Random(7)
    for _ in range(500):
        y, want = 0.02, []
        for _r in range(rnd.randint(1, 4)):
            h = rnd.uniform(.15, .3)
            n = rnd.randint(1, 4)
            xs = sorted(rnd.uniform(0, 1) for _ in range(n - 1))
            edges = [0.02] + [0.02 + .96 * x for x in xs] + [0.98]
            row = []
            for i in range(n):
                if edges[i + 1] - edges[i] < .1:
                    continue
                jitter = rnd.uniform(-.02, .02)
                row.append(P(edges[i] + .01, max(0, y + jitter), edges[i + 1] - edges[i] - .02, h - .02))
            want += row
            y += h + .02
        got = G.order(rnd.sample(want, len(want)), rtl=False)
        assert got == want


def test_set_page_keeps_panel(tmp_path, monkeypatch):
    from panelview import store
    monkeypatch.setattr(store, "STATE", tmp_path / "state.json")
    st = store.State()
    st.set_page(tmp_path / "bok", 7, 3)
    assert st.comic(tmp_path / "bok") == {"page": 7, "panel": 3}
    st.set_page(tmp_path / "bok", 8)  # ny sida utan ruta: rutan från förra sidan gäller inte
    assert st.comic(tmp_path / "bok") == {"page": 8}
    assert st.d["last"] == str(tmp_path / "bok")


def test_history_keeps_20_newest_with_position(tmp_path, monkeypatch):
    from panelview import store
    monkeypatch.setattr(store, "STATE", tmp_path / "state.json")
    st = store.State()
    for i in range(25):
        st.add_history(tmp_path / f"b{i}.cbz", pages=30)
    st.add_history(tmp_path / "b3.cbz", pages=30)  # öppnad igen: flyttas först, ingen dubblett
    h = st.d["history"]
    assert len(h) == 20 and h[0] == str(tmp_path / "b3.cbz") and h.count(str(tmp_path / "b3.cbz")) == 1
    assert st.comic(tmp_path / "b3.cbz")["pages"] == 30 and st.comic(tmp_path / "b3.cbz")["opened"] > 0
