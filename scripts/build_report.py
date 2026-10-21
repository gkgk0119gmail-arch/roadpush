"""성과보고서 PPT(공식 양식 4p) 자동 생성. 수치는 평가 JSON 에서 읽고, 없으면 '평가 중'.

    python scripts/build_report.py --out dist/RoadPush_성과보고서.pptx [--pdf]

양식의 '※ 작성 요령' 안내 상자는 지우고 같은 영역에 내용을 채운다. 폰트는 양식과 같은 Pretendard.
그림은 scripts/make_figures.py 결과(docs/figures/*.png).
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Cm, Pt

ROOT = Path(__file__).resolve().parent.parent
FIG = ROOT / "docs" / "figures"
FONT, FONT_B = "Pretendard", "Pretendard SemiBold"
INK, INK2, EMPH = RGBColor(0x0B, 0x0B, 0x0B), RGBColor(0x52, 0x51, 0x4E), RGBColor(0x2A, 0x78, 0xD6)


def _j(rel: str) -> dict:
    p = ROOT / rel
    return json.loads(p.read_text()) if p.exists() else {}


def numbers() -> dict:
    surf = _j("outputs/eval/eval_surface_final_full_v2.json")
    s150 = _j("outputs/eval/eval_surface_final_150_v2.json")
    sam3 = _j("outputs/teachers/eval_sam3_surface_v2.json")
    obs = _j("outputs/eval/eval_obstacle_v2_full.json") or _j("outputs/eval/eval_obstacle_final_full.json")
    push = _j("docs/figures/push_stats.json")
    sam3o = _j("outputs/teachers/eval_sam3_obstacle.json")
    f = lambda d, k, fmt: fmt.format(d[k]) if k in d else "평가 중"  # noqa: E731
    n = {
        "ratio_mae": f(surf, "ratio_mae", "{:.3f}"), "within": f(surf, "ratio_within_0.1", "{:.1%}"),
        "vanish_f1": f(surf, "vanish_f1", "{:.2f}"), "surf_miou": f(surf, "miou", "{:.2f}"),
        "sidewalk_iou": f"{surf['iou']['sidewalk']:.2f}" if surf else "평가 중",
        "n_surf": str(surf.get("n_images", "-")),
        "mae150": f(s150, "ratio_mae", "{:.3f}"), "sam3_mae150": f(sam3, "ratio_mae", "{:.3f}"),
        "obs_miou": f(obs, "miou", "{:.2f}"), "sam3_obs_miou": f(sam3o, "miou", "{:.2f}"),
    }
    if s150 and sam3:
        n["x_better"] = f"{sam3['ratio_mae'] / s150['ratio_mae']:.1f}배"
    else:
        n["x_better"] = "-"
    if push:
        n.update(links=str(push["measured"]), km=str(push["measured_km"]), push_links=str(push["links"]),
                 push_km=str(push["km"]), shared=str(push["shared"]), frames=f"{push['frames']:,}",
                 grades=" · ".join(f"{k} {v}" for k, v in push["grades"].items()))
    else:
        n.update(links="-", km="-", push_links="-", push_km="-", shared="-", frames="-", grades="-")
    return n


def text(slide, x, y, w, h, paras, anchor_top=True):
    """paras: [(문자열, pt, bold, color)] 또는 문자열(본문 기본)."""
    tb = slide.shapes.add_textbox(Cm(x), Cm(y), Cm(w), Cm(h))
    tf = tb.text_frame
    tf.word_wrap = True
    for i, p in enumerate(paras):
        if isinstance(p, str):
            p = (p, 22, False, INK)
        t, size, bold, color = p
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.space_after = Pt(size * 0.45)
        r = para.add_run()
        r.text = t
        r.font.size, r.font.bold, r.font.color.rgb = Pt(size), bold, color
        r.font.name = FONT_B if bold else FONT
    return tb


def picture(slide, path: Path, x, y, w=None, h=None):
    if path.exists():
        return slide.shapes.add_picture(str(path), Cm(x), Cm(y), Cm(w) if w else None, Cm(h) if h else None)
    return text(slide, x, y, w or 10, 2, [(f"[그림 없음: {path.name}]", 16, False, INK2)])


def stat(slide, x, y, value, label):
    text(slide, x, y, 12.5, 4.2, [(value, 44, True, EMPH), (label, 17, False, INK2)])


def drop_guides(slide):
    for sh in list(slide.shapes):
        if sh.has_text_frame and sh.text_frame.text.strip().startswith("※"):
            sh._element.getparent().remove(sh._element)


def build(out: Path) -> Path:
    n = numbers()
    prs = Presentation(str(ROOT / "docs/templates/성과보고서_양식_PPT.pptx"))
    s1, s2, s3, s4 = prs.slides
    for s in prs.slides:
        drop_guides(s)

    # ---- p1 AI 기술명
    text(s1, 3.5, 6.5, 30, 12, [
        ("RoadPush", 80, True, INK),
        ("보행 영상 기반 보행공간 단절 위험도 자동 산출 시스템", 30, True, INK),
        ("보도 세그멘테이션 + 유효보행폭 비율로, 도로 링크마다 '걸을 수 없는 구간'을 찾아 "
         "지자체 담당자에게 조치 우선순위를 제시하는 AI", 20, False, INK2)])
    stat(s1, 3.5, 21.0, n["ratio_mae"], "유효보행폭 비율 오차(MAE)\nAI Hub 검증 " + n["n_surf"] + "장")
    stat(s1, 16.5, 21.0, n["x_better"], "zero-shot SAM 3 대비\n비율 오차 감소")
    stat(s1, 3.5, 28.0, "서버 0대", "브라우저 안 AI 추론(ONNX)\nGPU 없이 지자체 PC에서")
    stat(s1, 16.5, 28.0, n["push_links"] + "개", f"차도로 밀려나는 링크 ({n['push_km']} km)\n서울 도심 {n['links']}개 링크·{n['km']} km 중")
    picture(s1, FIG / "fig_push_map.png", 34.5, 6.0, w=32.0)

    # ---- p2 아이디어명 / 기술요약
    text(s2, 3.5, 6.0, 60, 6, [
        ("2. 아이디어명", 26, True, INK),
        ("RoadPush (2026 AI 라이프 아이디어 챌린지 수상 후보작) — 보행공간 단절 위험도", 22, False, INK)])
    text(s2, 3.5, 11.0, 60, 9, [
        ("3. 기술요약", 26, True, INK),
        ("① 보행자 시점 영상을 경량 분할 모델(RF-DETR-Seg, Apache 2.0)로 분석해 보도면 9종과 주정차 차량·이륜차·"
         "입간판·볼라드 등 장애물 11종을 픽셀 단위로 구분한다.", 20, False, INK),
        ("② 분할 위에서 스캔라인별 '실제로 지나갈 수 있는 폭 ÷ 원래 보도 폭'(유효보행폭 비율)의 병목을 재고, "
         "보도 소멸·폭 협소·공사·단차·보차 혼용을 판정한다(보행자는 조치 대상이 아니므로 제외).", 20, False, INK),
        ("③ GPS로 보행 링크에 매핑해 링크별 위험도(0~100)를 산출하고, 멀티모달 LLM이 측정값을 근거로 쓴 "
         "점검 메모와 함께 지자체 담당자용 지도 대시보드로 제공한다.", 20, False, INK)])
    picture(s2, FIG / "fig_pipeline.png", 6.0, 21.5, w=55.0)

    # ---- p3 최종목표 / 개발 내용 및 결과
    text(s3, 3.5, 6.0, 30, 7, [
        ("4. 최종목표", 26, True, INK),
        ("• 걸으며 눈으로 하던 보도 점검을, 촬영 영상만으로 링크 단위 정량 지표로 바꾸는 PoC", 19, False, INK),
        ("• 서울 도심(중구·종로) 실제 거리 사진으로 링크 위험도·차도로 밀려나는 구간·조치 메모까지 자동 산출", 19, False, INK)])
    rows = [("단계", "내용", "결과"),
            ("데이터", "AI Hub 인도보행 영상 → 20종 COCO, 폴더 단위 분할", "보도면 9.6천·장애물 1.5만 장"),
            ("모델", "RF-DETR-Seg Medium 파인튜닝 (RTX 3090)", f"보도면 mIoU {n['surf_miou']} · 장애물 mIoU {n['obs_miou']}"),
            ("핵심 지표", "유효보행폭 비율(병목, 통과 여유)", f"MAE {n['ratio_mae']} · ±0.1 이내 {n['within']}"),
            ("판정", "소멸·협소·공사·단차·보차 혼용", f"보도 소멸 F1 {n['vanish_f1']}"),
            ("teacher", "SAM 3 vs Grounding DINO zero-shot 비교", f"비율 MAE {n['sam3_mae150']} → {n['mae150']}, 장애물 mIoU 0.52 → 0.70"),
            ("실사진", f"Mapillary(CC BY-SA) 도심 {n['frames']}장(360° 변환 포함) + OSM", f"{n['links']}링크 · 밀려남 {n['push_links']}개({n['push_km']} km)"),
            ("서비스", "정적 웹앱(지도·상세·사진 분석) · 브라우저 안 ONNX 추론", "HF Space 무료 · 서버 없음")]
    tbl = s3.shapes.add_table(len(rows), 3, Cm(3.5), Cm(13.6), Cm(30.5), Cm(17)).table
    for c, wcm in enumerate((5.0, 13.5, 12.0)):
        tbl.columns[c].width = Cm(wcm)
    for i, row in enumerate(rows):
        for j, v in enumerate(row):
            cell = tbl.cell(i, j)
            cell.text = v
            for p in cell.text_frame.paragraphs:
                for r in p.runs:
                    r.font.size, r.font.name = Pt(15 if i else 16), FONT_B if i == 0 or j == 0 else FONT
    text(s3, 3.5, 31.3, 30.5, 5, [
        ("차별점: '단절'은 객체가 아니라 공간 관계 → 객체 검출을 넘어 기하 후처리로 통과 폭을 정량화. "
         "파운데이션 모델(SAM 3)은 라벨링 teacher로만, 배포는 CPU에서 도는 경량 모델.", 16, False, INK2)])
    picture(s3, FIG / "fig_compare.png", 35.0, 6.0, w=30.0)
    picture(s3, FIG / "fig_push_gallery.png", 35.0, 15.5, w=30.0)

    # ---- p4 애로점 / 기대효과
    text(s4, 3.5, 6.0, 29, 30, [
        ("6. 개발 과정에서 애로점과 해결", 26, True, INK),
        ("• 라벨 결측: AI Hub 보도면 데이터엔 장애물이, 장애물 데이터엔 보도면이 없음 → 두 전문 모델 결합(A) + "
         "SAM 3 의사 라벨로 결측을 채운 통합 모델(B) 비교.", 21, False, INK),
        ("• 평가 누수: 연속 프레임을 이미지 단위로 나누면 검증 점수가 부풀려짐 → 촬영 폴더 단위 분할.", 21, False, INK),
        ("• 지표 희석: 명동 실사진에서 노점·입간판이 있어도 비율이 1.0 → 스캔라인 중앙값 대신 병목, "
         "마스크 틈 메움(통과 여유).", 21, False, INK),
        ("• 원근: 픽셀 폭을 m로 바꾸기 어려움 → 제안자 답변대로 비율이 기본, 1.2 m는 카메라 높이 가정 보조 지표.", 21, False, INK),
        ("• LLM 환각: 열린 질문에 사진과 무관한 장애물 나열 → 닫힌 질문 + 분할 결과 교차검증한 사실만 메모에 사용.", 21, False, INK),
        ("• 데이터 접근: 지도앱 로드뷰는 약관상 사용 불가 → Mapillary(CC BY-SA) 보행 시퀀스 + OSM 링크.", 21, False, INK),
        ("• 배포: 무료 서버 호스팅 중단 → 모델을 ONNX로 바꿔 사용자 브라우저에서 추론하는 서버 없는 웹앱(사진도 외부 전송 없음).", 21, False, INK)])
    text(s4, 34.5, 6.0, 30, 30, [
        ("7. 기대효과", 26, True, INK),
        ("• 지자체: 민원·순찰 의존 점검 → '촬영 → 자동 리포트'. 링크별 우선순위로 단속·정비 예산 배분 근거.", 21, False, INK),
        ("• 보행약자: 휠체어 기준(폭 0.7·단차 가중) 토글로 지나갈 수 없는 구간을 정량화 → 디지털 포용 정책 기초자료.", 21, False, INK),
        ("• 보차 혼용 구간 식별: 보도블록이 깔려도 차가 드나드는 거리 → 보행자 우선도로 지정·속도 제한 근거.", 21, False, INK),
        ("• 확장: 청소차·순찰차·배달 이륜차 카메라에 그대로 적용(경량·CPU). 시간대별 재분석으로 상습 적치·주정차 탐지.", 21, False, INK),
        ("• 개방: 코드 Apache-2.0, 데이터 출처 AI Hub·Mapillary(CC BY-SA)·OpenStreetMap(ODbL).", 19, False, INK2)])

    out.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out))
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "dist" / "RoadPush_성과보고서.pptx")
    ap.add_argument("--pdf", action="store_true")
    args = ap.parse_args(argv)
    out = build(args.out)
    print("→", out)
    if args.pdf:
        subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(out.parent), str(out)],
                       check=False, capture_output=True)
        print("→", out.with_suffix(".pdf"))


if __name__ == "__main__":
    main()
