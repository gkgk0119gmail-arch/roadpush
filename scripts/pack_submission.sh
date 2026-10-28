#!/usr/bin/env bash
# 제출 첨부 묶음 생성: dist/submission/
set -euo pipefail
cd "$(dirname "$0")/.."
R="env -u PYTHONPATH $HOME/miniconda3/envs/roadpush/bin/python"
# 성과보고서는 scripts/media/build_media.sh 결과(docs/report/)를 사용
$R scripts/build_dataset_summary.py >/dev/null
out=dist/submission; rm -rf "$out"; mkdir -p "$out"
cp docs/report/RoadPush_성과보고서.pptx docs/report/RoadPush_성과보고서.pdf dist/RoadPush_데이터셋요약.pdf dist/RoadPush_데이터셋요약.docx "$out/"
cp docs/media/RoadPush_demo.mp4 "$out/"
if ls docs/참가신청서* >/dev/null 2>&1; then cp docs/참가신청서* "$out/"; else echo "⚠ 참가신청서 없음 — docs/ 에 서명본을 두면 같이 묶임"; fi
ls -la "$out"; du -sh "$out"
