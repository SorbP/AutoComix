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
    assert G.finalize([wide, bot, top, tall], rtl=True) == [top, bot, tall, wide]


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
