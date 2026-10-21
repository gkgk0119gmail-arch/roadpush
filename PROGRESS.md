# 진행 기록

자율 개발 루프(10분 체크) 기록. 최신이 위.

## 2026-10-21 (D0) 18시 40분: AI Hub 다운로드 완료, 보도면 v2 계획

- AI Hub 189 **전체 다운로드 완료**: Polygon 14 + Surface 5 (zip 무결성 검사 통과). Surface 전체 46,399장: stairs 1,485(Surface_1 대비 8배)·repair_zone 207·bike_lane 3,585.
- **surface_v2** = surface_v1 + 희소 면(계단·공사·자전거도로) 포함 이미지 → train 11,676 / valid 1,248, v1 valid 누수 0.
- 끝난 학습의 epoch 중간 체크포인트 삭제(11 GB 확보, best·last 가중치 유지).
- 대기열 3단: `queue`(SAM 3 의사 라벨→통합 학습) → `queue2`(장애물 v2→최선 조합→데모·보고서) → `queue3`(보도면 v2→비율 MAE 우선 선택→바뀌면 데모·보고서 재생성→체크포인트 정리).

## 2026-10-21 (D0) 18시 20분: VLM bench, SAM 3 의사 라벨 품질 점검

- VLM bench 200장: 평균 acc 2B 0.886 / 8B 0.895. 8B 도 car 오경보 29%·person 14%, 소형 객체 재현율 ~50% → 단독 판정 불가, 교차검증 설계 근거(`docs/results.md` 2절).
- SAM 3 의사 라벨(Polygon train → 면, 진행 중 0.52 s/img) 표본 6장 육안 점검: 보도·블록 보도·횡단보도(차도) 양호. **알려진 공백: alley(이면도로)는 프롬프트에 없어 Polygon 쪽에서 미라벨 → 통합 모델 alley 성능 저하 가능** → 평가에서 alley IoU 확인, 저하 시 A안(전문 모델 결합) 유지(queue2 자동 선택 로직과 일치).

## 2026-10-21 (D0) 18시: 최종 모델 실사진 결과·오판 수정

- 최종 보도면+장애물 모델로 실사진 재분석. 대표 프레임 검토 중 넓은 명동 광장이 비율 0.07 → 원인: 지평선 부근에서 사람에 가려 조각난 보도 옆 **차도 위 트럭이 corridor 로 선택**됨. → corridor 내 보도 비중 25% 미만 행은 판단 제외. 이후 '폭 협소 0.16' 은 보행자 거리 한가운데 진입 차량(정답). AI Hub GT 지표 불변(면 GT 에 장애물 없음).
- 오버레이: 보행자 등 이동 객체 연보라(장애물 빨강과 구분).
- **명동 2025**: 24링크 안전 19·주의 4·위험 1, 보차 혼용 13. **을지로 2017**: 68링크 위험 24(공구상가 골목 보도 소멸)·주의 11·안전 33.
- 8B 메모 예(명동8나길): "보도블록 위에 백색 트럭이 정차해 보행 공간을 차지… 골목 폭이 좁아 혼용" → 보행자 우선도로 지정·통행 시간제. seg–VLM 일치율 0.85.

## 2026-10-21 (D0) 17시 40분: 장애물 모델 완료, 야간 대기열 시작

- `seg_m_obstacle_v1` 완료(17:24). **Polygon valid 1,566장 mIoU 0.736** (car 0.91, person 0.87 … barricade 0.61, other_moving 0.58). 학습 중 지표 0.27 은 마스크 헤드 저해상도라 원해상도 평가와 큰 차이.
- 공정 비교(같은 150장·프롬프트 9종): **RF-DETR 0.701 vs SAM 3 0.518 vs GDINO 0.373**.
- 야간 대기열 진행: 실사진 데모 + Qwen3-VL-8B 메모 생성 중. 8B 메모 예: "좁은 골목 양쪽에 상점과 상자, 수레 등이 배치되어 보행로가 사실상 소멸" — 2B 대비 사진 근거 구체성 크게 향상.
- README 진행 갤러리(미리보기 GIF·학습 곡선 등) + tmux `autopush` 90분 스냅샷 푸시(사용자 요청).

