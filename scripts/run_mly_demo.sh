#!/usr/bin/env bash
# Mapillary 실사진 세션(중구 2017·2025) → 추론 → 링크 집계 → (VLM) → app/data 배치.
# 사용: [VLM=Qwen/Qwen3-VL-8B-Instruct] bash scripts/run_mly_demo.sh <ckpt> [<ckpt2> ...]
set -euo pipefail
cd "$(dirname "$0")/.."
[ $# -ge 1 ] || { echo "체크포인트를 1개 이상 주세요"; exit 1; }
PY="env -u PYTHONPATH $HOME/miniconda3/envs/roadpush/bin/python"
LINKS=data/links/jung_gu.geojson

mkdir -p app/data
cp "$LINKS" app/data/links.geojson
for name in ${SESSIONS:-mly_junggu_2017 mly_junggu_2025}; do
  out=outputs/$name
  [ -f "$out/frames.csv" ] || { echo "없음: $out (mapillary.py 먼저)"; continue; }
  $PY -m roadpush.infer --ckpt "$@" --run "$out" --overlay-every 1
  $PY -m roadpush.aggregate --run "$out" --links "$LINKS" --session "$name"
  if [ -n "${VLM:-}" ]; then
    $PY -m roadpush.vlm explain --run "$out" --model "$VLM" --top 25
  fi
  rm -rf "app/data/$name" && mkdir -p "app/data/$name"
  for f in links_scored.geojson frames_linked.csv links_vlm.json attribution.json; do
    if [ -f "$out/$f" ]; then cp "$out/$f" "app/data/$name/"; fi
  done
  cp -r "$out/overlay" "app/data/$name/"
done
echo "완료: app/data  →  env -u PYTHONPATH streamlit run app/app.py"
