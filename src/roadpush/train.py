"""RF-DETR-Seg 파인튜닝 (Apache 2.0, 배포 모델).

데이터는 convert_aihub_to_coco 가 만든 RF-DETR(Roboflow) 레이아웃:
    <dataset>/train/_annotations.coco.json, <dataset>/valid/_annotations.coco.json

반드시 tmux 안에서:
    tmux new -s train
    env -u PYTHONPATH python -m roadpush.train --dataset data/coco/aihub_v1 --run seg_m_v1
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

MODELS = {
    "nano": "RFDETRSegNano",
    "small": "RFDETRSegSmall",
    "medium": "RFDETRSegMedium",
    "large": "RFDETRSegLarge",
}


def load_model(size: str, weights: str | None = None, **kw):
    import rfdetr

    cls = getattr(rfdetr, MODELS[size])
    return cls(pretrain_weights=weights, **kw) if weights else cls(**kw)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", required=True, type=Path)
    ap.add_argument("--run", required=True, help="checkpoints/<run> 에 저장")
    ap.add_argument("--model", choices=sorted(MODELS), default="medium")
    ap.add_argument("--weights", default=None, help="이어서 파인튜닝할 체크포인트(.pth)")
    ap.add_argument("--resume", default=None, help="중단된 학습 재개용 checkpoint.pth")
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--batch", default="auto", help="정수 또는 auto")
    ap.add_argument("--grad-accum", type=int, default=1)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--patience", type=int, default=5)
    ap.add_argument("--eval-interval", type=int, default=2)
    ap.add_argument("--full-res-eval", action="store_true",
                    help="학습 중 검증을 원본 해상도로 (1080p에서 매우 느림). 기본은 마스크 헤드 해상도 → 최종 지표는 evaluate.py")
    args = ap.parse_args(argv)

    out = Path("checkpoints") / args.run
    out.mkdir(parents=True, exist_ok=True)
    meta = {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()}
    meta["started"] = datetime.now().isoformat(timespec="seconds")
    (out / "run.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))

    model = load_model(args.model, args.weights)
    batch = args.batch if args.batch == "auto" else int(args.batch)
    model.train(
        dataset_dir=str(args.dataset),
        output_dir=str(out),
        epochs=args.epochs,
        batch_size=batch,
        grad_accum_steps=args.grad_accum,
        lr=args.lr,
        num_workers=args.workers,
        early_stopping=True,
        early_stopping_patience=args.patience,
        checkpoint_interval=1,
        resume=args.resume,
        tensorboard=True,
        eval_interval=args.eval_interval,
        eval_masks_head_resolution=not args.full_res_eval,
        eval_max_dets=100,
        progress_bar="tqdm",
    )
    print("완료:", out)


if __name__ == "__main__":
    main()
