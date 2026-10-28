#!/usr/bin/env bash
# 인포그래픽 3장 → 영상 v2 → KEIT 양식 성과보고서(PPTX·PDF)
# 필요: playwright(chromium), ffmpeg, python-pptx, LibreOffice, 폰트 Noto Sans CJK KR·Pretendard
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
M=outputs/media; mkdir -p $M/out $M/vc
python3 scripts/media/crop_scenes.py
cp scripts/media/info.html scripts/media/video.html $M/            # html 은 img/ 상대 경로
python3 scripts/media/render.py $M/info.html $M/out 1920 1080 summary,types,how
python3 scripts/media/render.py $M/video.html $M/vc 1280 720 h1,h2,h3 alpha
python3 scripts/media/render.py $M/video.html $M/vc 1280 720 t,r,e
for n in summary types how; do cp $M/out/$n.png docs/figures/infographic_$n.png; done
bash scripts/media/build_video.sh
python3 scripts/media/build_report_keit.py
soffice --headless --convert-to pdf --outdir docs/report docs/report/RoadPush_성과보고서.pptx >/dev/null
ls -la docs/report docs/figures/infographic_*.png docs/media/RoadPush_demo.mp4
