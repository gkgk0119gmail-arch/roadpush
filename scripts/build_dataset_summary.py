"""선택 제출물: 학습 데이터셋 요약 + 샘플 결과물 1~2쪽 PDF (HTML → 크롬 헤드리스 인쇄).

    python scripts/build_dataset_summary.py --out dist/RoadPush_데이터셋요약.pdf
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def img(p: Path, w: str = "100%") -> str:
    b = base64.b64encode(p.read_bytes()).decode()
    return f'<img src="data:image/png;base64,{b}" style="width:{w}">'


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ROOT / "dist" / "RoadPush_데이터셋요약.pdf")
    args = ap.parse_args(argv)
    push = json.loads((ROOT / "docs/figures/push_stats.json").read_text())
    fig = ROOT / "docs/figures"
    html = f"""<!doctype html><html lang="ko"><meta charset="utf-8"><style>
    @page {{ size: A4; margin: 14mm; }}
    body {{ font-family: "Pretendard", "Noto Sans CJK KR", sans-serif; font-size: 10.5pt; color: #111; line-height: 1.5; }}
    h1 {{ font-size: 17pt; margin: 0 0 4px; }} h2 {{ font-size: 12.5pt; margin: 14px 0 6px; border-bottom: 1px solid #ccc; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 9.5pt; }} th, td {{ border: 1px solid #ccc; padding: 4px 6px; text-align: left; }}
    th {{ background: #eef3fb; }} .muted {{ color: #666; font-size: 9pt; }} .pb {{ page-break-before: always; }}
    </style><body>
    <h1>RoadPush — 학습 데이터셋 요약 · 샘플 결과물</h1>
    <div class="muted">2026 AI 라이프 솔루션 챌린지 · 보행공간 단절 위험도 · 코드 github.com/gkgk0119gmail-arch/roadpush</div>

    <h2>1. 학습 데이터 — AI Hub 인도보행 영상 (dataSetSn=189)</h2>
    <table><tr><th>구분</th><th>원천</th><th>사용 분량</th><th>라벨</th></tr>
    <tr><td>보도면(Surface Masking)</td><td>AI Hub, CVAT 폴리곤</td><td>Surface_1 9,558장 + 희소 보강 실험</td><td>보도·점자블록·차도·골목·자전거도로·계단·공사·맨홀/배수구·가로수틀 (9종)</td></tr>
    <tr><td>장애물(Polygon)</td><td>AI Hub, CVAT 폴리곤</td><td>Polygon_1 14,838장 + Polygon 1~10 희소 클래스 이미지 8.6천 장</td><td>차량·트럭/버스·이륜차·볼라드·기둥·바리케이드·입간판·화분·사람·기타 (11종, AI Hub 29종 통합)</td></tr>
    <tr><td>분할</td><td colspan="3">촬영 폴더(XML) 단위 train/valid 분리 — 연속 프레임이 검증에 새는 것 방지. 보도면 valid 954장, 장애물 valid 1,566장</td></tr>
    <tr><td>결측 보강(실험)</td><td colspan="3">보도면 데이터엔 장애물이, 장애물 데이터엔 보도면이 없음 → SAM 3 텍스트 프롬프트 의사 라벨 14.4만 개로 채운 통합 데이터셋(21,876장) 비교 실험</td></tr></table>

    <h2>2. 분석 대상 — 공개 거리 사진 (Mapillary, CC BY-SA 4.0)</h2>
    <table><tr><th>지역</th><th>사진</th><th>측정 링크</th><th>차도로 밀려나는 링크</th></tr>
    <tr><td>서울 도심(중구·종로), 2015~2025</td><td>{push['frames']:,}장 (일반 4,778 + 360° 진행 방향 변환 2,781)</td>
    <td>{push['measured']}개 · {push['measured_km']} km (OSM 보행 링크)</td><td><b>{push['links']}개 · {push['km']} km</b></td></tr></table>
    <div class="muted">얼굴·번호판 Mapillary 자동 블러. 지도앱 로드뷰는 약관상 사용하지 않음. 보행 속도(0.5~2.5 m/s) 시퀀스만 사용.</div>

    <h2>3. 모델·성능 (AI Hub 검증셋)</h2>
    <table><tr><th>모델</th><th>역할</th><th>성능</th></tr>
    <tr><td>RF-DETR-Seg Medium ×2 (Apache 2.0)</td><td>보도면·장애물 분할 (배포·브라우저 추론)</td><td>유효보행폭 비율 오차 0.017 · 보도 소멸 F1 0.915 · 장애물 mIoU 0.755</td></tr>
    <tr><td>SAM 3 (teacher)</td><td>결측 라벨 보강·zero-shot 비교</td><td>같은 150장 비율 오차 0.109 (파인튜닝 0.038)</td></tr>
    <tr><td>Qwen3-VL-8B (Apache 2.0)</td><td>점검 메모·닫힌 질문 교차검증</td><td>단독 판정 정확도 0.895 (차량 오경보 29% → 분할과 교차검증)</td></tr></table>
    {img(fig / "fig_compare.png")}

    <div class="pb"></div>
    <h2>4. 샘플 결과물 — 걷는 사람이 차도로 밀려나는 구간</h2>
    {img(fig / "fig_push_map.png", "88%")}
    {img(fig / "fig_push_gallery.png")}
    <div class="muted">초록 보도 · 갈색 골목(이면도로) · 회색 차도 · 빨강 장애물 · 연보라 보행자(장애물로 세지 않음). 링크 프레임 30% 이상이 보도 소멸·차량 점유·심한 협소(비율&lt;0.3)면 '밀려나는 링크'.</div>
    </body></html>"""
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        h = Path(td) / "s.html"
        h.write_text(html, encoding="utf-8")
        subprocess.run(["google-chrome", "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={args.out}", h.as_uri()], check=True, capture_output=True)
    print("→", args.out)


if __name__ == "__main__":
    main()
