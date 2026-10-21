#!/usr/bin/env bash
# AI Hub 인도보행 영상(189) Surface Masking + Polygon 전체를 파일 단위로 받는다.
# 파일 하나씩: 다운로드 → (aihubshell이 분할 병합) → unzip → zip 삭제 → .done 마커.
# 중단 후 다시 실행하면 .done 이 있는 파일은 건너뛴다.
#
# 사용: echo '<API키>' > .aihub_key && tmux new -s aihub 'bash scripts/aihub_fetch.sh'
#   특정 파일만: bash scripts/aihub_fetch.sh 49954 49959
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD

KEY=${AIHUB_APIKEY:-$(cat .aihub_key 2>/dev/null || true)}
[ -n "$KEY" ] || { echo "API 키 없음: .aihub_key 파일 또는 AIHUB_APIKEY 환경변수"; exit 1; }
AIHUBSHELL=$(command -v aihubshell || echo "$HOME/.local/bin/aihubshell")

SURFACE=(49954 49955 49956 49957 49958)          # Surface_1~5
POLYGON=($(seq 49959 49972))                     # Polygon_1~14_new
if [ $# -gt 0 ]; then KEYS=("$@"); else KEYS=("${SURFACE[@]}" "${POLYGON[@]}"); fi

zips_ok() {   # 모든 zip 이 unzip -t 통과하면 0
  local z
  for z in "$@"; do unzip -tqq "$z" >/dev/null 2>&1 || return 1; done
}

DL=$ROOT/data/raw/aihub/_download
OUT=$ROOT/data/raw/aihub/extracted
mkdir -p "$DL" "$OUT"

for fk in "${KEYS[@]}"; do
  if [ "$fk" -ge 49959 ]; then group=polygon; else group=surface; fi
  done_mark=$OUT/$group/.done_$fk
  [ -e "$done_mark" ] && { echo "[skip] $fk"; continue; }

  work=$DL/$fk
  ok=0
  for attempt in 1 2 3; do
    rm -rf "$work" && mkdir -p "$work"
    echo "== [$(date +%H:%M)] $fk ($group) 다운로드 시도 $attempt =="
    # aihubshell 은 현재 디렉토리 기준으로 tar 해제·병합하므로 파일별 작업 폴더에서 실행
    (cd "$work" && "$AIHUBSHELL" -mode d -datasetkey 189 -filekey "$fk" -aihubapikey "$KEY") || true
    mapfile -t zips < <(find "$work" -type f -name '*.zip')
    # 연결이 끊겨도 aihubshell 은 성공으로 끝낼 때가 있다 → zip 무결성 확인 후 재시도
    if [ ${#zips[@]} -gt 0 ] && zips_ok "${zips[@]}"; then
      ok=1; break
    fi
    echo "   [warn] $fk zip 손상/없음 → 30초 후 재시도"
    sleep 30
  done
  [ $ok -eq 1 ] || { echo "[fail] $fk 3회 실패, 건너뜀"; rm -rf "$work"; continue; }
  mkdir -p "$OUT/$group"
  for z in "${zips[@]}"; do
    echo "   unzip $(basename "$z") ($(du -h "$z" | cut -f1))"
    # AI Hub zip은 내부 파일명이 CP949인 경우가 있다
    unzip -q -o -O cp949 "$z" -d "$OUT/$group"
  done
  rm -rf "$work"
  touch "$done_mark"
  df -h "$ROOT" | tail -1
done
echo "완료: $OUT"
