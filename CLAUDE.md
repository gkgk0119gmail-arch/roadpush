# RoadPush — Claude Code 작업 지침

이 레포는 **2026 AI 라이프 솔루션 챌린지**(산업통상부/KEIT)에 1인 참가하는 프로젝트다.
아이디어 챌린지 후보작 **RoadPush(보행공간 단절 위험도)** 를 AI로 구현한다.
마감 **2026-10-31(토) 24:00** 이메일 접수. 목표 제출일 **2026-10-30(금)**.

## 먼저 읽을 것 (순서대로)
1. `PLAN.md` — 전체 계획, 아키텍처, 10일 일정, 리스크. 모든 결정의 근거.
2. `docs/RoadPush_사전질의답변서_20261012.pdf` — 제안자가 밝힌 전제. 설계가 이것을 따라야 "취지 부합" 점수를 받는다.
3. `docs/공고문_2026_AI라이프솔루션챌린지.pdf` — 제출물, 심사, 제외 사유.
4. `docs/templates/` — 성과보고서(PPT 4p 사용 예정), 참가신청서 양식.

PDF는 `pdftotext -layout <file> -` 로 읽는다.

## 절대 규칙
- **타 대회(ESW, PAC 등) 코드·모델 재사용 금지.** 유사 공모전 제출 코드는 제외 사유다. 모든 코드는 이 레포에서 새로 작성한다.
- **배포 모델은 RF-DETR-Seg(Apache 2.0)만.** SAM 3는 teacher(의사 라벨링, zero-shot 비교)로만 쓰고 웹 데모·배포물에 포함하지 않는다. AGPL(YOLO 등) 라이브러리 사용 금지.
- **판정은 유효보행폭 "비율" 기반**이 기본(제안자 답변). 절대폭 1.2m는 보조 지표.
- **분석 단위는 도로 링크**, 1차 사용자는 **지자체·도로관리기관 담당자**. 개인 경로 안내·주민 제보 기능은 만들지 않는다.
- 사용자에게는 한국어로 답한다. 코드 주석·docstring도 한국어 가능.
- 데이터(영상, AI Hub 원본, 체크포인트)는 커밋하지 않는다. `.gitignore` 유지.

## 환경 (데스크탑, RTX 3090 24GB)
- `scripts/setup_env.sh` 로 conda env 2개 생성:
  - `roadpush` (py3.11): torch cu128, rfdetr, supervision, 앱/GIS 패키지. 학습·추론·앱 전부 여기서.
  - `sam3` (py3.12): facebookresearch/sam3. HF 게이트 승인 후 `hf auth login` 필요.
- 학습은 반드시 `tmux` 세션에서 실행하고 체크포인트를 `checkpoints/<run_name>/` 에 저장.
- Windows라면 WSL2 Ubuntu에서 작업(AI Hub 분할압축 병합, sam3 설치가 Linux 기준).
- 맥(개발용, CUDA 없음)과는 GitHub으로 코드 동기화. 결과물(GeoJSON/JSON/ckpt)은 scp.

## 레포 구조
```
PLAN.md                 계획서(단일 진실 공급원)
docs/                   공고·답변서·양식
scripts/setup_env.sh    환경 세팅
scripts/aihub_download.md  AI Hub 인도보행 영상 다운로드 가이드
src/roadpush/
  classes.py            클래스 체계 + AI Hub 라벨 매핑 (단일 진실 공급원)
  convert_aihub_to_coco.py  AI Hub CVAT XML → COCO(RF-DETR 레이아웃)
  width_ratio.py        프레임별 유효보행폭 비율(핵심 기여)
  (예정) frames.py      영상→1fps 프레임 + GPX 시각 매칭
  (예정) links.py       서울 도보네트워크 링크 추출·스냅
  (예정) scoring.py     링크 점수·단절 유형 분류
  (예정) train.py / infer.py  RF-DETR 학습·추론
  (예정) sam3_label.py  SAM 3 의사 라벨링 (sam3 env)
tests/                  pytest (합성 데이터)
data/raw/aihub/         AI Hub 원본 (gitignored)
data/raw/footage/<YYYYMMDD>_<지역>/  촬영 mp4 + gpx (gitignored)
data/coco/<name>/{train,valid}/_annotations.coco.json  학습 데이터
checkpoints/ outputs/   gitignored
app/                    Streamlit 앱 (HF Spaces 배포)
```

## 데이터 규약
- AI Hub 인도보행 영상(dataSetSn=189): Surface Masking(보도면 폴리곤) + Polygon(장애물 29종 폴리곤)만 사용. Bounding Box·Depth 불필요.
- 라벨 XML은 CVAT 1.1 포맷으로 **가정**하고 변환기를 짰다. 실데이터 받으면 반드시 `python -m roadpush.convert_aihub_to_coco --inspect` 로 라벨·속성 분포를 먼저 확인하고 파서를 맞춘다.
- 클래스 체계는 `src/roadpush/classes.py` 가 유일한 기준. 변경 시 PLAN.md 6장도 갱신.

## 현재 상태 (2026-10-21, 맥에서 작성)
- 뼈대 레포, 계획서, 환경 스크립트, 변환기, 비율 모듈 + 유닛테스트(합성 데이터 통과).
- **실데이터로 검증된 것은 아직 없다.** AI Hub 승인·SAM 3 HF 승인은 사용자가 신청해야 한다.
- 참가신청서 단독 docx는 분실. `docs/templates/성과보고서_양식_Word.docx` 2페이지에 동일 양식이 있고, KEIT 공지(list_no=128385) 첨부에서 재다운로드 가능.

## 다음 할 일 (D0~D1)
1. 데스크탑 OS 확인 → `scripts/setup_env.sh` 실행, `torch.cuda.is_available()` 확인.
2. AI Hub 다운로드 승인 확인 → `scripts/aihub_download.md` 따라 Surface Masking·Polygon 일부 다운로드.
3. `--inspect` 로 XML 확인 → 변환 → `data/coco/aihub_v1`.
4. RF-DETR-Seg Medium 학습 스크립트 작성·실행(tmux).
5. 병행: 서울 도보네트워크 API로 신촌 링크 추출, 프레임·GPX 매칭 코드.
