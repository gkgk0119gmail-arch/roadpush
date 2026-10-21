#!/usr/bin/env bash
# 시뮬레이션 데모 2세션(같은 경로, 다른 장면) 생성 → 추론 → 링크 집계 → app/data 에 배치.
# 사용: bash scripts/run_sim_demo.sh <ckpt> [<ckpt2> ...]
#   예: bash scripts/run_sim_demo.sh checkpoints/seg_m_surface_v1/checkpoint_best_total.pth \
#                                    checkpoints/seg_m_obstacle_v1/checkpoint_best_total.pth
set -euo pipefail
cd "$(dirname "$0")/.."
[ $# -ge 1 ] || { echo "체크포인트를 1개 이상 주세요"; exit 1; }
PY="env -u PYTHONPATH $HOME/miniconda3/envs/roadpush/bin/python"
LINKS=data/links/sinchon.geojson
SRC=${SIM_SRC:-data/raw/aihub/extracted/surface}
HOLD=${SIM_HOLDOUT:-data/coco/surface_v1/valid/_annotations.coco.json}

mkdir -p app/data
cp "$LINKS" app/data/links.geojson
for spec in "sim_aihub_1:0" "sim_aihub_2:1"; do
  name=${spec%%:*}; seed=${spec##*:}
  out=outputs/$name
  rm -rf "$out"
  $PY -m roadpush.simulate --src "$SRC" --links "$LINKS" --out "$out" --folders 10 \
      --seed "$seed" --route-seed 7 --holdout-coco "$HOLD"
  $PY -m roadpush.infer --ckpt "$@" --run "$out" --overlay-every 1
  $PY -m roadpush.aggregate --run "$out" --links "$LINKS" --session "$name"
  rm -rf "app/data/$name" && mkdir -p "app/data/$name"
  cp "$out/links_scored.geojson" "$out/frames_linked.csv" "app/data/$name/"
  cp -r "$out/overlay" "app/data/$name/"
done
echo "완료: app/data  →  env -u PYTHONPATH streamlit run app/app.py"