## 2026-10-21 (D0) 16시 20분: 보고서 PPT 자동화, 희소 클래스 보강 데이터

- `scripts/build_report.py`: 공식 PPT 양식 4p에 문안·그림·평가 JSON 수치 자동 삽입 + PDF. Pretendard 폰트 로컬 설치(OFL)로 미리보기 확인. 최종 수치 나오면 재실행.
- `make_figures.py`: 파이프라인 도식 추가(SAM 3=학습 teacher, Qwen3-VL=메모 사전 생성 구분).
- 앱 '방법·출처' 탭.
- 장애물 희소 클래스: 받은 Polygon 1~10(1,270폴더) 전체에 barricade 3,519·other_moving 1,744·potted_plant 6,470·movable_signage 14,143 (Polygon_1 대비 3~7배).
  → `--select-classes` 로 희소 클래스 포함 이미지만 뽑아 **polygon_v2** (train 21,869 / valid 2,477, 폴더 분할 유지, v1 valid 와 누수 0). merge_coco 파일명 중복 제거.
- **다음(내일)**: 야간 대기열 종료 후 polygon_v2 로 장애물 모델 v2 학습(~3h), 비교 평가는 polygon_v1 valid 로 고정.

## 2026-10-21 (D0) 15시 50분: 비율 v2(병목), 보차 혼용, 야간 대기열

- 사용자 지적: 명동처럼 보도블록이지만 차가 다니는 곳 → **보차 혼용** 판정 추가: 보행 공간 안 차량 프레임 비중 + OSM 도로 유형(residential 등은 15%, 그 외 30%) → 링크 `space_type`(분리 보도/보차 혼용/보도 없음), 단절 유형 'shared', VLM 확인 질문·조치 메뉴.
- 장애물 ep1(0.247) 붙여 명동 실행 → 장애물 66% 프레임인데 비율 1.00 → **비율 v2**: 최저 2줄 평균(병목) + 장애물 좌우 1% 통과 여유(마스크 틈 메움). 재평가 MAE 0.017(954장), 150장 0.038 vs SAM 3 0.109.
- 명동 2025: 안전 17·주의 6·위험 1, 보차 혼용 11(명동길·명동8나길·명동9·10길). 퇴계로 '혼용' 의심 → 최종 장애물 모델로 재확인.
- VLM 2B 메모(실사진): 동작·일치율 0.889이나 문장 반복·어색 → 8B 로 생성 예정.
- 보고서 그림 스크립트(`make_figures.py`): 비교 패널·위험도 지도·대표 프레임. 등급색 = 상태 팔레트.
- **야간 대기열** tmux `queue` (`scripts/night_queue.sh`): 장애물 학습 종료 → 평가 → 실사진 데모+VLM 8B → VLM bench(2B/8B 200장) → SAM 3 의사 라벨(처음부터) → unified_v1 → 통합 학습 → 평가. 일시정지했던 SAM 3(600장 진행)는 종료.

## 2026-10-21 (D0) 15시 20분: 보도면 모델 완료, 명동 실사진 적용

- `seg_m_surface_v1` 완료(14:55). **전체 valid 954장: mIoU 0.670, sidewalk 0.860, 비율 MAE 0.015, ≤0.1 97.8%, 소멸 F1 0.915.** ep3 대비 전 지표 우세(150장 부분집합에선 반대 → 소표본 흔들림).
- 학습 대기열 버그: `tmux has-session -t train` 이 접두어 매칭으로 `train_q` 자신에 걸려 무한 대기 → `-t =train` 정확 매칭. 장애물 모델 15:03 시작(3,320 step/epoch, ~17:30 완료 예상).
- 명동 2025 실사진(544장)에 보도면 모델 적용: 보도 검출 94%, 횡단보도 프레임 '소멸' 정상, 도메인 차이 문제 작음. 절대폭 추정 가능 41%.
- **보행자·유모차 등 이동 객체(TRANSIENT)는 유효폭에서 빼지 않음** — 지자체 조치 대상 아님, 명동 인파에서 과소추정. 이동 객체 아래는 보도로 채움.

