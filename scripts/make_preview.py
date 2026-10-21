"""세션 오버레이 → 미리보기 영상(mp4) + README 용 GIF.

    python scripts/make_preview.py --session outputs/mly_junggu_2025 --title "명동 2025"
출력: outputs/video/preview_<session>.mp4 (gitignored), docs/media/preview_<session>.gif (README 용, 작게)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
LEGEND = [("보도", (60, 180, 75)), ("차도", (128, 128, 128)), ("골목(이면도로)", (170, 110, 40)),
          ("점자블록", (255, 225, 25)), ("맨홀·배수구", (70, 240, 240)), ("장애물(윤곽)", (230, 25, 75))]


def _font(size: int):
    for f in ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"):
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def frames(session: Path, title: str, out_dir: Path) -> int:
    big, mid, sm, xs = _font(54), _font(30), _font(22), _font(16)
    card = Image.new("RGB", (1280, 720), (20, 24, 32))
    d = ImageDraw.Draw(card)
    for y, (t, f, c) in zip((230, 310, 370), [("RoadPush", big, (255, 255, 255)),
                                               ("보행공간 단절 위험도", mid, (200, 220, 255)),
                                               (f"{title} · AI 분할 + 유효보행폭 비율", sm, (170, 170, 170))]):
        d.text(((1280 - d.textlength(t, font=f)) / 2, y), t, font=f, fill=c)
    card.save(out_dir / "title.png")
    rs = {x["frame"]: x for x in map(json.loads, open(session / "frame_results.jsonl", encoding="utf-8"))}
    attrib = (session / "attribution.json").exists()
    k = 0
    for fn, x in sorted(rs.items()):
        ov = session / "overlay" / fn
        if not ov.exists():
            continue
        im = Image.open(ov).convert("RGB")
        im = im.resize((960, round(im.height * 960 / im.width)))
        c = Image.new("RGB", (1280, 720), (0, 0, 0))
        c.paste(im, (0, (720 - im.height) // 2 if im.height < 720 else 0))
        d = ImageDraw.Draw(c)
        d.text((980, 30), title, font=mid, fill=(255, 255, 255))
        if not x["sidewalk_present"]:
            st, col = "보도 없음 → 차도·골목 합류", (255, 120, 120)
        else:
            st = f"유효보행폭 비율 {x['ratio']:.2f}"
            col = (140, 230, 160) if x["ratio"] >= 0.7 else (250, 190, 80) if x["ratio"] >= 0.5 else (255, 120, 120)
        d.text((980, 90), st, font=sm, fill=col)
        if "shared" in x.get("tags", []):
            d.text((980, 122), "보차 혼용(보행 공간 안 차량)", font=xs, fill=(250, 190, 80))
        for i, (name, rgb) in enumerate(LEGEND):
            d.rectangle((980, 170 + i * 38, 1002, 192 + i * 38), fill=rgb)
            d.text((1012, 168 + i * 38), name, font=sm, fill=(230, 230, 230))
        if attrib:
            d.text((980, 665), "© Mapillary, CC BY-SA 4.0", font=xs, fill=(150, 150, 150))
        c.save(out_dir / f"f_{k:05d}.jpg", quality=88)
        k += 1
    return k


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--session", type=Path, default=ROOT / "outputs/mly_junggu_2025")
    ap.add_argument("--title", default="명동 2025")
    ap.add_argument("--fps", type=int, default=6)
    ap.add_argument("--gif-seconds", type=int, default=12)
    args = ap.parse_args(argv)
    name = args.session.name
    mp4 = ROOT / "outputs/video" / f"preview_{name}.mp4"
    gif = ROOT / "docs/media" / f"preview_{name}.gif"
    mp4.parent.mkdir(parents=True, exist_ok=True)
    gif.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        n = frames(args.session, args.title, t)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-loop", "1", "-t", "3", "-i", str(t / "title.png"),
                        "-framerate", str(args.fps), "-i", str(t / "f_%05d.jpg"), "-filter_complex",
                        f"[0:v]fps={args.fps},format=yuv420p[a];[1:v]format=yuv420p[b];[a][b]concat=n=2:v=1[v]",
                        "-map", "[v]", "-c:v", "libx264", "-crf", "23", "-pix_fmt", "yuv420p", str(mp4)], check=True)
        # GIF: 프레임 고르게 솎아 gif-seconds 분량, 폭 640
        step = max(1, n // (args.gif_seconds * 4))
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-framerate", "4", "-i", str(t / "f_%05d.jpg"),
                        "-vf", f"select='not(mod(n\\,{step}))',setpts=N/4/TB,scale=640:-1:flags=lanczos,"
                               "split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer",
                        "-t", str(args.gif_seconds), "-loop", "0", str(gif)], check=True)
    print(f"frames={n} → {mp4} ({mp4.stat().st_size / 2**20:.1f} MB), {gif} ({gif.stat().st_size / 2**20:.1f} MB)")


if __name__ == "__main__":
    main()
