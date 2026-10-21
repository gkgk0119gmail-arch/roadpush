"""SAM 3 teacher: 텍스트 프롬프트 zero-shot 분할 → RoadPush 클래스 COCO 의사 라벨.

SAM 3는 커스텀 SAM License라 **teacher(의사 라벨링·zero-shot 비교)로만** 쓴다.
배포물·웹 데모에는 넣지 않는다 (CLAUDE.md 절대 규칙).

sam3 env 에서 실행 (roadpush 패키지 미설치여도 동작하게 classes 만 경로로 import):
    env -u PYTHONPATH ~/miniconda3/envs/sam3/bin/python src/roadpush/sam3_label.py \
        --images data/coco/aihub_v1/valid --out outputs/sam3/aihub_valid.coco.json --max-images 200
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from roadpush.classes import CLASSES, CLASS_TO_ID  # noqa: E402

# RoadPush 클래스 → 텍스트 프롬프트 (여러 개면 합침)
PROMPTS: dict[str, list[str]] = {
    "sidewalk": ["sidewalk"],
    "braille_guide_blocks": ["yellow tactile paving"],
    "roadway": ["road"],
    "bike_lane": ["bike lane"],
    "stairs": ["stairs"],
    "repair_zone": ["construction site on sidewalk"],
    "car": ["car"],
    "truck_bus": ["truck", "bus"],
    "two_wheeler": ["motorcycle", "bicycle", "scooter"],
    "bollard": ["bollard"],
    "pole": ["pole"],
    "barricade": ["construction barrier"],
    "movable_signage": ["standing signboard"],
    "potted_plant": ["potted plant"],
    "person": ["person"],
}
IMG_EXTS = {".jpg", ".jpeg", ".png"}


def mask_to_polygons(mask: np.ndarray, min_area: float = 64.0, eps_frac: float = 0.002) -> list[list[float]]:
    m = mask.astype(np.uint8)
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    polys = []
    for c in cnts:
        if cv2.contourArea(c) < min_area:
            continue
        c = cv2.approxPolyDP(c, eps_frac * cv2.arcLength(c, True), True)
        if len(c) >= 3:
            polys.append(c.reshape(-1).astype(float).tolist())
    return polys


class Sam3Teacher:
    def __init__(self, threshold: float = 0.5, resolution: int = 1008):
        tok = ROOT / ".hf_token"
        if tok.exists():
            os.environ.setdefault("HF_TOKEN_PATH", str(tok))
        from sam3.model.sam3_image_processor import Sam3Processor
        from sam3.model_builder import build_sam3_image_model

        self.model = build_sam3_image_model()
        self.proc = Sam3Processor(self.model, resolution=resolution, confidence_threshold=threshold)

    def segment(self, image_rgb: np.ndarray, prompts: dict[str, list[str]] = PROMPTS):
        """클래스 → [(mask bool HxW, score)]"""
        import torch
        from PIL import Image

        out: dict[str, list[tuple[np.ndarray, float]]] = {}
        with torch.autocast("cuda", dtype=torch.bfloat16):   # 이미지·텍스트 경로 모두 같은 dtype
            state = self.proc.set_image(Image.fromarray(image_rgb))
            for cls, texts in prompts.items():
                for t in texts:
                    self.proc.reset_all_prompts(state)
                    r = self.proc.set_text_prompt(prompt=t, state=state)
                    masks = r["masks"].squeeze(1).cpu().numpy().astype(bool)
                    scores = r["scores"].float().cpu().numpy()
                    out.setdefault(cls, []).extend(zip(masks, scores.tolist()))
        return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--images", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--max-images", type=int, default=0)
    ap.add_argument("--coco-ref", type=Path, default=None,
                    help="이미지 id/파일명을 맞출 COCO json (기본: <images>/_annotations.coco.json 있으면 사용)")
    args = ap.parse_args(argv)

    ref = args.coco_ref or (args.images / "_annotations.coco.json")
    if ref.exists():
        ims = json.loads(ref.read_text())["images"]
    else:
        files = sorted(p for p in args.images.iterdir() if p.suffix.lower() in IMG_EXTS)
        ims = [{"id": i + 1, "file_name": p.name} for i, p in enumerate(files)]
    if args.max_images:
        ims = ims[: args.max_images]

    teacher = Sam3Teacher(args.threshold)
    images, anns, aid, t0 = [], [], 1, time.time()
    for k, im in enumerate(ims):
        img = cv2.cvtColor(cv2.imread(str(args.images / im["file_name"])), cv2.COLOR_BGR2RGB)
        h, w = img.shape[:2]
        images.append({"id": im["id"], "file_name": im["file_name"], "width": w, "height": h})
        for cls, items in teacher.segment(img).items():
            for mask, score in items:
                for poly in mask_to_polygons(mask):
                    xs, ys = poly[0::2], poly[1::2]
                    area = float(cv2.contourArea(np.array(poly, np.float32).reshape(-1, 2)))
                    anns.append({"id": aid, "image_id": im["id"], "category_id": CLASS_TO_ID[cls],
                                 "segmentation": [poly], "bbox": [min(xs), min(ys), max(xs) - min(xs),
                                                                  max(ys) - min(ys)],
                                 "area": area, "iscrowd": 0, "score": round(score, 4), "source": "sam3"})
                    aid += 1
        if k % 20 == 0:
            print(f"  {k + 1}/{len(ims)} anns={len(anns)} {(time.time() - t0) / (k + 1):.2f}s/img", flush=True)
    cats = [{"id": CLASS_TO_ID[c], "name": c, "supercategory": "roadpush"} for c in CLASSES]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"images": images, "annotations": anns, "categories": cats}))
    print(f"완료: images={len(images)} anns={len(anns)} → {args.out}")


if __name__ == "__main__":
    main()
