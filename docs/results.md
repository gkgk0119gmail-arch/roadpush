# 실험 결과 (보고서·발표용 수치 원본)

모든 수치는 AI Hub 인도보행 영상 GT 기준, **폴더(XML) 단위로 분리된 valid** 에서 측정.
원본 JSON: `outputs/teachers/eval_*.json`, `outputs/vlm/*.json`, `outputs/eval/*.json` (gitignored, 재현 스크립트 `outputs/teachers/run.sh`).

## 1. Zero-shot teacher 비교 (2026-10-21)

같은 텍스트 프롬프트(`sam3_label.PROMPTS`), score ≥ 0.5, valid 150장(폴더 고루 샘플).
장애물은 Polygon valid(장애물만 라벨), 면은 Surface valid(면만 라벨)에서 해당 클래스만 평가.

| 지표 | SAM 3 | Grounding DINO-B + SAM 2.1-L |
|---|---|---|
| 장애물 mIoU (11종) | **0.424** | 0.305 |
| car / person | 0.853 / 0.778 | **0.878 / 0.835** |
| truck_bus / two_wheeler | **0.877 / 0.766** | 0.755 / 0.670 |
| bollard / movable_signage / potted_plant | **0.296 / 0.179 / 0.383** | 0.000 / 0.000 / 0.000 |
| pole | **0.504** | 0.208 |
| 면 mIoU (9종) | **0.239** | 0.207 |
| sidewalk | **0.658** | 0.522 |
| manhole_grating / braille | **0.662 / 0.371** | 0.505 / 0.257 |
| 유효보행폭 비율 MAE | **0.088** | 0.193 |
| 비율 오차 ≤ 0.1 | **91.4 %** | 80.8 % |
| 보도 유무 정확도 | **84.7 %** | 73.3 % |
| 보도 소멸 F1 | **0.736** | 0.565 |

해석
- GDINO 는 큰 객체(차량·사람)는 약간 낫지만 **보도 위 소형 장애물(볼라드·입간판·화분)을 전혀 못 찾음** → RoadPush 핵심 대상에서 치명적.
- SAM 3 는 zero-shot 만으로 비율 MAE 0.088. 파인튜닝 RF-DETR 의 목표선.
- 결론: 결측 라벨 보강(B안) teacher = **SAM 3**.
- 공통 약점: roadway(0.07~0.11), alley·repair_zone·tree_zone(≈0) — AI Hub 의 '차도/이면도로' 구분은 텍스트 프롬프트로 재현 어려움 → 파인튜닝 필요성의 근거.

## 2. VLM 환각 (Qwen3-VL, 닫힌 예/아니오 질문)

Polygon valid 40장, GT 면적 ≥ 1500 px² 객체를 '있음'으로.

| 항목 | 2B acc | 2B 오경보율 | 8B acc | 8B 오경보율 |
|---|---|---|---|---|
| car | 0.775 | 0.60 | | |
| truck_bus | 0.975 | 0.03 | | |
| two_wheeler | 0.925 | 0.08 | | |
| person | 0.875 | 0.14 | | |
| bollard | 0.800 | 0.13 | | |
| movable_signage | 0.825 | 0.09 | | |
| construction | 0.900 | 0.08 | | |

열린 질문(나열형)에서는 2B 가 사진과 무관하게 프롬프트 예시를 그대로 나열 → 닫힌 질문 + 세그 교차검증으로 전환.

## 3. RF-DETR-Seg 파인튜닝 (진행 중)

| 모델 | 데이터 | 평가 | 결과 |
|---|---|---|---|
| A안 surface (Medium) | surface_v1 | Surface valid, 면 | |
| A안 obstacle (Medium) | polygon_v1 | Polygon valid, 장애물 | |
| B안 unified (Medium) | unified_v1 (GT + SAM 3 보강) | 양쪽 | |

## 4. 절대폭 보조 지표 (GT 마스크, Surface valid 239장)

카메라 높이 1.3 m 가정, 스캔라인 폭 선형 적합(R² ≥ 0.9)으로 지평선 추정 → W = h·a.
- 보도가 보이는 175장 중 **52장(30%)만 추정 가능**: 보도 위에서 찍으면 하단 행이 화면 좌우 끝까지 차서 잘림.
- 보도 폭 P10/50/90 = 0.79 / 1.48 / 2.35 m, 통과 가능 폭 < 1.2 m 비중 29%.
- AI Hub 촬영 높이 미상이라 값 자체는 참고용. 점수에는 넣지 않고 링크 상세에 보조로만 표시 (제안자 답변: 비율 기본).
