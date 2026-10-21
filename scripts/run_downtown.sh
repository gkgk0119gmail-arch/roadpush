#!/usr/bin/env bash
# 도심 통합 세션: Mapillary 일반+360° 다운로드 종료 대기 → 각각 추론 → 합치기 → 도심 링크 집계 → app/data → 정적 재배포
# 사용: tmux new -d -s downtown "bash scripts/run_downtown.sh 2>&1 | tee outputs/downtown.log"
set -uo pipefail
cd "$(dirname "$0")/.."
R="env -u PYTHONPATH $HOME/miniconda3/envs/roadpush/bin/python"
for t in mly2 mly3; do while tmux has-session -t "=$t" 2>/dev/null; do sleep 60; done; done
CK="checkpoints/seg_m_surface_v1/checkpoint_best_total.pth checkpoints/seg_m_obstacle_v1/checkpoint_best_total.pth"
for r in outputs/mly_downtown_all outputs/mly_downtown_pano; do
  echo "== 추론 $r"; $R -m roadpush.infer --ckpt $CK --run $r --overlay-every 1 2>&1 | grep -v -i warn | tail -1
done
rm -rf outputs/mly_downtown
$R -m roadpush.merge_runs --out outputs/mly_downtown --run p:outputs/mly_downtown_all --run v:outputs/mly_downtown_pano
$R -m roadpush.aggregate --run outputs/mly_downtown --links data/links/downtown.geojson --session mly_downtown
rm -rf app/data/mly_downtown && mkdir -p app/data/mly_downtown
cp outputs/mly_downtown/{links_scored.geojson,frames_linked.csv,attribution.json} app/data/mly_downtown/
cp -rL outputs/mly_downtown/overlay app/data/mly_downtown/
$R - <<'PY'
import geopandas as g
d = g.read_file("app/data/mly_downtown/links_scored.geojson")
print("도심 통합:", len(d), "링크", round(d.length_m.sum() / 1000, 1), "km", d.grade.value_counts().to_dict(), d.space_type.value_counts().to_dict())
PY
bash scripts/redeploy_static.sh
echo "== 도심 세션 배포 완료"
