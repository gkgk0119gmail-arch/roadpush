#!/usr/bin/env bash
# 3차 대기열: queue2 종료 대기 → 보도면 v2(surface_v2, 계단·공사·자전거도로 보강) 학습·평가
# → 비율 MAE 기준으로 보도면 모델 선택 → 바뀌면 실사진 데모+VLM·그림·보고서 재생성 → 중간 체크포인트 정리.
# 사용: tmux new -d -s queue3 "bash scripts/queue3.sh 2>&1 | tee outputs/queue3.log"
set -uo pipefail
cd "$(dirname "$0")/.."
R="env -u PYTHONPATH $HOME/miniconda3/envs/roadpush/bin/python"
step() { echo; echo "===== [$(date +%m-%d\ %H:%M)] $* ====="; }

step "queue2 종료 대기"
while tmux has-session -t =queue2 2>/dev/null; do sleep 60; done

step "보도면 v2 학습 (surface_v2)"
$R -m roadpush.train --dataset data/coco/surface_v2 --run seg_m_surface_v2 --model medium --epochs 8 \
   --batch 4 --grad-accum 4 --workers 8 2>&1 | tee checkpoints/seg_m_surface_v2.log | grep --line-buffered -E "Best|완료|Error"

step "보도면 v2 평가 (비교 고정: surface_v1 valid 전체)"
$R -m roadpush.evaluate --gt data/coco/surface_v1/valid --ckpt checkpoints/seg_m_surface_v2/checkpoint_best_total.pth \
   --classes surface --out outputs/eval/eval_surface_v2_full.json

step "보도면 모델 선택 (비율 MAE 우선, 동률이면 mIoU)"
NEW=$($R - <<'EOF'
import json, pathlib
def j(p):
    p = pathlib.Path(p); return json.loads(p.read_text()) if p.exists() else None
a, b = j("outputs/eval/eval_surface_final_full_v2.json"), j("outputs/eval/eval_surface_v2_full.json")
better = b is not None and a is not None and (b["ratio_mae"] < a["ratio_mae"] - 1e-4 or
          (abs(b["ratio_mae"] - a["ratio_mae"]) <= 1e-4 and b["miou"] > a["miou"]))
print("yes" if better else "no")
EOF
)
echo "보도면 v2 채택: $NEW" | tee -a outputs/model_choice.txt
if [ "$NEW" = "yes" ]; then
  CHOICE=$(tail -n +1 outputs/model_choice.txt | grep -m1 "^선택:" | sed 's/^선택: //')
  OBS=$(echo "$CHOICE" | awk '{print $NF}')
  case "$OBS" in *obstacle*) ;; *) OBS=checkpoints/seg_m_obstacle_v1/checkpoint_best_total.pth;; esac
  step "실사진 데모 재생성 (보도면 v2 + $OBS)"
  VLM=Qwen/Qwen3-VL-8B-Instruct bash scripts/run_mly_demo.sh checkpoints/seg_m_surface_v2/checkpoint_best_total.pth "$OBS"
  $R scripts/make_figures.py
  $R scripts/make_preview.py --session outputs/mly_junggu_2025 --title "명동 2025"
  $R scripts/build_report.py --pdf
fi

step "중간 체크포인트 정리 (best·last 가중치만 유지)"
for d in checkpoints/seg_m_*/; do rm -f "$d"checkpoint_[0-9]*.ckpt; done
du -sh checkpoints
step "완료"
