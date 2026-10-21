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


def test_merge_coco_fills_missing(tmp_path):
    import json
    from roadpush.merge_coco import merge_split
    src = tmp_path / "src"
    for split in ("train", "valid"):
        d = src / split; d.mkdir(parents=True)
        (d / "a.jpg").write_bytes(b"x")
        (d / "_annotations.coco.json").write_text(json.dumps({
            "images": [{"id": 7, "file_name": "a.jpg", "width": 10, "height": 10}],
            "annotations": [{"id": 1, "image_id": 7, "category_id": 5, "segmentation": [[0, 0, 5, 0, 5, 5]],
                             "bbox": [0, 0, 5, 5], "area": 12.5, "iscrowd": 0}],
            "categories": [{"id": 5, "name": "sidewalk"}]}))
    ps = tmp_path / "ps.json"
    ps.write_text(json.dumps({
        "images": [{"id": 1, "file_name": "a.jpg"}],
        "annotations": [{"id": 1, "image_id": 1, "category_id": 99, "segmentation": [[0, 0, 9, 0, 9, 9]],
                         "bbox": [0, 0, 9, 9], "area": 300.0, "iscrowd": 0, "score": 0.9},
                        {"id": 2, "image_id": 1, "category_id": 99, "segmentation": [[0, 0, 9, 0, 9, 9]],
                         "bbox": [0, 0, 9, 9], "area": 300.0, "iscrowd": 0, "score": 0.2}],
        "categories": [{"id": 99, "name": "car"}]}))
    tr = merge_split([(src, ps)], "train", tmp_path / "out" / "train", 0.5, 100)
    va = merge_split([(src, ps)], "valid", tmp_path / "out" / "valid", 0.5, 100)
    assert tr == {"images": 1, "gt": 1, "pseudo": 1, "pseudo_dropped": 1}
    assert va["pseudo"] == 0
    d = json.loads((tmp_path / "out" / "train" / "_annotations.coco.json").read_text())
    names = {c["id"]: c["name"] for c in d["categories"]}
    assert sorted(names[a["category_id"]] for a in d["annotations"]) == ["car", "sidewalk"]
