"""RF-DETR-Seg 추론 → 프레임별 유효보행폭 분석.

입력: frames.py 가 만든 <run>/frames/*.jpg (+ frames.csv)
출력: <run>/frame_results.jsonl  (frame, ratio, min_ratio, sidewalk_present, tags, n_obs, 클래스별 개수)
      <run>/overlay/*.jpg          (--overlay-every N 프레임마다 마스크 오버레이)

사용:
    env -u PYTHONPATH python -m roadpush.infer --ckpt checkpoints/seg_m_v1/checkpoint_best_total.pth \
        --run outputs/20261022_sinchon/a
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from .scoring import FrameAnalysis, analyze_frame
from .train import load_model

# 클래스별 오버레이 색 (BGR 아님, RGB)
PALETTE = {
    "sidewalk": (60, 180, 75), "braille_guide_blocks": (255, 225, 25), "roadway": (128, 128, 128),
    "alley": (170, 110, 40), "bike_lane": (0, 130, 200), "stairs": (145, 30, 180),
    "repair_zone": (245, 130, 48), "manhole_grating": (70, 240, 240), "tree_zone": (128, 0, 0),
}
OBSTACLE_RGB = (230, 25, 75)


class Predictor:
    """체크포인트 하나(통합 모델) 또는 여러 개(보도면 모델 + 장애물 모델)를 받아 결과를 합친다."""

    def __init__(self, ckpt: str | Path | list, size: str = "medium", threshold: float = 0.4):
        ckpts = ckpt if isinstance(ckpt, (list, tuple)) else [ckpt]
        self.models = [load_model(size, str(c)) for c in ckpts]
        self.threshold = threshold
        for m in self.models:
            try:
                m.optimize_for_inference()
            except Exception:   # CPU/구버전에서 실패해도 추론은 가능
                pass

    def masks(self, image) -> tuple[dict[str, list[np.ndarray]], tuple[int, int], list]:
        out: dict[str, list[np.ndarray]] = defaultdict(list)
        dets, shape = [], None
        for model in self.models:
            det = model.predict(image, threshold=self.threshold)
            names = list(model.class_names)
            if det.mask is not None and len(det):
                shape = det.mask.shape[1:]
                for cid, m in zip(det.class_id, det.mask):
                    out[names[int(cid)]].append(m.astype(bool))
            dets.append(det)
        return dict(out), shape or _shape_of(image), dets

    def analyze(self, image) -> tuple[FrameAnalysis, dict[str, list[np.ndarray]], object]:
        cm, shape, det = self.masks(image)
        return analyze_frame(cm, shape), cm, det


def _shape_of(image) -> tuple[int, int]:
    if isinstance(image, np.ndarray):
        return image.shape[:2]
    from PIL import Image
    im = Image.open(image) if isinstance(image, (str, Path)) else image
    return im.size[1], im.size[0]


def render_overlay(image_rgb: np.ndarray, class_masks: dict[str, list[np.ndarray]], fa: FrameAnalysis,
                   alpha: float = 0.45) -> np.ndarray:
    """마스크 + 스캔라인 비율 텍스트 오버레이 (RGB)."""
    import cv2

    out = image_rgb.copy()
    layer = out.copy()
    for cls, ms in class_masks.items():
        color = PALETTE.get(cls, OBSTACLE_RGB)
        for m in ms:
            layer[m] = color
    out = cv2.addWeighted(layer, alpha, out, 1 - alpha, 0)
    for cls, ms in class_masks.items():
        if cls in PALETTE:
            continue
        for m in ms:
            cnts, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(out, cnts, -1, OBSTACLE_RGB, 2)
    label = f"ratio {fa.ratio:.2f}" + (f"  [{','.join(fa.tags)}]" if fa.tags else "")
    cv2.rectangle(out, (0, 0), (12 + 18 * len(label), 44), (0, 0, 0), -1)
    cv2.putText(out, label, (8, 32), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2, cv2.LINE_AA)
    return out


def run_frames(pred: Predictor, run_dir: Path, overlay_every: int = 10) -> Path:
    from PIL import Image

    frames = sorted((run_dir / "frames").glob("*.jpg"))
    ov_dir = run_dir / "overlay"
    ov_dir.mkdir(parents=True, exist_ok=True)
    out = run_dir / "frame_results.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for i, fp in enumerate(frames):
            img = np.asarray(Image.open(fp).convert("RGB"))
            fa, cm, _ = pred.analyze(img)
            rec = {"frame": fp.name, **fa.to_dict(), "counts": {k: len(v) for k, v in cm.items()}}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if overlay_every and i % overlay_every == 0:
                ov = Image.fromarray(render_overlay(img, cm, fa))
                if ov.width > 960:    # 대시보드·배포 용량용 축소
                    ov = ov.resize((960, round(ov.height * 960 / ov.width)))
                ov.save(ov_dir / fp.name, quality=80)
            if i % 50 == 0:
                print(f"  {i}/{len(frames)} {fp.name} ratio={fa.ratio:.2f} tags={fa.tags}")
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ckpt", required=True, nargs="+", help="하나(통합) 또는 여러 개(보도면+장애물)")
    ap.add_argument("--size", default="medium")
    ap.add_argument("--run", required=True, type=Path, help="frames/ 가 있는 출력 폴더")
    ap.add_argument("--threshold", type=float, default=0.4)
    ap.add_argument("--overlay-every", type=int, default=10)
    args = ap.parse_args(argv)
    pred = Predictor(args.ckpt, args.size, args.threshold)
    print("→", run_frames(pred, args.run, args.overlay_every))


if __name__ == "__main__":
    main()
