#!/usr/bin/env bash
# 야간 GPU 대기열: 장애물 학습 종료 대기 → 평가 → 실사진 데모(+VLM 8B) → VLM bench → SAM 3 의사 라벨
# → 통합 데이터셋 → 통합 모델 학습 → 평가. 각 단계 실패해도 다음 단계는 계속(로그 확인).
# 사용: tmux new -d -s queue "bash scripts/night_queue.sh 2>&1 | tee outputs/night_queue.log"
set -uo pipefail
cd "$(dirname "$0")/.."
R="env -u PYTHONPATH $HOME/miniconda3/envs/roadpush/bin/python"
S="env -u PYTHONPATH $HOME/miniconda3/envs/sam3/bin/python"
VLM8=Qwen/Qwen3-VL-8B-Instruct
step() { echo; echo "===== [$(date +%m-%d\ %H:%M)] $* ====="; }

step "장애물 학습 종료 대기"
while tmux has-session -t =train 2>/dev/null; do sleep 60; done
SURF=checkpoints/seg_m_surface_v1/checkpoint_best_total.pth
OBS=checkpoints/seg_m_obstacle_v1/checkpoint_best_total.pth
[ -f "$OBS" ] || OBS=checkpoints/seg_m_obstacle_v1/checkpoint_best_ema.pth

step "장애물 모델 평가 (Polygon valid 전체)"
$R -m roadpush.evaluate --gt data/coco/polygon_v1/valid --ckpt "$OBS" --classes obstacle \
   --out outputs/eval/eval_obstacle_final_full.json

step "실사진 데모 (명동 2025·을지로 2017) + VLM 8B 메모"
VLM=$VLM8 bash scripts/run_mly_demo.sh "$SURF" "$OBS"

step "VLM 8B 환각률 bench (Polygon valid 200장)"
$R -m roadpush.vlm bench --gt data/coco/polygon_v1/valid --max-images 200 --model $VLM8 \
   --out outputs/vlm/bench_8b_polygon200.json
$R -m roadpush.vlm bench --gt data/coco/polygon_v1/valid --max-images 200 --model Qwen/Qwen3-VL-2B-Instruct \
   --out outputs/vlm/bench_2b_polygon200.json

step "SAM 3 의사 라벨: Polygon train → 면 7종"
$S src/roadpush/sam3_label.py --images data/coco/polygon_v1/train --out outputs/sam3/polygon_train_surface.coco.json \
   --classes sidewalk,braille_guide_blocks,roadway,bike_lane,stairs,manhole_grating,tree_zone
step "SAM 3 의사 라벨: Surface train → 장애물 9종"
$S src/roadpush/sam3_label.py --images data/coco/surface_v1/train --out outputs/sam3/surface_train_obstacle.coco.json \
   --classes car,truck_bus,two_wheeler,bollard,pole,barricade,movable_signage,potted_plant,person

step "통합 데이터셋 (GT + SAM 3 결측 보강)"
rm -rf data/coco/unified_v1
$R -m roadpush.merge_coco --out data/coco/unified_v1 \
   --src data/coco/surface_v1:outputs/sam3/surface_train_obstacle.coco.json \
   --src data/coco/polygon_v1:outputs/sam3/polygon_train_surface.coco.json --pseudo-score 0.5

step "통합 모델 학습 (B안)"
$R -m roadpush.train --dataset data/coco/unified_v1 --run seg_m_unified_v1 --model medium --epochs 10 \
   --batch 4 --grad-accum 4 --workers 8 2>&1 | tee checkpoints/seg_m_unified_v1.log | grep --line-buffered -E "Best|완료|Error"
UNI=checkpoints/seg_m_unified_v1/checkpoint_best_total.pth

step "통합 모델 평가 (A안과 같은 GT)"
$R -m roadpush.evaluate --gt data/coco/surface_v1/valid --ckpt "$UNI" --classes surface --out outputs/eval/eval_unified_surface_full.json
$R -m roadpush.evaluate --gt data/coco/polygon_v1/valid --ckpt "$UNI" --classes obstacle --out outputs/eval/eval_unified_obstacle_full.json
step "완료"
