"""데모 영상 자동 제작 (제출물: 2~5분 mp4).

구성: 타이틀·문제 제기 카드 → 웹앱 조작 화면 녹화(Playwright, 자막 시점 기록) → 명동 걷기 미리보기 일부 → 성과·출처 카드.
자막은 ASS 로 만들어 ffmpeg 로 입힌다(Noto Sans CJK).

사용 (정적 사이트를 로컬에서 띄운 뒤):
    (cd dist/static && python3 -m http.server 8765 &)
    python scripts/record_demo.py --url http://localhost:8765/ --out outputs/video/RoadPush_demo.mp4
"""
from __future__ import annotations

import argparse
import asyncio
import subprocess
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
W, H = 1280, 720
SLOW = 1.45   # 자막·장면 유지 배율 (2분 32초 → 약 3분 30초, 사용자 피드백 "조금 빠름")


def font(sz):
    return ImageFont.truetype(FONT, sz)


def card(lines, path: Path, bg=(20, 24, 32), img: Path | None = None):
    """텍스트(+선택 이미지) 카드 PNG."""
    im = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(im)
    y = 70 if img else 220
    for t, sz, col in lines:
        f = font(sz)
        d.text(((W - d.textlength(t, font=f)) / 2, y), t, font=f, fill=col)
        y += sz + 22
    if img and img.exists():
        p = Image.open(img).convert("RGB")
        s = min((W - 80) / p.width, (H - y - 30) / p.height)
        p = p.resize((int(p.width * s), int(p.height * s)))
        im.paste(p, ((W - p.width) // 2, y + 10))
    im.save(path)


def still(png: Path, secs: float, out: Path):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-loop", "1", "-t", str(secs), "-i", str(png),
                    "-vf", f"scale={W}:{H},fps=30,format=yuv420p", "-c:v", "libx264", "-crf", "20", str(out)], check=True)


def ass_time(t: float) -> str:
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def write_ass(subs: list[tuple[float, float, str]], path: Path):
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV
Style: Default,Noto Sans CJK KR,30,&H00FFFFFF,&H00000000,&HA0000000,1,3,2,0,2,40,40,28

