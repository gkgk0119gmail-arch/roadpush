import numpy as np
import pytest

from roadpush.evaluate import Accum, rasterize

H, W = 200, 400


def _sw():
    m = np.zeros((H, W), bool); m[100:, 100:300] = True
    return m


def test_rasterize_square():
    ann = {"category_id": 1, "segmentation": [[10, 10, 50, 10, 50, 50, 10, 50]]}
    m = rasterize([ann], {1: "sidewalk"}, 100, 100)["sidewalk"][0]
    assert 1500 < m.sum() < 1800


def test_accum_perfect_and_miss():
    a = Accum()
    gt = {"sidewalk": [_sw()]}
    a.add(gt, gt, (H, W))
    a.add(gt, {}, (H, W))                 # 예측이 보도를 놓침 → ratio 오차 1
    r = a.report()
    assert r["iou"]["sidewalk"] == pytest.approx(0.5)
    assert r["ratio_mae"] == pytest.approx(0.5)
    assert r["present_acc"] == pytest.approx(0.5)
