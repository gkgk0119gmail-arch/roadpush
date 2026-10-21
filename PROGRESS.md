# 진행 기록

자율 개발 루프(10분 체크) 기록. 최신이 위.

## 2026-10-21 (D0) 오후: 실데이터 첫 확인

- Surface_1 해제: 130 XML / 9,558장. **CVAT 1.1 가정이 맞았음** (polygon + `attribute` 자식, z_order 있음). 파일명 중복 없음.
- Surface 라벨에는 장애물이 **전혀 없음**(면 8종만). → 장애물은 Polygon 데이터에서. Surface 이미지 속 차량·화분은 미라벨 → SAM 3로 결측 라벨 보강 후보.
- SAM 3 zero-shot 실사진 3장: 보도 마스크 GT와 거의 일치, GT에 없는 차량·화분도 검출. 골목(alley) 프레임은 GT·SAM 3 모두 "소멸".
- 클래스 변경: `caution_other` → `manhole_grating`(통행 가능, 보도로 합산) + `tree_zone`(통행 불가, 장애물 취급). 20종.
- `data/coco/surface_v1` (train 8,594 / valid 964, 40k 폴리곤).
- **학습 시작**: `seg_m_surface_v1` RF-DETR-Seg Medium, 12 epoch, batch 4, ~7.6분/epoch (tmux `train`).
- 다운로드는 총 대역폭 ~11MB/s 상한 확인 → Polygon 우선(tmux `aihub_p`), Surface_2~5는 그 뒤.
- 테스트 25개 통과.

## 2026-10-21 (D0) 데스크탑 3090

### 환경
- Ubuntu 22.04, RTX 3090. `roadpush` env(torch 2.11+cu128, rfdetr) 생성, `sam3` env는 기존 것 사용(torch 2.13+cu126).
- ROS Humble이 PYTHONPATH에 있어서 모든 명령은 `env -u PYTHONPATH` 로 실행.
- SAM 3 HF 게이트 승인, `sam3.pt`(3.45GB) 다운로드 완료. 토큰은 `.hf_token`(`HF_TOKEN_PATH`).
- 디스크 정리 후 여유 404GB.

### 데이터
- AI Hub 189 승인, aihubshell 설치. `scripts/aihub_fetch.sh` 로 Surface 5 + Polygon 14(약 186GB) 전체 다운로드 시작(tmux `aihub`, ~11MB/s, 4~5시간 예상).
- OSM 신촌 보행 링크 2,269개 / 73.1km → `data/links/sinchon.geojson` (서울 도보네트워크 API 키 없어 OSM 대체).

### 코드
- `links.py`: OSM 링크 추출, `LinkSnapper`(EPSG:5179, 15m 임계).
- `scoring.py`: `analyze_frame`(비율+vanish/repair/stairs 태그), `score_link`(PLAN 7장 산식), 휠체어 프로필.
- `frames.py`: ffmpeg 1fps 추출, GPX 로드·이동평균·보간, frames.csv.
- 테스트 22개 통과.

### 다음
- Surface_1 압축 해제되면 `--inspect` → 변환기 맞추기 → COCO → RF-DETR-Seg Medium 학습(tmux `train`).
- `train.py` / `infer.py` 작성.
