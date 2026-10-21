# AI Hub 인도보행 영상 다운로드 가이드

데이터셋: https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=189 (인도보행 영상, v1.1)

## 1. 승인 (사용자가 직접)
1. AI Hub 로그인(내국인 실명인증 필요) → 데이터셋 페이지 → **다운로드 신청**.
2. 승인되면 마이페이지에서 **API 키** 발급 (aihubshell 사용에 필요).
3. 승인 전까지는 "샘플(경량)" 데이터로 변환기·파이프라인 테스트.

## 2. aihubshell 설치 (Linux / WSL2)
```bash
curl -o aihubshell https://api.aihub.or.kr/api/aihubshell.do
chmod +x aihubshell && sudo mv aihubshell /usr/local/bin/
aihubshell -help
```
(명령 옵션은 버전에 따라 다르다. `-help` 출력과 AI Hub "다운로드 가이드" 페이지를 우선한다.)

## 3. 파일 목록 → 필요한 것만 받기
```bash
# 파일 트리 + filekey 확인
aihubshell -mode l -datasetkey 189
# 선택 다운로드 (filekey는 위 출력에서 복사, 쉼표 구분)
aihubshell -mode d -datasetkey 189 -filekey <키1>,<키2> -aihubapikey <API키>
```
우선순위:
1. **Surface Masking** (보도면 폴리곤, 5만) — 보도/점자블록/차도/이면도로/자전거도로/주의구역
2. **Polygon** (장애물 29종 폴리곤, 10만)
3. Bounding Box, Depth — 받지 않음

Medium 학습 기준 각 5천~1만 장이면 충분. 한 번에 전체를 받지 말고 폴더 단위로.

## 4. 분할 압축 병합
AI Hub는 큰 zip을 `*.part0`, `*.part1`... 로 나눠 준다.
```bash
cd data/raw/aihub/<폴더>
find . -type f -name "*.part*" | sort -V | xargs cat > merged.zip
ls -l merged.zip   # 0 byte면 실패
unzip -q merged.zip -d extracted && rm merged.zip
```

## 5. 변환
```bash
# 라벨/속성 분포 먼저 확인 (XML 포맷 검증)
python -m roadpush.convert_aihub_to_coco --xml-dir data/raw/aihub --img-root data/raw/aihub --inspect
# 변환 (이미지는 symlink)
python -m roadpush.convert_aihub_to_coco --xml-dir data/raw/aihub --img-root data/raw/aihub \
    --out data/coco/aihub_v1 --val-ratio 0.1 --link symlink
```
결과: `data/coco/aihub_v1/{train,valid}/_annotations.coco.json` + 이미지 → RF-DETR `train(dataset_dir="data/coco/aihub_v1")` 에 바로 사용.

## 라이선스 메모
AI Hub 이용약관 준수(출처 표기, 재배포 금지). 성과보고서·README에 "AI Hub 인도보행 영상 데이터 활용" 명시.
