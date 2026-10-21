"""여러 COCO 분할 + SAM 3 의사 라벨을 하나의 RF-DETR 데이터셋으로 합친다.

AI Hub Surface 에는 장애물이, Polygon 에는 보도면이 없다. 그대로 합치면 '안 그린 차량'을
배경으로 배우게 된다 → 각 소스의 결측 클래스를 SAM 3 의사 라벨로 채운다(train 만).
valid 는 GT 그대로 두고, 평가는 evaluate.py --classes 로 소스별 라벨된 클래스만 본다.

사용:
    python -m roadpush.merge_coco --out data/coco/unified_v1 \
        --src data/coco/surface_v1:outputs/sam3/surface_train_obstacle.coco.json \
        --src data/coco/polygon_v1:outputs/sam3/polygon_train_surface.coco.json \
        --pseudo-score 0.5
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .classes import CLASSES, CLASS_TO_ID


def _load(p: Path) -> dict:
    return json.loads(p.read_text())


def merge_split(sources: list[tuple[Path, Path | None]], split: str, out_dir: Path,
                pseudo_score: float, min_area: float) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    images, anns = [], []
    stats = {"gt": 0, "pseudo": 0, "pseudo_dropped": 0, "dup_skipped": 0}
    seen_files: set[str] = set()   # 여러 소스에 같은 이미지가 있으면 먼저 나온 것만
    for src_dir, pseudo in sources:
        gt = _load(src_dir / split / "_annotations.coco.json")
        gname = {c["id"]: c["name"] for c in gt["categories"]}
        ps_by_file: dict[str, list[dict]] = {}
        if pseudo is not None and split == "train" and pseudo.exists():
            pd_ = _load(pseudo)
            pname = {c["id"]: c["name"] for c in pd_["categories"]}
            fid = {im["id"]: im["file_name"] for im in pd_["images"]}
            for a in pd_["annotations"]:
                if a.get("score", 1.0) < pseudo_score or a["area"] < min_area:
                    stats["pseudo_dropped"] += 1
                    continue
                a = {**a, "category_id": CLASS_TO_ID[pname[a["category_id"]]]}
                ps_by_file.setdefault(fid[a["image_id"]], []).append(a)
        gt_by: dict[int, list[dict]] = {}
        for a in gt["annotations"]:
            gt_by.setdefault(a["image_id"], []).append(a)
        for im in gt["images"]:
            if im["file_name"] in seen_files:
                stats["dup_skipped"] += 1
                continue
            seen_files.add(im["file_name"])
            new_id = len(images) + 1
            images.append({**im, "id": new_id})
            dst = out_dir / im["file_name"]
            if not dst.exists():
                os.symlink((src_dir / split / im["file_name"]).resolve(), dst)
            for a in gt_by.get(im["id"], []):
                anns.append({**a, "id": len(anns) + 1, "image_id": new_id,
                             "category_id": CLASS_TO_ID[gname[a["category_id"]]]})
                stats["gt"] += 1
            for a in ps_by_file.get(im["file_name"], []):
                anns.append({**a, "id": len(anns) + 1, "image_id": new_id})
                stats["pseudo"] += 1
    cats = [{"id": CLASS_TO_ID[c], "name": c, "supercategory": "roadpush"} for c in CLASSES]
    (out_dir / "_annotations.coco.json").write_text(
        json.dumps({"images": images, "annotations": anns, "categories": cats}, ensure_ascii=False))
    return {"images": len(images), **stats}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", action="append", required=True, help="<coco_dir>[:<pseudo_json>]")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--pseudo-score", type=float, default=0.5)
    ap.add_argument("--min-area", type=float, default=200.0, help="의사 라벨 최소 면적(px²)")
    args = ap.parse_args(argv)
    sources = []
    for s in args.src:
        d, _, p = s.partition(":")
        sources.append((Path(d), Path(p) if p else None))
    for split in ("train", "valid"):
        print(split, merge_split(sources, split, args.out / split, args.pseudo_score, args.min_area))


if __name__ == "__main__":
    main()
