"""인포그래픽·영상·보고서용 장면 사진 잘라내기 (docs/figures 갤러리 → outputs/media/img)."""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
F = ROOT / "docs/figures"
OUT = ROOT / "outputs/media/img"
OUT.mkdir(parents=True, exist_ok=True)
PANELS = {"TL": (13, 75, 747, 625), "TR": (795, 75, 1530, 625), "BL": (13, 699, 747, 1249), "BR": (795, 699, 1530, 1249)}


def crop(im, box, name, top=20):
    x0, y0, x1, y1 = box
    im.crop((x0, y0 + top, x1, y1)).save(OUT / f"{name}.jpg", quality=92)   # 위쪽 ratio 라벨 제거


ga = Image.open(F / "fig_push_gallery_a.png").convert("RGB")
gb = Image.open(F / "fig_push_gallery_b.png").convert("RGB")
fr = Image.open(F / "fig_frames.png").convert("RGB")
for k, v in PANELS.items():
    crop(ga, v, "a_" + k); crop(gb, v, "b_" + k)
for i, x in enumerate([18, 946, 1872]):
    crop(fr, (x, 89, x + 900, 764), f"f_{i}", top=24)
Image.open(F / "fig_push_map.png").convert("RGB").crop((230, 200, 1560, 1240)).save(OUT / "map.png")
print("→", OUT)