## 2026-10-21 (D0) 14시 40분: 대상 지역 → 명동·을지로 (Mapillary 실사진)

- 사용자 제안: 공개된 실제 촬영 영상+GPS 활용, 지역은 신촌 고집 안 함.
- 지도앱 로드뷰(네이버·카카오·구글)는 약관상 다운로드·AI 활용 금지 → 제외. KartaView 는 서울 커버리지 사실상 0.
- **Mapillary** (CC BY-SA 4.0, 사용자 개발자 토큰 `.mapillary_token`): 서울 16곳 조사(`outputs/mapillary/survey.py`) → 신촌 보행 사진 0, **명동·을지로(중구)** 최다.
- `mapillary.py`: perspective 카메라 + 시퀀스 이동속도 중앙값 0.5~2.5 m/s(보행)만, 연도별 세션, `attribution.json` 출처 기록. 중구 보행 사진 2017년 1,315 / 2025년 1,172 → **2017 vs 2025 비교** 세션.
- `links.py --area jung_gu`, `scripts/run_mly_demo.sh`, 앱에 CC BY-SA 출처 표시. 지도 타일 OSM 으로(CartoDB 키 필요).
- 다운로드 완료(1 m 미만 정지 사진 제외): **2025 명동 544장(26링크), 2017 을지로 918장(90링크)**. 스냅 ≤15 m 비율 99%/93%.
- 단, **연도 간 공통 링크 0** (2017 을지로·2025 명동으로 지역이 다름). 전 연도 메타 확인해도 겹침 ≤5 링크. 2025 내부도 9/24·9/26 공통 2~3 링크.
- 결정: 실사진 세션은 '지역 분석'용(명동 2025, 을지로 2017). **전·후 비교는 사용자 재촬영(2025 경로 0.8 km, `docs/myeongdong_reshoot.html`) 권장**, 불가하면 시뮬레이션 비교(표시 명시).
- VLM explain 경로 E2E 확인(2B). '보도 위' 오기술·일반론 조치 → 유형별 사실 규칙·조치 메뉴·구체 관찰 요구 추가.
- mapillary 다운로드: 503 으로 중단 → 재시도·백오프, 4스레드.

## 2026-10-21 (D0) 14시 20분: 실데이터 첫 E2E, 파인튜닝 효과 확인

- teacher 비교 결과 **SAM 3 채택** (장애물 mIoU 0.42 vs GDINO 0.31, GDINO 는 볼라드·입간판·화분 0). `docs/results.md`.
- surface ep3 중간 체크포인트 평가(동일 150장): 면 mIoU **0.606**, 비율 MAE **0.011** (SAM 3 zero-shot 0.088), 소멸 F1 0.944. 약점 stairs·repair_zone(학습 희소).
- 절대폭 보조 지표(카메라 높이만으로 m 폭, 1.2 m 미만 비중) 구현. GT 에서 30% 프레임만 추정 가능 → 점수 미반영, 링크 상세 보조 표시.
- 시뮬레이션 E2E(590프레임, 31링크, 추론 1분 37초): 처음엔 24/31 이 '소멸' → 횡단·골목 입구의 짧은 보도 공백 때문. **연속 3프레임 미만 공백은 횡단으로 제외**(`drop_short_gaps`) → 안전 22·주의 6·위험 3. 위험 링크 대표 프레임 육안 확인: 실제로 보도 없는 이면도로(alley) → 유형 정의와 일치.
- aihub_fetch: 끊긴 다운로드를 성공 처리하던 문제 → zip 무결성 검사 + 3회 재시도.

