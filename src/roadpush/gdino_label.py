"""Grounding DINO(텍스트→박스) + SAM 2.1(박스→마스크) zero-shot teacher.

SAM 3(sam3_label.py)와 같은 프롬프트·같은 COCO 출력 형식 → evaluate.py 로 teacher 끼리 공정 비교.
둘 다 teacher 전용, 배포물 미포함. (Grounding DINO Apache 2.0, SAM 2.1 Apache 2.0)

사용:
    env -u PYTHONPATH python -m roadpush.gdino_label --images data/coco/polygon_v1/valid \
        --out outputs/teachers/gdino_polygon_valid.coco.json --classes car,truck_bus,two_wheeler,... --max-images 200
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np

from .classes import CLASS_TO_ID
from .sam3_label import IMG_EXTS, PROMPTS, _dump, mask_to_polygons


class GDinoSam:
    def __init__(self, gdino: str = "IDEA-Research/grounding-dino-base", sam: str = "facebook/sam2.1-hiera-large",
                 box_threshold: float = 0.35, text_threshold: float = 0.25):
        import torch
        from transformers import (AutoModelForZeroShotObjectDetection, AutoProcessor, Sam2Model,
                                  Sam2Processor)

        self.torch = torch
        self.dp = AutoProcessor.from_pretrained(gdino)
        self.dm = AutoModelForZeroShotObjectDetection.from_pretrained(gdino).to("cuda").eval()
        self.sp = Sam2Processor.from_pretrained(sam)
        self.sm = Sam2Model.from_pretrained(sam).to("cuda").eval()
        self.bt, self.tt = box_threshold, text_threshold

    def segment(self, image_rgb: np.ndarray, prompts: dict[str, list[str]] = PROMPTS):
        from PIL import Image

        torch = self.torch
        img = Image.fromarray(image_rgb)
        phrase2cls = {t.lower(): c for c, ts in prompts.items() for t in ts}
        text = ". ".join(phrase2cls) + "."
        with torch.inference_mode():
            inp = self.dp(images=img, text=text, return_tensors="pt").to("cuda")
            out = self.dm(**inp)
            det = self.dp.post_process_grounded_object_detection(
                out, inp.input_ids, threshold=self.bt, text_threshold=self.tt, target_sizes=[img.size[::-1]])[0]
        boxes, scores, labels = det["boxes"].cpu().numpy(), det["scores"].cpu().numpy(), det["text_labels"]
        res: dict[str, list[tuple[np.ndarray, float]]] = {}
        keep = [(b, s, self._cls(lbl, phrase2cls)) for b, s, lbl in zip(boxes, scores, labels)]
        keep = [k for k in keep if k[2] is not None]
        if not keep:
            return res
        with torch.inference_mode():
            sin = self.sp(images=img, input_boxes=[[k[0].tolist() for k in keep]], return_tensors="pt").to("cuda")
            sout = self.sm(**sin, multimask_output=False)
            masks = self.sp.post_process_masks(sout.pred_masks.cpu(), sin["original_sizes"])[0]   # (N,1,H,W)
        for (b, s, c), m in zip(keep, masks):
            res.setdefault(c, []).append((m[0].numpy().astype(bool), float(s)))
        return res

    @staticmethod
    def _cls(label: str, phrase2cls: dict[str, str]) -> str | None:
        label = label.lower().strip()
        if label in phrase2cls:
            return phrase2cls[label]
        # GDINO 는 구문 일부만 돌려주기도 함 → 가장 길게 겹치는 프롬프트
        cands = [(len(p), c) for p, c in phrase2cls.items() if label and (label in p or p in label)]
        return max(cands)[1] if cands else None


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--images", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--classes", default="")
    ap.add_argument("--max-images", type=int, default=0)
    ap.add_argument("--box-threshold", type=float, default=0.35)
    args = ap.parse_args(argv)

    ref = args.images / "_annotations.coco.json"
    if ref.exists():
        ims = json.loads(ref.read_text())["images"]
    else:
        files = sorted(p for p in args.images.iterdir() if p.suffix.lower() in IMG_EXTS)
        ims = [{"id": i + 1, "file_name": p.name} for i, p in enumerate(files)]
    if args.max_images:
        ims = ims[:: max(1, len(ims) // args.max_images)][: args.max_images]   # 폴더 고루 샘플
    prompts = {c: PROMPTS[c] for c in args.classes.split(",")} if args.classes else PROMPTS

    teacher = GDinoSam(box_threshold=args.box_threshold)
    images, anns, aid, t0 = [], [], 1, time.time()
    for k, im in enumerate(ims):
        img = cv2.cvtColor(cv2.imread(str(args.images / im["file_name"])), cv2.COLOR_BGR2RGB)
        h, w = img.shape[:2]
        images.append({"id": im["id"], "file_name": im["file_name"], "width": w, "height": h})
        for cls, items in teacher.segment(img, prompts).items():
            for mask, score in items:
                for poly in mask_to_polygons(mask):
                    xs, ys = poly[0::2], poly[1::2]
                    area = float(cv2.contourArea(np.array(poly, np.float32).reshape(-1, 2)))
                    anns.append({"id": aid, "image_id": im["id"], "category_id": CLASS_TO_ID[cls],
                                 "segmentation": [poly], "bbox": [min(xs), min(ys), max(xs) - min(xs),
                                                                  max(ys) - min(ys)],
                                 "area": area, "iscrowd": 0, "score": round(score, 4), "source": "gdino+sam2"})
                    aid += 1
        if k % 20 == 0:
            print(f"  {k + 1}/{len(ims)} anns={len(anns)} {(time.time() - t0) / (k + 1):.2f}s/img", flush=True)
    _dump(args.out, images, anns)
    print(f"완료: images={len(images)} anns={len(anns)} → {args.out}")


if __name__ == "__main__":
    main()
