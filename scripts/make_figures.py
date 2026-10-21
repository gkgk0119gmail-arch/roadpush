"""보고서·발표용 그림 (PNG, 밝은 배경).

    fig_compare.png  zero-shot teacher vs 파인튜닝 — 지표별 패널(단일 축), 파인튜닝만 강조색
    fig_map.png      세션 링크 위험도 지도 — 등급은 상태색 + 라벨 범례
    fig_frames.png   대표 프레임 오버레이 3장 (정상 / 폭 협소 / 보도 소멸)

사용:
    python scripts/make_figures.py --session outputs/mly_junggu_2025 --out docs/figures
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# 참조 팔레트(dataviz references/palette.md)
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
EMPH, MUTED = "#2a78d6", "#b8b7b0"
STATUS = {"안전": "#0ca30c", "주의": "#fab219", "위험": "#d03b3b"}


def _font() -> None:
    for f in font_manager.findSystemFonts():
        if "NotoSansCJK-Regular" in f or "NotoSansCJKkr-Regular" in f:
            font_manager.fontManager.addfont(f)
            plt.rcParams["font.family"] = font_manager.FontProperties(fname=f).get_name()
            break
    plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "axes.edgecolor": GRID,
                         "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "text.color": INK,
                         "axes.spines.top": False, "axes.spines.right": False, "axes.unicode_minus": False})


def fig_compare(out: Path) -> None:
    ev = ROOT / "outputs"
    rows = [("SAM 3 (zero-shot)", ev / "teachers/eval_sam3_surface_v2.json"),
            ("Grounding DINO+SAM 2 (zero-shot)", ev / "teachers/eval_gdino_surface_v2.json"),
            ("RoadPush RF-DETR-Seg (파인튜닝)", ev / "eval/eval_surface_final_150_v2.json")]
    data = [(n, json.loads(p.read_text())) for n, p in rows if p.exists()]
    metrics = [("유효보행폭 비율 오차 (병목 MAE, 낮을수록 좋음)", "ratio_mae", "{:.3f}"),
               ("보도 IoU (높을수록 좋음)", None, "{:.2f}"),
               ("보도 소멸 판정 F1 (높을수록 좋음)", "vanish_f1", "{:.2f}")]
    fig, axes = plt.subplots(1, 3, figsize=(15, 3.6))
    for ax, (title, key, fmt) in zip(axes, metrics):
        vals = [d["iou"]["sidewalk"] if key is None else d[key] for _, d in data]
        names = [n for n, _ in data]
        colors = [EMPH if "파인튜닝" in n else MUTED for n in names]
        y = range(len(names))[::-1]
        ax.barh(list(y), vals, color=colors, height=0.55, edgecolor=SURFACE, linewidth=2)
        for yi, v in zip(y, vals):
            ax.text(v, yi, " " + fmt.format(v), va="center", color=INK, fontsize=11)
        ax.set_yticks(list(y), names if ax is axes[0] else [""] * len(names), fontsize=10)
        ax.set_title(title, loc="left", fontsize=12, color=INK)
        ax.xaxis.grid(True, color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        ax.set_xlim(0, max(vals) * 1.25)
    fig.text(0.01, -0.04, "AI Hub 인도보행 영상 검증셋(폴더 단위 분리) 동일 150장 기준", color=INK2, fontsize=9)
    fig.tight_layout()
    fig.savefig(out / "fig_compare.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig_map(session: Path, links: Path, out: Path, col: str = "grade") -> None:
    import geopandas as gpd

    g = gpd.read_file(session / "links_scored.geojson").to_crs(5179)
    base = gpd.read_file(links).to_crs(5179)
    b = g.total_bounds
    pad = 120
    base = base.cx[b[0] - pad:b[2] + pad, b[1] - pad:b[3] + pad]
    fig, ax = plt.subplots(figsize=(8, 8))
    base.plot(ax=ax, color="#cfcdc6", linewidth=0.8)
    for grade, color in STATUS.items():
        sub = g[g[col] == grade]
        if len(sub):
            sub.plot(ax=ax, color=color, linewidth=4.5, label=f"{grade} ({len(sub)})")
    ax.set_xlim(b[0] - pad, b[2] + pad)
    ax.set_ylim(b[1] - pad, b[3] + pad)
    ax.set_axis_off()
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False, title="링크 등급",
              fontsize=11, title_fontsize=11, alignment="left")
    fig.suptitle(f"도로 링크별 보행공간 단절 위험도 — {session.name}", x=0.02, ha="left", fontsize=13)
    fig.text(0.02, 0.02, "지도 © OpenStreetMap contributors (ODbL)", color=INK2, fontsize=8)
    fig.savefig(out / "fig_map.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig_frames(session: Path, out: Path) -> None:
    import numpy as np
    from PIL import Image

    rs = [json.loads(line) for line in open(session / "frame_results.jsonl", encoding="utf-8")]
    have = {p.name for p in (session / "overlay").glob("*.jpg")}
    rs = [r for r in rs if r["frame"] in have]
    picks = []
    ok = [r for r in rs if r["sidewalk_present"] and r["ratio"] >= 0.95]
    nar = sorted([r for r in rs if r["sidewalk_present"] and r["ratio"] < 0.95], key=lambda r: r["ratio"])
    van = [r for r in rs if not r["sidewalk_present"]]
    for title, pool in (("정상 보도", ok), ("폭 협소", nar), ("보도 소멸", van)):
        if pool:
            picks.append((title, pool[len(pool) // 2] if title != "폭 협소" else pool[min(2, len(pool) - 1)]))
    fig, axes = plt.subplots(1, len(picks), figsize=(5.2 * len(picks), 4.2))
    for ax, (title, r) in zip(np.atleast_1d(axes), picks):
        ax.imshow(Image.open(session / "overlay" / r["frame"]))
        sub = "보도 없음 → 차도·골목 합류" if not r["sidewalk_present"] else f"유효보행폭 비율 {r['ratio']:.2f}"
        ax.set_title(f"{title}\n{sub}", fontsize=12, loc="left")
        ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(out / "fig_frames.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def fig_pipeline(out: Path) -> None:
    """파이프라인 도식: 주 흐름(가로) + teacher(점선, 학습 시에만)."""
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

    steps = [("보행 촬영 영상\n+ GPS", "폰·공개 거리사진"),
             ("RF-DETR-Seg", "보도면 9종 · 장애물 11종\n픽셀 분할 (CPU 가능)"),
             ("유효보행폭 비율", "스캔라인 병목\n보행자 제외·통과 여유"),
             ("링크 위험도", "0~100 · 4+1 단절 유형\n보차 혼용 판정"),
             ("담당자 대시보드", "지도 · 우선순위 · 전후 비교\nQwen3-VL 점검 메모(사전 생성)")]
    fig, ax = plt.subplots(figsize=(16, 4.2))
    ax.set_xlim(0, 16); ax.set_ylim(0, 4.2); ax.set_axis_off()
    w, h, y = 2.6, 1.5, 2.3
    xs = [0.2 + i * 3.18 for i in range(len(steps))]
    for i, (x, (t, sub)) in enumerate(zip(xs, steps)):
        core = i in (1, 2)
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.15",
                                    fc=EMPH if core else "#eef3fb", ec=EMPH, lw=1.5))
        ax.text(x + w / 2, y + h * 0.68, t, ha="center", va="center", fontsize=14,
                color="white" if core else INK, weight="bold")
        ax.text(x + w / 2, y + h * 0.28, sub, ha="center", va="center", fontsize=10,
                color="white" if core else INK2)
        if i < len(steps) - 1:
            ax.add_patch(FancyArrowPatch((x + w + 0.03, y + h / 2), (xs[i + 1] - 0.03, y + h / 2),
                                         arrowstyle="-|>", mutation_scale=18, color=INK2, lw=1.5))
    # teacher (학습 단계)
    tx = xs[1]
    ax.add_patch(FancyBboxPatch((tx - 0.1, 0.25), w + 0.2, 1.15, boxstyle="round,pad=0.02,rounding_size=0.15",
                                fc=SURFACE, ec=INK2, lw=1.2, ls="--"))
    ax.text(tx + w / 2, 0.98, "SAM 3 (teacher, 학습 단계)", ha="center", fontsize=11, color=INK, weight="bold")
    ax.text(tx + w / 2, 0.55, "결측 라벨 보강 · zero-shot 비교\n배포물 미포함", ha="center", va="center", fontsize=9, color=INK2)
    ax.add_patch(FancyArrowPatch((tx + w / 2, 1.42), (tx + w / 2, y - 0.03), arrowstyle="-|>", mutation_scale=14,
                                 color=INK2, lw=1.2, ls="--"))
    ax.text(xs[0] + w / 2, 0.82, "학습 데이터\nAI Hub 인도보행 영상\n보도면 9.5천 · 장애물 1.5만 장", ha="center", fontsize=10, color=INK2, va="center")
    fig.savefig(out / "fig_pipeline.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


# 모델(엔티티)별 고정 색 — 참조 팔레트 categorical 1~4 순서, 모델이 늘어도 기존 색 유지
RUN_COLOR = {"seg_m_surface_v1": ("#2a78d6", "보도면 모델"), "seg_m_obstacle_v1": ("#eb6834", "장애물 모델"),
             "seg_m_unified_v1": ("#1baf7a", "통합 모델(SAM 3 보강)"), "seg_m_obstacle_v2": ("#eda100", "장애물 v2(희소 보강)")}


def fig_training(out: Path) -> None:
    """학습 곡선: 검증 마스크 mAP(EMA, 마스크 헤드 해상도) vs epoch. 단일 축, 모델별 고정색 + 직접 라벨."""
    import pandas as pd

    fig, ax = plt.subplots(figsize=(9, 4.2))
    drawn = 0
    for run, (color, label) in RUN_COLOR.items():
        f = ROOT / "checkpoints" / run / "metrics.csv"
        if not f.exists():
            continue
        d = pd.read_csv(f)
        col = "val/ema_segm_mAP_50_95"
        if col not in d:
            continue
        v = d.dropna(subset=[col]).groupby("epoch")[col].max()
        if v.empty:
            continue
        ax.plot(v.index + 1, v.values, color=color, lw=2, marker="o", ms=6, mec=SURFACE, mew=2, label=label)
        ax.annotate(f"{label} {v.values[-1]:.3f}", (v.index[-1] + 1, v.values[-1]), xytext=(6, 0),
                    textcoords="offset points", va="center", fontsize=10, color=INK)
        drawn += 1
    ax.set_xlabel("epoch")
    ax.set_ylabel("검증 마스크 mAP")
    ax.yaxis.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.set_title("학습 곡선 (검증 마스크 mAP@50:95, 마스크 헤드 해상도 — 최종 지표는 evaluate.py)", loc="left", fontsize=11)
    if drawn >= 2:
        ax.legend(frameon=False, loc="lower right", fontsize=9)
    ax.set_xlim(left=0.5, right=ax.get_xlim()[1] + 2.5)
    fig.tight_layout()
    fig.savefig(out / "fig_training.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--session", type=Path, default=ROOT / "outputs/mly_junggu_2025")
    ap.add_argument("--links", type=Path, default=ROOT / "data/links/jung_gu.geojson")
    ap.add_argument("--out", type=Path, default=ROOT / "docs/figures")
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    _font()
    fig_compare(args.out)
    fig_pipeline(args.out)
    fig_training(args.out)
    if (args.session / "links_scored.geojson").exists():
        fig_map(args.session, args.links, args.out)
        fig_frames(args.session, args.out)
    print("→", sorted(p.name for p in args.out.glob("*.png")))


if __name__ == "__main__":
    main()
