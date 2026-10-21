"""정답(GT) vs 예측의 클래스별 IoU와 유효보행폭 비율 오차.

예측 소스:
    --ckpt <pth>      RF-DETR-Seg 로 직접 추론
    --pred-coco <json> SAM 3 teacher 등이 만든 COCO (score 필드 있으면 --score-min 적용)

지표 (보고서 비교표용):
    semantic IoU (클래스별, 이미지 전체 합산)
    ratio MAE      : |r_pred − r_gt| (GT에 보도가 있는 프레임)
    present acc    : 보도 유무 판정 일치율
    vanish F1      : 보도 소멸 프레임 검출

사용:
    python -m roadpush.evaluate --gt data/coco/aihub_v1/valid --ckpt checkpoints/seg_m_v1/checkpoint_best_total.pth
    python -m roadpush.evaluate --gt data/coco/aihub_v1/valid --pred-coco outputs/sam3/aihub_valid.coco.json
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

from .classes import CLASSES
from .scoring import analyze_frame


def rasterize(anns: list[dict], id2name: dict[int, str], h: int, w: int) -> dict[str, list[np.ndarray]]:
    out: dict[str, list[np.ndarray]] = defaultdict(list)
    for a in anns:
        m = np.zeros((h, w), np.uint8)
        for poly in a["segmentation"]:
            pts = np.round(np.asarray(poly, np.float32).reshape(-1, 2)).astype(np.int32)
            cv2.fillPoly(m, [pts], 1)
        out[id2name[a["category_id"]]].append(m.astype(bool))
    return dict(out)


def _load_coco(path: Path):
    d = json.loads(path.read_text())
    id2name = {c["id"]: c["name"] for c in d["categories"]}
    by_img = defaultdict(list)
    for a in d["annotations"]:
        by_img[a["image_id"]].append(a)
    return d, id2name, by_img


class Accum:
    def __init__(self):
        self.inter = defaultdict(int)
        self.union = defaultdict(int)
        self.err: list[float] = []
        self.present = []           # (gt, pred)
        self.n = 0

    def add(self, gt: dict, pr: dict, shape):
        for c in CLASSES:
            g = np.zeros(shape, bool)
            for m in gt.get(c, ()):
                g |= m
            p = np.zeros(shape, bool)
            for m in pr.get(c, ()):
                p |= m
            if g.any() or p.any():
                self.inter[c] += int((g & p).sum())
                self.union[c] += int((g | p).sum())
        fg, fp = analyze_frame(gt, shape), analyze_frame(pr, shape)
        self.present.append((fg.sidewalk_present, fp.sidewalk_present))
        if fg.sidewalk_present:
            self.err.append(abs((fp.ratio if fp.sidewalk_present else 0.0) - fg.ratio))
        self.n += 1

    def report(self) -> dict:
        iou = {c: round(self.inter[c] / self.union[c], 4) for c in CLASSES if self.union[c]}
        pres = np.array(self.present, bool) if self.present else np.zeros((0, 2), bool)
        gv, pv = ~pres[:, 0], ~pres[:, 1]           # vanish = 보도 없음
        tp, fp_, fn = int((gv & pv).sum()), int((~gv & pv).sum()), int((gv & ~pv).sum())
        f1 = 2 * tp / (2 * tp + fp_ + fn) if (2 * tp + fp_ + fn) else float("nan")
        return {
            "n_images": self.n,
            "miou": round(float(np.mean(list(iou.values()))), 4) if iou else float("nan"),
            "iou": iou,
            "ratio_mae": round(float(np.mean(self.err)), 4) if self.err else float("nan"),
            "ratio_within_0.1": round(float(np.mean(np.array(self.err) <= 0.1)), 4) if self.err else float("nan"),
            "present_acc": round(float((pres[:, 0] == pres[:, 1]).mean()), 4) if len(pres) else float("nan"),
            "vanish_f1": round(f1, 4),
        }


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gt", required=True, type=Path, help="_annotations.coco.json 이 있는 폴더")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--ckpt", nargs="+")
    g.add_argument("--pred-coco", type=Path)
    ap.add_argument("--size", default="medium")
    ap.add_argument("--threshold", type=float, default=0.4)
    ap.add_argument("--score-min", type=float, default=0.0)
    ap.add_argument("--max-images", type=int, default=0)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    gt, gid2name, gt_by = _load_coco(args.gt / "_annotations.coco.json")
    ims = gt["images"][: args.max_images] if args.max_images else gt["images"]
    if args.pred_coco:
        pd_, pid2name, pr_by = _load_coco(args.pred_coco)
        fname2id = {im["file_name"]: im["id"] for im in pd_["images"]}
        ims = [im for im in ims if im["file_name"] in fname2id]
    else:
        from PIL import Image
        from .infer import Predictor
        pred = Predictor(args.ckpt, args.size, args.threshold)

    acc = Accum()
    for k, im in enumerate(ims):
        h, w = im["height"], im["width"]
        gtm = rasterize(gt_by[im["id"]], gid2name, h, w)
        if args.pred_coco:
            anns = [a for a in pr_by[fname2id[im["file_name"]]] if a.get("score", 1.0) >= args.score_min]
            prm = rasterize(anns, pid2name, h, w)
        else:
            img = np.asarray(Image.open(args.gt / im["file_name"]).convert("RGB"))
            prm, shape, _ = pred.masks(img)
            if shape != (h, w):   # 원본 해상도로 맞춤
                prm = {c: [cv2.resize(m.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST).astype(bool)
                           for m in ms] for c, ms in prm.items()}
        acc.add(gtm, prm, (h, w))
        if k % 50 == 0:
            print(f"  {k + 1}/{len(ims)}", flush=True)
    rep = acc.report()
    rep["source"] = " + ".join(args.ckpt) if args.ckpt else str(args.pred_coco)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(rep, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
