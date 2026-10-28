#!/usr/bin/env bash
# 데모 영상 v2: 앞 훅(장면 3컷 + 제목) + 인포그래픽 2장 + 웹앱 녹화(record_demo.py 결과에서 잘라냄) + 성과·엔딩 카드
# 입력: outputs/video/RoadPush_demo.mp4 (record_demo.py, v1), outputs/media/{img,vc,out}  출력: docs/media/RoadPush_demo.mp4
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
M=$ROOT/outputs/media; O=$M/seg; SRC=$ROOT/outputs/video/RoadPush_demo.mp4
[ -f "$SRC" ] || { echo "먼저 python scripts/record_demo.py 로 $SRC 를 만드세요"; exit 1; }
mkdir -p "$O"
ENC="-c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -r 30 -an"
hook(){ # 이름 사진 길이(초): 사진은 천천히 확대, 글자 오버레이는 고정
  local d=$3; local n; n=$(python3 -c "print(int($d*30))")
  ffmpeg -v error -y -loop 1 -i "$M/img/$2.jpg" -loop 1 -i "$M/vc/$1.png" -filter_complex \
   "[0]scale=1280:-2,crop=1280:720:0:(ih-720)*0.55,scale=2560:1440,zoompan=z='1+0.06*on/$n':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1280x720:fps=30[bg];[bg][1]overlay=0:0,trim=duration=$d" \
   -t "$d" $ENC "$O/$1.mp4"; }
still(){ # png 길이 출력
  ffmpeg -v error -y -loop 1 -i "$1" -vf "scale=1280:720,fade=t=in:st=0:d=0.35,fade=t=out:st=$(python3 -c "print($2-0.35)"):d=0.35" -t "$2" $ENC "$3"; }
hook h1 b_BL 3.5; hook h2 f_1 3.5; hook h3 b_TR 3.5
still "$M/vc/t.png" 4.5 "$O/t.mp4"
still "$M/out/summary.png" 9 "$O/sum.mp4"
still "$M/out/how.png" 10 "$O/how.mp4"
# v1 구성: 카드 4장 37초 → 웹앱 녹화·명동 걷기 → 성과·출처 18초. 로딩 1초 제외하고 38.0초부터
end=$(python3 -c "import subprocess as s;print(float(s.run(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0','$SRC'],capture_output=True,text=True).stdout)-18)")
ffmpeg -v error -y -ss 38.0 -to "$end" -i "$SRC" -vf "fade=t=in:st=0:d=0.3" $ENC "$O/app.mp4"
still "$M/vc/r.png" 9 "$O/r.mp4"
still "$M/vc/e.png" 8 "$O/e.mp4"
printf "file '%s'\n" "$O"/h1.mp4 "$O"/h2.mp4 "$O"/h3.mp4 "$O"/t.mp4 "$O"/sum.mp4 "$O"/how.mp4 "$O"/app.mp4 "$O"/r.mp4 "$O"/e.mp4 > "$O/list.txt"
ffmpeg -v error -y -f concat -safe 0 -i "$O/list.txt" -c:v libx264 -preset veryfast -crf 21 -pix_fmt yuv420p -movflags +faststart -an "$ROOT/docs/media/RoadPush_demo.mp4"
ffprobe -v error -show_entries format=duration,size -of compact "$ROOT/docs/media/RoadPush_demo.mp4"
