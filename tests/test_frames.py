import numpy as np
import pytest

from roadpush.frames import Track, frame_times, interpolate, load_gpx, smooth

GPX = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">
<trk><trkseg>
<trkpt lat="37.5580" lon="126.9360"><time>2026-10-22T01:00:00Z</time></trkpt>
<trkpt lat="37.5581" lon="126.9361"><time>2026-10-22T01:00:02Z</time></trkpt>
<trkpt lat="37.5582" lon="126.9362"><time>2026-10-22T01:00:04Z</time></trkpt>
<trkpt lat="37.5590" lon="126.9370"><time>2026-10-22T01:01:00Z</time></trkpt>
</trkseg></trk></gpx>"""


def test_load_and_interpolate(tmp_path):
    p = tmp_path / "a.gpx"; p.write_text(GPX)
    tr = load_gpx(p)
    assert len(tr.t) == 4
    t0 = tr.t[0]
    lat, lon, ok = interpolate(tr, np.array([t0 + 1, t0 + 3, t0 + 30, t0 - 5]), max_gap_s=10)
    assert lat[0] == pytest.approx(37.55805) and lon[1] == pytest.approx(126.93615)
    assert ok.tolist() == [True, True, False, False]     # 56초 공백, 범위 밖


def test_smooth_keeps_length_and_straight_line():
    t = np.arange(10.0)
    tr = smooth(Track(t, np.linspace(0, 1, 10), np.linspace(0, 1, 10)), 5)
    assert len(tr.lat) == 10
    assert tr.lat[5] == pytest.approx(5 / 9)


def test_frame_times():
    assert frame_times(3, 1.0).tolist() == [0.5, 1.5, 2.5]
