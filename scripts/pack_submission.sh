#!/usr/bin/env bash
# 제출 첨부 묶음 생성: dist/submission/
set -euo pipefail
cd "$(dirname "$0")/.."
R="env -u PYTHONPATH $HOME/miniconda3/envs/roadpush/bin/python"
$R scripts/build_report.py --pdf >/dev/null
$R scripts/build_dataset_summary.py >/dev/null
out=dist/submission; rm -rf "$out"; mkdir -p "$out"
cp dist/RoadPush_성과보고서.pptx dist/RoadPush_성과보고서.pdf dist/RoadPush_데이터셋요약.pdf "$out/"
cp docs/media/RoadPush_demo.mp4 "$out/"
if ls docs/참가신청서* >/dev/null 2>&1; then cp docs/참가신청서* "$out/"; else echo "⚠ 참가신청서 없음 — docs/ 에 서명본을 두면 같이 묶임"; fi
ls -la "$out"; du -sh "$out"
