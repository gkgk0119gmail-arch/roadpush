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


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--session", type=Path, default=ROOT / "outputs/mly_junggu_2025")
    ap.add_argument("--links", type=Path, default=ROOT / "data/links/jung_gu.geojson")
    ap.add_argument("--out", type=Path, default=ROOT / "docs/figures")
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    _font()
    fig_compare(args.out)
    if (args.session / "links_scored.geojson").exists():
        fig_map(args.session, args.links, args.out)
        fig_frames(args.session, args.out)
    print("→", sorted(p.name for p in args.out.glob("*.png")))


if __name__ == "__main__":
    main()
