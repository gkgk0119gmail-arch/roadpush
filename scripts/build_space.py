"""Hugging Face Spaces(Streamlit, 무료 CPU) 배포 폴더를 만든다.

구성 (out/):
    README.md            Spaces 메타데이터(front matter)
    requirements.txt     CPU torch + rfdetr + 앱 의존성
    app.py               app/app.py 복사 (ROOT 를 out/ 로 보도록 환경변수 기본값 사용)
    src/roadpush/        추론·점수 모듈만 (sam3_label 등 teacher 코드는 제외)
    app/data/<session>/  links_scored.geojson, frames_linked.csv, overlay/*.jpg
    app/data/links.geojson
    app/model/*.pth      RF-DETR-Seg 체크포인트 (git lfs)
    app/samples/*.jpg    업로드 탭 예시 이미지

SAM 3 는 배포물에 넣지 않는다 (CLAUDE.md 절대 규칙) — 아래 EXCLUDE 로 강제.

사용:
    python scripts/build_space.py --out dist/space --sessions outputs/sim_aihub_s1 \
        --ckpt checkpoints/seg_m_surface_v1/checkpoint_best_total.pth checkpoints/seg_m_obstacle_v1/checkpoint_best_total.pth \
        --samples data/coco/surface_v1/valid/MP_SEL_SUR_000121.jpg
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULES = ["__init__.py", "classes.py", "width_ratio.py", "scoring.py", "infer.py", "train.py"]
EXCLUDE = {"sam3_label.py"}

README = """---
title: RoadPush 보행공간 단절 위험도
emoji: 🚶
colorFrom: green
colorTo: red
sdk: streamlit
sdk_version: "{sdk}"
app_file: app.py
pinned: false
license: apache-2.0
---

RoadPush — 보행 촬영 영상으로 도로 링크별 유효보행폭 비율과 단절 위험도를 산출하는 PoC
(2026 AI 라이프 솔루션 챌린지). 모델: RF-DETR-Seg (Apache 2.0), AI Hub 인도보행 영상 파인튜닝.
"""

REQUIREMENTS = """--extra-index-url https://download.pytorch.org/whl/cpu
torch
torchvision
rfdetr
supervision
numpy
opencv-python-headless
pillow
pandas
geopandas
shapely
pyproj
folium
streamlit-folium
"""


def main(argv: list[str] | None = None) -> None:
    import streamlit

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "dist" / "space")
    ap.add_argument("--sessions", nargs="+", type=Path, required=True)
    ap.add_argument("--links", type=Path, default=ROOT / "data" / "links" / "sinchon.geojson")
    ap.add_argument("--ckpt", nargs="+", type=Path, required=True)
    ap.add_argument("--size", default="medium")
    ap.add_argument("--samples", nargs="*", type=Path, default=[])
    args = ap.parse_args(argv)

    out = args.out
    if out.exists():
        shutil.rmtree(out)
    (out / "src" / "roadpush").mkdir(parents=True)
    for m in MODULES:
        assert m not in EXCLUDE
        shutil.copy2(ROOT / "src" / "roadpush" / m, out / "src" / "roadpush" / m)

    data = out / "app" / "data"
    data.mkdir(parents=True)
    shutil.copy2(args.links, data / "links.geojson")
    for s in args.sessions:
        d = data / s.name
        d.mkdir()
        for f in ("links_scored.geojson", "frames_linked.csv", "links_vlm.json"):
            if (s / f).exists():
                shutil.copy2(s / f, d / f)
        if (s / "overlay").exists():
            shutil.copytree(s / "overlay", d / "overlay")

    model = out / "app" / "model"
    model.mkdir(parents=True)
    names = []
    for i, c in enumerate(args.ckpt):
        n = f"roadpush_seg_{i}.pth"
        shutil.copy2(c, model / n)
        names.append(f"app/model/{n}")

    samples = out / "app" / "samples"
    samples.mkdir(parents=True)
    for p in args.samples:
        shutil.copy2(p.resolve(), samples / p.name)

    app_src = (ROOT / "app" / "app.py").read_text(encoding="utf-8")
    # Space 에서는 app.py 가 루트에 있으므로 ROOT 계산을 바꾸고 체크포인트 기본값을 박는다
    app_src = app_src.replace("ROOT = Path(__file__).resolve().parent.parent", "ROOT = Path(__file__).resolve().parent")
    app_src = app_src.replace('str(ROOT / "app" / "model" / "roadpush_seg.pth")',
                              repr(",".join(str(Path("app") / "model" / Path(n).name) for n in names)))
    app_src = app_src.replace('SIZE = os.environ.get("ROADPUSH_SIZE", "medium")',
                              f'SIZE = os.environ.get("ROADPUSH_SIZE", "{args.size}")')
    (out / "app.py").write_text(app_src, encoding="utf-8")
    (out / "README.md").write_text(README.format(sdk=streamlit.__version__), encoding="utf-8")
    (out / "requirements.txt").write_text(REQUIREMENTS, encoding="utf-8")
    (out / ".gitattributes").write_text("*.pth filter=lfs diff=lfs merge=lfs -text\n*.jpg filter=lfs diff=lfs merge=lfs -text\n")
    total = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(f"Space 폴더: {out}  ({total / 2**20:.0f} MB)")


if __name__ == "__main__":
    main()
