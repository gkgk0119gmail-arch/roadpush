import numpy as np
import pytest
from shapely.geometry import LineString

from roadpush.links import LinkSnapper
from roadpush.scoring import (
    PEDESTRIAN, WHEELCHAIR, FrameAnalysis, analyze_frame, grade_of, score_link, score_links,
)

H, W = 200, 400


def _sidewalk():
    m = np.zeros((H, W), dtype=bool); m[100:, 100:300] = True     # 하단 보도 200px 폭
    return m


def test_analyze_frame_clear():
    fa = analyze_frame({"sidewalk": [_sidewalk()]}, (H, W))
    assert fa.sidewalk_present and fa.ratio == pytest.approx(1.0) and fa.tags == []


def test_analyze_frame_car_on_sidewalk_and_roadway():
    sw = _sidewalk()
    car_on = np.zeros((H, W), dtype=bool); car_on[120:190, 100:200] = True   # 보도 왼쪽 절반
    sw[120:190, 100:200] = False
    car_road = np.zeros((H, W), dtype=bool); car_road[120:190, 320:390] = True  # 차도 위
    fa = analyze_frame({"sidewalk": [sw], "car": [car_on, car_road]}, (H, W))
    assert fa.n_obstacles_on_sidewalk == 1
    assert 0.4 < fa.ratio < 0.6


def test_analyze_frame_vanish_and_repair():
    fa = analyze_frame({}, (H, W))
    assert not fa.sidewalk_present and fa.tags == ["vanish"]
    rep = np.zeros((H, W), dtype=bool); rep[150:, 150:250] = True
    fa = analyze_frame({"sidewalk": [_sidewalk()], "repair_zone": [rep]}, (H, W))
    assert "repair" in fa.tags


def _f(r, tags=(), present=True):
    return FrameAnalysis(r, r, present, list(tags))


def test_score_link_safe_vs_danger():
    safe = score_link("a", [_f(0.95)] * 10)
    assert safe.grade == "안전" and safe.primary_type == "none"
    narrow = score_link("b", [_f(0.2)] * 10)
    assert narrow.grade == "위험" and narrow.primary_type == "narrow"
    vanish = score_link("c", [_f(0.0, ["vanish"], False)] * 10)
    assert vanish.score == pytest.approx(100.0) and vanish.primary_type == "vanish"


def test_wheelchair_is_stricter():
    frames = [_f(0.6, ["stairs"])] * 5 + [_f(0.9)] * 5
    assert score_link("x", frames, WHEELCHAIR).score > score_link("x", frames, PEDESTRIAN).score


def test_grade_bounds_and_min_frames():
    assert grade_of(29.9) == "안전" and grade_of(30) == "주의" and grade_of(60) == "위험"
    out = score_links({"a": [_f(0.9)] * 2, "b": [_f(0.1)] * 5})
    assert [s.link_id for s in out] == ["b"]


def test_snapper_offline():
    # 신촌 부근 동서 방향 직선 링크 2개 (약 110m 떨어짐)
    a = LineString([(126.936, 37.558), (126.938, 37.558)])
    b = LineString([(126.936, 37.559), (126.938, 37.559)])
    sn = LinkSnapper(["a", "b"], [a, b], max_dist_m=15)
    s = sn.snap(126.937, 37.55805)          # a에서 약 5.5m
    assert s.link_id == "a" and 4 < s.dist_m < 7 and 80 < s.offset_m < 95
    assert sn.snap(126.937, 37.5585).link_id is None     # 둘 다 50m 이상


def test_grating_walkable_tree_zone_blocks():
    sw = _sidewalk()
    gr = np.zeros((H, W), dtype=bool); gr[150:170, 150:250] = True    # 배수구 덮개: 보도 가운데
    sw[150:170, 150:250] = False
    fa = analyze_frame({"sidewalk": [sw], "manhole_grating": [gr]}, (H, W))
    assert fa.ratio == pytest.approx(1.0)
    tz = np.zeros((H, W), dtype=bool); tz[110:199, 100:180] = True    # 가로수 보호틀: 보도 왼쪽 40%
    sw2 = _sidewalk(); sw2[110:199, 100:180] = False
    fa = analyze_frame({"sidewalk": [sw2], "tree_zone": [tz]}, (H, W))
    assert fa.ratio == pytest.approx(0.6, abs=0.02)


def test_legal_width_aux():
    frames = [FrameAnalysis(0.9, 0.9, True, [], 0, 2.0, 1.0)] * 3 + [FrameAnalysis(0.9, 0.9, True, [], 0, 2.0, 1.8)]
    ls = score_link("x", frames)
    assert ls.frac_below_legal == pytest.approx(0.75) and ls.median_free_width_m == pytest.approx(1.0)
    assert score_link("y", [_f(0.9)] * 3).frac_below_legal is None
