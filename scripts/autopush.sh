#!/usr/bin/env bash
# 주기적 진행 스냅샷: 그림·학습 곡선·미리보기 GIF 재생성 → 해당 파일만 커밋 → 푸시.
# 사용: tmux new -d -s autopush "bash scripts/autopush.sh 5400"   (초 단위 간격, 기본 90분)
set -uo pipefail
cd "$(dirname "$0")/.."
INTERVAL=${1:-5400}
R="env -u PYTHONPATH $HOME/miniconda3/envs/roadpush/bin/python"
while true; do
  echo "== [$(date +%m-%d\ %H:%M)] 스냅샷"
  $R scripts/make_figures.py >/dev/null 2>&1 || echo "  그림 실패"
  if [ -f outputs/mly_junggu_2025/frame_results.jsonl ]; then
    $R scripts/make_preview.py --session outputs/mly_junggu_2025 --title "명동 2025" >/dev/null 2>&1 || echo "  미리보기 실패"
  fi
  git add docs/figures docs/media
  if ! git diff --cached --quiet; then
    git commit -q -m "진행 스냅샷 $(date +%m-%d\ %H:%M): 그림·학습 곡선·미리보기 갱신

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" && git push -q && echo "  푸시 완료"
  else
    echo "  변경 없음"
  fi
  sleep "$INTERVAL"
done
