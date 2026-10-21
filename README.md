# RoadPush — 보행공간 단절 위험도 자동 산출 PoC

2026 AI 라이프 솔루션 챌린지(산업통상부·KEIT) 출품작. 아이디어 챌린지 후보작 **RoadPush** 구현.

보행 촬영 영상을 세그멘테이션 모델(RF-DETR-Seg, AI Hub 인도보행 영상으로 파인튜닝)로 분석해
도로 링크별 **유효보행폭 비율**과 단절 위험도를 산출하고, 지자체 담당자가 지도에서 확인·조치 전후를 비교하는 PoC.
대상 지역: 서울 중구 명동·을지로 (Mapillary 공개 보행 사진, CC BY-SA).

- 계획: [PLAN.md](PLAN.md) · 진행 기록: [PROGRESS.md](PROGRESS.md) · 결과 수치: [docs/results.md](docs/results.md)
- 보고서 초안: [docs/report_draft.md](docs/report_draft.md) · 데모 영상 스토리보드: [docs/demo_script.md](docs/demo_script.md)

## 📸 진행 현황 갤러리

그림은 학습·분석이 진행되면 자동으로 다시 그려져 약 90분마다 푸시된다(`scripts/autopush.sh`). 날짜별 상세 기록은 [PROGRESS.md](PROGRESS.md).

**명동 2025 실사진 분석 미리보기** — 보도(초록)·차도(회색)·골목(갈색)·장애물(빨강 윤곽), 오른쪽에 유효보행폭 비율

![명동 미리보기](docs/media/preview_mly_junggu_2025.gif)

**전체 구조** — 분할 모델이 폭을 재고, 규칙이 점수를 매기고, 멀티모달 LLM이 확인·설명한다

![파이프라인](docs/figures/fig_pipeline.png)

**학습 곡선** — 모델별 검증 마스크 mAP

![학습 곡선](docs/figures/fig_training.png)

**zero-shot vs 파인튜닝** — 같은 검증 150장

![성능 비교](docs/figures/fig_compare.png)

**도로 링크별 단절 위험도 (명동 2025)**

<img src="docs/figures/fig_map.png" width="560">

**대표 프레임** — 정상 보도 / 폭 협소 / 보도 소멸

![대표 프레임](docs/figures/fig_frames.png)

## 주요 결과 (AI Hub 검증셋, 촬영 폴더 단위 분리)

| | SAM 3 zero-shot | Grounding DINO+SAM 2 | **RoadPush (파인튜닝)** |
|---|---|---|---|
| 유효보행폭 비율 오차 (150장) | 0.109 | 0.200 | **0.038** |
| 유효보행폭 비율 오차 (954장 전체) | – | – | **0.017** (±0.1 이내 97.0 %) |
| 보도 소멸 판정 F1 (954장) | – | – | **0.915** |

CPU 2스레드 추론 약 0.6초/장(모델 1개). 상세·한계는 `docs/results.md`.

## 파이프라인

```
영상+GPX / Mapillary ─ frames.py · mapillary.py ─▶ frames/*.jpg, frames.csv
                         │
          infer.py (RF-DETR-Seg: 보도면 + 장애물) ─▶ frame_results.jsonl, overlay/
                         │   width_ratio: 스캔라인 병목 비율(통과 여유, 보행자 제외)
                         │   scoring.analyze_frame: 소멸·공사·단차·보차혼용 태그
       aggregate.py + links.py ─▶ links_scored.geojson (점수·등급·단절 유형·공간 유형)
                         │
                  vlm.py (Qwen3-VL) ─▶ links_vlm.json (닫힌 질문 교차검증 + 담당자 메모)
                         │
                  app/app.py ─▶ 지도 · 링크 상세 · 전후 비교 · 업로드 추론 · 방법·출처
```

| 모듈 | 역할 |
|---|---|
| `classes.py` | 20개 클래스 체계(보도면 9 + 장애물 11), AI Hub 라벨 매핑, 통행 가능면·이동 객체 구분 |
| `convert_aihub_to_coco.py` | AI Hub CVAT XML → COCO, 폴더 단위 분할, 희소 클래스 선택 |
| `train.py` / `infer.py` | RF-DETR-Seg 학습 / 다중 체크포인트 추론 |
| `width_ratio.py` | 유효보행폭 비율(병목), 절대폭 보조 지표 |
| `scoring.py` | 프레임 태그, 링크 점수·등급·단절 유형·공간 유형, 일반/휠체어 프로필 |
| `links.py` / `frames.py` / `mapillary.py` | OSM 링크·스냅 / 영상·GPX / 공개 보행 사진 수집 |
| `aggregate.py` / `vlm.py` | 링크 집계 / 멀티모달 LLM 확인·메모·환각 bench |
| `evaluate.py` | 클래스 IoU, 비율 MAE, 소멸 F1 (모델·teacher 공통) |
| `sam3_label.py` / `gdino_label.py` / `merge_coco.py` | zero-shot teacher(SAM 3, GDINO+SAM 2), 결측 라벨 보강 통합 데이터셋 |
| `simulate.py` | AI Hub 연속 프레임을 링크 위에 배치한 시뮬레이션 세션(검증용) |

## 실행

```bash
E="env -u PYTHONPATH"                       # 외부 PYTHONPATH(ROS 등) 차단
bash scripts/setup_env.sh                   # conda env: roadpush, sam3
bash scripts/aihub_fetch.sh                 # AI Hub 189 Surface·Polygon (.aihub_key)
$E python -m roadpush.convert_aihub_to_coco --xml-dir data/raw/aihub/extracted/surface \
   --img-root data/raw/aihub/extracted/surface --out data/coco/surface_v1
$E python -m roadpush.train --dataset data/coco/surface_v1 --run seg_m_surface_v1     # tmux 안에서
$E python -m roadpush.mapillary --area jung_gu --year 2025 --out outputs/mly_junggu_2025   # .mapillary_token
VLM=Qwen/Qwen3-VL-8B-Instruct bash scripts/run_mly_demo.sh <surface.pth> <obstacle.pth>
$E streamlit run app/app.py
$E python scripts/make_figures.py && $E python scripts/build_report.py --pdf    # 그림·성과보고서
```

## 라이선스·출처
코드 Apache-2.0. 학습 데이터 AI Hub 인도보행 영상(이용약관 범위), 거리 사진 © Mapillary contributors (CC BY-SA 4.0),
지도·링크 © OpenStreetMap contributors (ODbL). SAM 3는 라벨링 teacher로만 사용하며 배포물에 포함하지 않음.
