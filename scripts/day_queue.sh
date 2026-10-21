#!/usr/bin/env bash
# 2차 대기열: 야간 대기열(queue) 종료 대기 → 장애물 v2(polygon_v2, 희소 클래스 보강) 학습·평가
# → 장애물 v1/v2 및 통합 모델 중 최선 조합 선택 → 실사진 데모 + VLM 8B 재생성 → 그림·보고서 재생성.
# 사용: tmux new -d -s queue2 "bash scripts/day_queue.sh 2>&1 | tee outputs/day_queue.log"
set -uo pipefail
cd "$(dirname "$0")/.."
R="env -u PYTHONPATH $HOME/miniconda3/envs/roadpush/bin/python"
step() { echo; echo "===== [$(date +%m-%d\ %H:%M)] $* ====="; }

step "야간 대기열 종료 대기"
while tmux has-session -t =queue 2>/dev/null; do sleep 60; done

step "장애물 v2 학습 (polygon_v2)"
$R -m roadpush.train --dataset data/coco/polygon_v2 --run seg_m_obstacle_v2 --model medium --epochs 8 \
   --batch 4 --grad-accum 4 --workers 8 2>&1 | tee checkpoints/seg_m_obstacle_v2.log | grep --line-buffered -E "Best|완료|Error"

step "장애물 v2 평가 (비교 고정: polygon_v1 valid)"
$R -m roadpush.evaluate --gt data/coco/polygon_v1/valid --ckpt checkpoints/seg_m_obstacle_v2/checkpoint_best_total.pth \
   --classes obstacle --out outputs/eval/eval_obstacle_v2_full.json

step "최선 조합 선택"
CHOICE=$($R - <<'EOF'
import json, pathlib
def m(p):
    p = pathlib.Path(p); return json.loads(p.read_text())["miou"] if p.exists() else -1
obs = {"checkpoints/seg_m_obstacle_v1/checkpoint_best_total.pth": m("outputs/eval/eval_obstacle_final_full.json"),
       "checkpoints/seg_m_obstacle_v2/checkpoint_best_total.pth": m("outputs/eval/eval_obstacle_v2_full.json")}
best_obs = max(obs, key=obs.get)
# 통합(B안)이 보도면·장애물 모두 A안 이상이면 단일 모델 사용
us, uo = m("outputs/eval/eval_unified_surface_full.json"), m("outputs/eval/eval_unified_obstacle_full.json")
ss = m("outputs/eval/eval_surface_final_full_v2.json")
if us >= ss and uo >= obs[best_obs]:
    print("checkpoints/seg_m_unified_v1/checkpoint_best_total.pth")
else:
    print("checkpoints/seg_m_surface_v1/checkpoint_best_total.pth " + best_obs)
EOF
)
echo "선택: $CHOICE" | tee outputs/model_choice.txt

step "실사진 데모 + VLM 8B 재생성"
VLM=Qwen/Qwen3-VL-8B-Instruct bash scripts/run_mly_demo.sh $CHOICE

step "그림·보고서 재생성"
$R scripts/make_figures.py
$R scripts/build_report.py --pdf
step "완료"