[Events]
Format: Layer, Start, End, Style, Text
"""
    lines = [f"Dialogue: 0,{ass_time(a)},{ass_time(b)},Default,{t}" for a, b, t in subs]
    path.write_text(head + "\n".join(lines) + "\n", encoding="utf-8")


async def record(url: str, vdir: Path) -> list[tuple[float, float, str]]:
    from playwright.async_api import async_playwright

    subs: list[tuple[float, float, str]] = []
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chrome", headless=True)
        ctx = await b.new_context(viewport={"width": W, "height": H}, record_video_dir=str(vdir),
                                  record_video_size={"width": W, "height": H})
        pg = await ctx.new_page()
        t0 = time.monotonic()
        now = lambda: time.monotonic() - t0  # noqa: E731

        async def say(text, secs):
            a = now()
            await pg.wait_for_timeout(int(secs * SLOW * 1000))
            subs.append((a, now(), text))

        await pg.goto(url)
        await pg.wait_for_selector("#prio tbody tr")
        await pg.wait_for_timeout(1500)
        await say("서울 도심(중구·종로) 공개 거리 사진 7,559장을 AI로 분석한 결과입니다", 5)
        await say("도로 구간(링크)마다 보행공간 단절 위험도 0~100점 — 빨강 위험 · 노랑 주의 · 초록 안전", 5)
        await say("회색은 사진이 없어 측정하지 못한 길입니다. 촬영을 더하면 바로 채워집니다", 4)
        await pg.mouse.move(400, 460)
        for _ in range(2):
            await pg.mouse.wheel(0, -300)
            await pg.wait_for_timeout(700)
        await say("오른쪽 표는 담당자를 위한 조치 우선순위입니다", 4)
        # 상세 장면: AI 메모가 있는 링크 중 프레임이 가장 많은 것(비율 타임라인·대표 프레임이 풍부)
        await pg.evaluate("""() => {
          const ids = Object.keys(state.memos).filter(k => state.memos[k].cause && state.frames[k]);
          ids.sort((a, b) => state.frames[b].length - state.frames[a].length);
          selectLink(ids[0], true); }""")
        await pg.wait_for_timeout(1200)
        await say("링크 상세 — 점수, 단절 유형, 공간 유형(분리 보도 · 보차 혼용 · 보도 없음)", 4)
        await say("멀티모달 AI(Qwen3-VL)가 측정값과 사진을 근거로 원인과 권고 조치를 씁니다", 5)
        await say("분할 모델과 교차검증한 사실만 근거로 씁니다 — AI 단독 판단의 환각을 막기 위해", 4)
        await pg.mouse.wheel(0, 500)
        await pg.wait_for_timeout(800)
        await say("촬영 순서별 유효보행폭 비율 — 0.5 아래로 떨어지는 지점이 병목입니다", 4)
        await pg.mouse.wheel(0, 600)
        await pg.wait_for_timeout(800)
        await say("대표 프레임 — 초록 보도, 갈색 골목, 빨강 장애물, 연보라 보행자(장애물로 세지 않음)", 5)
        await pg.mouse.wheel(0, -2000)
        await pg.click("#tabs button[data-tab=map]")
        await pg.wait_for_timeout(800)
        await pg.click("#profile button[data-p=wc]")
        await pg.wait_for_timeout(800)
        await say("휠체어 기준(통과 폭 0.7, 단차 가중)으로 바꾸면 위험 구간이 늘어납니다", 5)
        await pg.click("#profile button[data-p=ped]")
        await pg.select_option("#session", "mly_junggu_2025")
        await pg.wait_for_timeout(1500)
        await say("명동 2025 — 보도블록이 깔려 있어도 차량이 드나드는 보차 혼용 거리들", 5)
        await pg.select_option("#session", "mly_junggu_2017")
        await pg.wait_for_timeout(1500)
        await say("을지로 2017 — 보도 없이 차·수레·사람이 섞이는 공구상가 골목", 5)
        await pg.click("#tabs button[data-tab=upload]")
        await pg.wait_for_timeout(800)
        await say("사진 분석 — 사진 한 장을 올리면 AI가 브라우저 안에서 바로 분석합니다", 4)
        await pg.click("#samples button:nth-child(2)")
        a = now()
        await pg.wait_for_function("document.getElementById('ustatus').textContent.startsWith('완료')", timeout=300000)
        subs.append((a, now(), "서버가 없어 사진이 밖으로 나가지 않습니다 — 보도·장애물 분할과 유효보행폭 비율 계산"))
        await say("노란 선이 폭을 재는 스캔라인, 오른쪽이 판정 결과입니다", 5)
        await pg.click("#tabs button[data-tab=method]")
        await pg.wait_for_timeout(600)
        await say("지표 정의·판정 기준·모델·데이터 출처를 그대로 공개합니다", 4)
        await ctx.close()
        await b.close()
    return subs


def main(argv: list[str] | None = None) -> None:
    import json

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://localhost:8765/")
    ap.add_argument("--out", type=Path, default=ROOT / "outputs/video/RoadPush_demo.mp4")
    args = ap.parse_args(argv)
    st = json.loads((ROOT / "docs/figures/push_stats.json").read_text())
    fig = ROOT / "docs/figures"
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        # 1. 인트로·문제 제기
        card([("RoadPush", 72, (255, 255, 255)), ("보행공간 단절 위험도", 36, (200, 220, 255)),
              ("걷는 사람이 차도로 밀려나는(push) 구간을 거리 사진만으로 찾습니다", 26, (190, 190, 190)),
              ("2026 AI 라이프 솔루션 챌린지 · 아이디어 챌린지 후보작 RoadPush 구현", 20, (150, 150, 150))], t / "c1.png")
        card([("보도가 있어도 걸을 수 없는 길이 있습니다", 34, (255, 255, 255)),
              ("보도가 끊긴 골목 · 보행 공간을 차지한 차량 · 길을 막은 적치물", 24, (200, 200, 200))],
             t / "c2.png", img=fig / "fig_push_gallery.png")
        card([("지자체 담당자에게는 '어디가, 얼마나 막혀 있는지' 보여 줄 지표가 없습니다", 28, (255, 255, 255)),
              ("RoadPush: 사진 → AI 분할 → 유효보행폭 비율 → 도로 구간 점수 → 담당자 대시보드", 24, (200, 220, 255))],
             t / "c3.png", img=fig / "fig_pipeline.png")
        card([(f"서울 도심 {st['measured']}개 구간 · {st['measured_km']} km 측정", 34, (255, 255, 255)),
              (f"그중 {st['links']}개 · {st['km']} km에서 걷는 사람이 차도로 밀려납니다", 30, (255, 150, 150))],
             t / "c4.png", img=fig / "fig_push_map.png")
        for i, s in enumerate((7, 10, 10, 10), start=1):
            still(t / f"c{i}.png", s, t / f"c{i}.mp4")
        # 2. 웹앱 녹화 + 자막
        vdir = t / "v"
        subs = asyncio.run(record(args.url, vdir))
        webm = next(vdir.glob("*.webm"))
        write_ass(subs, t / "s.ass")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(webm), "-vf",
                        f"ass={t / 's.ass'},fps=30,format=yuv420p", "-c:v", "libx264", "-crf", "20", str(t / "app.mp4")], check=True)
        # 3. 명동 걷기 미리보기 일부(20초)
        pv = ROOT / "outputs/video/preview_mly_junggu_2025.mp4"
        parts = [t / f"c{i}.mp4" for i in (1, 2, 3, 4)] + [t / "app.mp4"]
        if pv.exists():
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", "8", "-t", "18", "-i", str(pv), "-vf",
                            f"setpts=1.33*PTS,scale={W}:{H},fps=30,format=yuv420p", "-c:v", "libx264", "-crf", "20",
                            str(t / "walk.mp4")], check=True)
            parts.append(t / "walk.mp4")
        # 4. 성과·출처
        card([("성과", 40, (255, 255, 255)),
              ("유효보행폭 비율 오차 0.017 · 파운데이션 모델(SAM 3) 대비 1/3 · 장애물 mIoU 0.76", 24, (200, 220, 255)),
              ("SAM 3는 라벨링 선생님으로만, 서비스는 가벼운 모델로 — 서버 없이 브라우저에서", 22, (190, 190, 190))],
             t / "c5.png", img=fig / "fig_compare.png")
        card([("RoadPush — 걸을 수 있는 도시를 위한 데이터", 36, (255, 255, 255)),
              ("데이터: AI Hub 인도보행 영상 · 거리 사진 © Mapillary contributors (CC BY-SA 4.0)", 20, (170, 170, 170)),
              ("지도 © OpenStreetMap contributors (ODbL) · 모델 RF-DETR-Seg (Apache 2.0) · Qwen3-VL", 20, (170, 170, 170)),
              ("github.com/gkgk0119gmail-arch/roadpush", 22, (150, 190, 255))], t / "c6.png")
        still(t / "c5.png", 10, t / "c5.mp4")
        still(t / "c6.png", 8, t / "c6.mp4")
        parts += [t / "c5.mp4", t / "c6.mp4"]
        (t / "list.txt").write_text("".join(f"file '{p}'\n" for p in parts))
        args.out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(t / "list.txt"),
                        "-c:v", "libx264", "-crf", "21", "-pix_fmt", "yuv420p", str(args.out)], check=True)
    dur = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(args.out)],
                         capture_output=True, text=True).stdout.strip()
    print(f"→ {args.out} ({float(dur):.0f}초, {args.out.stat().st_size / 2**20:.1f} MB)")


if __name__ == "__main__":
    main()