## 2026-10-21 (D0) 13시 40분: 멀티모달 LLM·teacher 비교 층 추가 (사용자 제안)

구조: **세그(폭 측정) → 규칙(점수) → VLM(확인·설명·조치 제안)**, teacher 는 SAM 3 vs Grounding DINO+SAM 2.1 비교.
- 캐시에 Qwen3-VL-2B/8B, grounding-dino-base/tiny, sam2.1-hiera-large 가 이미 있음 → roadpush env(transformers 5.20)로 실행.
- Qwen3-VL-2B 열린 질문: 버스정류장으로 좁아진 보도·골목 사진 둘 다 "차량·이륜차·입간판·적치물·공사"를 그대로 나열 → **환각**(프롬프트 예시 복창).
- 대응: 닫힌 예/아니오 질문 10개(`CHECKS`), 세그 결과와 교차검증(둘 다 '있음'만 confirmed), 측정값을 근거로 준 담당자 메모(`cause/action/priority`).
- `vlm bench` (Polygon valid 40장, 2B): truck_bus 0.975, two_wheeler 0.925, person 0.875, car 0.775(오경보 0.6) → 8B 비교 예정.
- `gdino_label.py`: 동일 프롬프트·동일 COCO 출력. 첫 확인에서 "construction site on sidewalk" 과검출 경향.
- teacher 비교 실험(tmux `teach`): 각 150장, 장애물=Polygon valid, 면=Surface valid → `outputs/teachers/eval_*.json`. **결과로 B안 teacher 결정 후 의사 라벨링 재개.**
- 앱 링크 상세에 VLM 메모·교차검증 표시.

## 2026-10-21 (D0) 13시 15분: Polygon 확인, A/B 두 갈래

- Polygon_1: 300 XML / 14,838장, 장애물 11종 전부 매핑(미매핑 0), **보도면 라벨 0**. → Surface(면만)·Polygon(장애물만) 라벨이 서로 배타적.
- `data/coco/polygon_v1` (train 13,272 / valid 1,566, 폴더 단위 분할).
- **A안(기준선)**: 보도면 모델 + 장애물 모델 따로 학습, `Predictor`가 여러 체크포인트 결과를 합침. 학습: tmux `train`(surface) → `train_q`(obstacle) 순차.
- **B안(개선)**: SAM 3로 결측 클래스 의사 라벨(Polygon train에 면 7종, Surface train에 장애물 9종) → `merge_coco.py`로 통합 → 단일 모델. tmux `sam3` (0.53 s/img). A안 학습 우선을 위해 SAM 3 프로세스 SIGSTOP, 학습 끝나면 `sam3_resume`이 자동 재개.
- 학습 중 1080p 마스크 검증이 epoch당 15분 → `eval_masks_head_resolution` + 2 epoch 간격으로 변경. 최종 지표는 `evaluate.py --classes surface|obstacle`.
- 테스트 26개 통과.

## 2026-10-21 (D0) 13시: 분할 누수 수정, 시뮬레이션 세션

- AI Hub 폴더 = 연속 프레임 → 이미지 단위 분할은 인접 프레임이 valid 로 새서 지표가 부풀려짐. **XML(폴더) 단위 분할(`--split-by xml`, 기본)** 로 바꾸고 surface 학습 재시작(`seg_m_surface_v1`, train 8,604 / valid 954).
- `simulate.py`: 학습에 안 쓴 valid 폴더 연속 프레임을 신촌 OSM 링크 위 가상 보행 경로(1.2 m/s, 1 fps)에 배치 → 대시보드 검증용 `sim_` 세션. 11폴더/640프레임/29링크 확인. **GPS 가짜이므로 보고서·앱에서 시뮬레이션으로 명시.**

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
