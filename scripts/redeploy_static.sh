#!/usr/bin/env bash
# 최종 모델 선택 결과(outputs/model_choice.txt)로 ONNX 재생성 → 정적 사이트 빌드 → HF Space 업로드(비공개 유지).
# 사용: bash scripts/redeploy_static.sh [--wait queue3]
set -euo pipefail
cd "$(dirname "$0")/.."
R="env -u PYTHONPATH $HOME/miniconda3/envs/roadpush/bin/python"
if [ "${1:-}" = "--wait" ]; then
  echo "[$(date +%H:%M)] ${2} 종료 대기"; while tmux has-session -t "=${2}" 2>/dev/null; do sleep 60; done
fi

# 모델 결정: queue2 '선택:' 줄(보도면+장애물 또는 통합 1개), queue3 '보도면 v2 채택: yes' 면 보도면 교체
CHOICE=$(grep -m1 "^선택:" outputs/model_choice.txt 2>/dev/null | sed 's/^선택: //' || true)
[ -n "$CHOICE" ] || CHOICE="checkpoints/seg_m_surface_v1/checkpoint_best_total.pth checkpoints/seg_m_obstacle_v1/checkpoint_best_total.pth"
if grep -q "보도면 v2 채택: yes" outputs/model_choice.txt 2>/dev/null && [ "$(echo $CHOICE | wc -w)" -eq 2 ]; then
  CHOICE="checkpoints/seg_m_surface_v2/checkpoint_best_total.pth $(echo $CHOICE | awk '{print $2}')"
fi
echo "배포 모델: $CHOICE"

rm -rf outputs/onnx/deploy && mkdir -p outputs/onnx/deploy
ONNX=()
i=0
for ck in $CHOICE; do
  CUDA_VISIBLE_DEVICES="" $R - "$ck" "outputs/onnx/deploy/m$i" <<'EOF'
import json, sys
from rfdetr import RFDETRSegMedium
m = RFDETRSegMedium(pretrain_weights=sys.argv[1])
m.export(output_dir=sys.argv[2], format="onnx")
json.dump({"class_names": list(m.class_names), "input": 432}, open("outputs/onnx/meta.json", "w"), ensure_ascii=False)
EOF
  ONNX+=("outputs/onnx/deploy/m$i/rfdetr-seg-medium.onnx"); i=$((i + 1))
done

# FULL=1: (GPU 가 빈 마지막 단계에서) 최종 모델로 도심 세션 재추론 + VLM 8B 메모
if [ "${FULL:-0}" = "1" ] && [ -d outputs/mly_downtown_all ]; then
  for r in outputs/mly_downtown_all outputs/mly_downtown_pano; do
    $R -m roadpush.infer --ckpt $CHOICE --run $r --overlay-every 1 2>&1 | grep -v -i warn | tail -1
  done
  rm -rf outputs/mly_downtown
  $R -m roadpush.merge_runs --out outputs/mly_downtown --run p:outputs/mly_downtown_all --run v:outputs/mly_downtown_pano
  $R -m roadpush.aggregate --run outputs/mly_downtown --links data/links/downtown.geojson --session mly_downtown
  $R -m roadpush.vlm explain --run outputs/mly_downtown --model Qwen/Qwen3-VL-8B-Instruct --top 40 || echo "VLM 실패(계속)"
  rm -rf app/data/mly_downtown && mkdir -p app/data/mly_downtown
  for f in links_scored.geojson frames_linked.csv attribution.json links_vlm.json; do
    if [ -f outputs/mly_downtown/$f ]; then cp outputs/mly_downtown/$f app/data/mly_downtown/; fi
  done
  cp -rL outputs/mly_downtown/overlay app/data/mly_downtown/
fi

SAMPLES=$(ls outputs/mly_junggu_2025/frames | sed -n '85p;200p;400p' | sed 's|^|outputs/mly_junggu_2025/frames/|' | tr '\n' ' ')
SESS=()
if [ -f app/data/mly_downtown/links_scored.geojson ]; then SESS+=(--session "mly_downtown:서울 도심(중구·종로) 전 연도 통합"); fi
SESS+=(--session "mly_junggu_2025:명동 2025" --session "mly_junggu_2017:을지로 2017")
$R scripts/build_static.py --out dist/static "${SESS[@]}" \
   --onnx "${ONNX[@]}" --samples $SAMPLES
$R - <<'EOF'
from huggingface_hub import HfApi
api = HfApi(token=open(".hf_token_write").read().strip())
info = api.upload_folder(folder_path="dist/static", repo_id="YunSangNam/roadpush", repo_type="space",
                         commit_message="RoadPush 정적 웹앱 갱신: 최종 모델·분석 결과", delete_patterns=["data/**", "models/**"])
print(info.commit_url)
EOF
echo "[$(date +%H:%M)] 재배포 완료"
