import numpy as np
import pytest

from roadpush.width_ratio import (
    dilate, footpoint, frame_ratio, obstacles_on_sidewalk, row_ratio, runs,
)


def _canvas(h=100, w=200):
    return np.zeros((h, w), dtype=bool)


def test_runs_basic():
    row = np.array([0, 1, 1, 0, 1, 0, 0, 1, 1, 1], dtype=bool)
    assert runs(row) == [(1, 3), (4, 5), (7, 10)]
    assert runs(np.zeros(5, dtype=bool)) == []


def test_row_ratio_obstacle_in_middle():
    S = np.zeros(200, dtype=bool); S[50:150] = True        # 보도 100px
    O = np.zeros(200, dtype=bool); O[90:110] = True        # 가운데 장애물 20px
    S[90:110] = False                                      # 세그 모델은 장애물 아래 보도를 못 봄
    r = row_ratio(S, O)
    assert r.span == 100 and r.blocked == 20 and r.free == 40
    assert r.ratio == pytest.approx(0.4)


def test_row_ratio_no_obstacle():
    S = np.zeros(200, dtype=bool); S[50:150] = True
    r = row_ratio(S, np.zeros(200, dtype=bool))
    assert r.ratio == pytest.approx(1.0)


def test_row_ratio_picks_sidewalk_with_more_pixels():
    S = np.zeros(300, dtype=bool); S[10:40] = True; S[150:250] = True   # 좌 30px, 우 100px
    O = np.zeros(300, dtype=bool)
    r = row_ratio(S, O)
    assert r.span == 100


def test_row_ratio_none_when_too_little_sidewalk():
    S = np.zeros(200, dtype=bool); S[10:20] = True
    assert row_ratio(S, np.zeros(200, dtype=bool), min_sidewalk_px=40) is None


def test_frame_ratio_median_and_presence():
    sw = _canvas(); ob = _canvas()
    sw[50:100, 50:150] = True
    ob[60:100, 90:110] = True
    sw[60:100, 90:110] = False
    res = frame_ratio(sw, ob)
    assert res.sidewalk_present
    assert res.ratio == pytest.approx(0.4)
    assert res.min_ratio == pytest.approx(0.4)
    assert res.valid_fraction == 1.0


def test_frame_ratio_no_sidewalk():
    res = frame_ratio(_canvas(), _canvas())
    assert not res.sidewalk_present and res.ratio == 0.0


def test_footpoint_and_filter():
    sw = _canvas(); sw[50:100, 50:150] = True
    on = _canvas(); on[60:99, 95:105] = True        # 발점 (98, ~99) → 보도 안
    off = _canvas(); off[60:99, 170:190] = True     # 발점 x≈179 → 보도 밖(차도)
    assert footpoint(on) == (98, 99) or footpoint(on) == (98, 100)
    m = obstacles_on_sidewalk(sw, [on, off], dilate_px=5)
    assert m[70, 100] and not m[70, 180]


def test_dilate_grows_square():
    m = _canvas(); m[50, 50] = True
    d = dilate(m, 2)
    assert d[48:53, 48:53].all() and not d[47, 50] and not d[50, 53]
