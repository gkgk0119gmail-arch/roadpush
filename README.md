# RoadPush — 보행공간 단절 위험도 자동 산출 PoC

2026 AI 라이프 솔루션 챌린지(산업통상부·KEIT) 출품작. 아이디어 챌린지 후보작 **RoadPush** 구현.

보행 촬영 영상을 세그멘테이션 모델(RF-DETR-Seg, AI Hub 인도보행 영상으로 파인튜닝)로 분석해
보도 링크별 **유효보행폭 비율**과 단절 위험도를 산출하고, 지자체 담당자가 지도에서 확인·조치 전후를 비교하는 PoC.

- 계획·아키텍처: [PLAN.md](PLAN.md)
- Claude Code 작업 지침: [CLAUDE.md](CLAUDE.md)
- 환경: `bash scripts/setup_env.sh` (Linux/WSL2, RTX 3090)
- 데이터: [scripts/aihub_download.md](scripts/aihub_download.md)
- 테스트: `pytest`

## 라이선스
코드 Apache-2.0. 학습 데이터는 AI Hub 이용약관, 보행 네트워크는 서울시 공공누리 1유형. SAM 3는 라벨링 보조로만 사용하며 배포물에 포함하지 않음.
