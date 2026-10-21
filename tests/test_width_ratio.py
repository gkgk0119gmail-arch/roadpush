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


def test_frame_ratio_presence_and_clearance():
    sw = _canvas(); ob = _canvas()
    sw[50:100, 50:150] = True
    ob[60:100, 90:110] = True
    sw[60:100, 90:110] = False
    assert frame_ratio(sw, ob, gap_frac=0).ratio == pytest.approx(0.4)
    res = frame_ratio(sw, ob)               # 기본: 화면 폭 1%(2px) 통과 여유
    assert res.sidewalk_present and res.ratio == pytest.approx(0.38)
    assert res.valid_fraction == 1.0


def test_bottleneck_and_gap_bridging():
    sw = _canvas(); ob = _canvas()
    sw[50:100, 50:150] = True
    ob[85:92, 50:100] = True; sw[85:92, 50:100] = False     # 2줄 높이에만 걸친 장애물(왼쪽 절반)
    assert frame_ratio(sw, ob, gap_frac=0).ratio < 0.6      # 중앙값이면 1.0 → 병목으로 반영
    sw2 = _canvas(); ob2 = _canvas()
    sw2[50:100, 60:150] = True
    ob2[50:100, 40:57] = True                               # 보도와 3px 틈을 둔 노점
    assert frame_ratio(sw2, ob2, gap_frac=0).ratio == pytest.approx(1.0)
    assert frame_ratio(sw2, ob2, gap_frac=0.02).ratio < 0.85  # 틈 메움 → 협소로 반영


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


def _trapezoid(h=400, w=800, y_h=100.0, a=1.5, cx=400):
    """지평선 y_h 에서 만나는 사다리꼴 보도: span(y) = a·(y−y_h)."""
    S = np.zeros((h, w), dtype=bool)
    for y in range(int(y_h) + 1, h):
        half = a * (y - y_h) / 2
        S[y, max(0, int(round(cx - half))):min(w, int(round(cx + half)))] = True
    return S


def test_metric_width_recovers_geometry():
    from roadpush.width_ratio import frame_ratio
    S = _trapezoid()
    fr = frame_ratio(S, np.zeros_like(S), cam_h=1.3)
    mw = fr.metric
    assert mw is not None and mw.r2 > 0.99
    assert mw.horizon_y == pytest.approx(100, abs=3)
    assert mw.width_m == pytest.approx(1.3 * 1.5, rel=0.03)      # h·a
    assert mw.min_free_m == pytest.approx(mw.width_m, rel=0.05)


def test_metric_width_obstacle_and_edge_cut():
    from roadpush.width_ratio import frame_ratio
    S = _trapezoid()
    O = np.zeros_like(S); O[200:390, 330:400] = True; S[200:390, 330:400] = False   # 왼쪽 절반 가로막음
    mw = frame_ratio(S, O, cam_h=1.3).metric
    assert mw is not None and mw.min_free_m < mw.width_m * 0.7
    wide = _trapezoid(a=4.0)          # 아래쪽 행은 화면 밖으로 잘림 → 잘리지 않은 행만으로 추정
    mw = frame_ratio(wide, np.zeros_like(wide)).metric
    assert mw is not None and mw.width_m == pytest.approx(1.3 * 4.0, rel=0.03)
    wider = _trapezoid(a=8.0)         # 남는 행이 min_rows 미만 → None
    assert frame_ratio(wider, np.zeros_like(wider)).metric is None


def test_row_ignored_when_corridor_mostly_obstacle():
    S = np.zeros(200, dtype=bool); S[50:60] = True       # 멀리서 조각난 보도 10px … 너무 적어서 기본 min_sidewalk_px 로도 걸러짐
    O = np.zeros(200, dtype=bool); O[60:150] = True      # 붙어 있는 차도 위 트럭 90px
    assert row_ratio(S, O, min_sidewalk_px=5) is None    # 보도 비중 10% < 25% → 판단 제외
    S2 = np.zeros(200, dtype=bool); S2[20:120] = True; S2[90:110] = False
    O2 = np.zeros(200, dtype=bool); O2[90:110] = True    # 보도 한가운데 장애물(보도 비중 80%) → 정상 계산
    assert row_ratio(S2, O2).ratio == pytest.approx(0.7)
