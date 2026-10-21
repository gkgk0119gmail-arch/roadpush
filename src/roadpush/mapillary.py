"""Mapillary(CC BY-SA 4.0) 보행 시퀀스 → RoadPush 세션 (실제 사진 + 실제 GPS).

자가 촬영 대신 공개 거리 사진을 쓴다. 지도앱 로드뷰(네이버·카카오·구글)는 약관상 다운로드·AI 활용 금지라 쓰지 않는다.
보행 시점만 쓰기 위해 시퀀스별 이동 속도(인접 사진 거리/시간)의 중앙값이 보행 범위(0.5~2.5 m/s)인 것만,
일반 카메라(perspective)만 받는다. 360°(spherical/fisheye)·차량 시퀀스는 제외.

출력 (frames.py 와 같은 레이아웃 → infer/aggregate 그대로):
    <out>/frames/frame_000001.jpg ...
    <out>/frames.csv       frame,t_sec,utc,lat,lon,gps_ok,source(=mapillary image id),sequence,creator
    <out>/attribution.json CC BY-SA 출처 (이미지 id·촬영자·URL)

토큰: 저장소 루트 .mapillary_token (gitignored) 또는 MAPILLARY_TOKEN.

사용:
    python -m roadpush.mapillary --area myeongdong --year 2025 --out outputs/mly_myeongdong_2025
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = "https://graph.mapillary.com"

# (west, south, east, north)
AREAS = {
    "myeongdong": (126.9805, 37.5590, 126.9895, 37.5665),
    "euljiro": (126.9850, 37.5630, 126.9970, 37.5690),
    "jung_gu": (126.9805, 37.5590, 126.9970, 37.5690),   # 명동+을지로
    "sinchon": (126.930, 37.553, 126.946, 37.563),
}


def token() -> str:
    t = os.environ.get("MAPILLARY_TOKEN")
    if t:
        return t.strip()
    return (ROOT / ".mapillary_token").read_text().strip()


def _get(path: str, **params) -> dict:
    params["access_token"] = token()
    url = f"{API}/{path}?" + urllib.parse.urlencode(params)
    for k in range(4):
        try:
            return json.load(urllib.request.urlopen(url, timeout=60))
        except Exception:
            if k == 3:
                raise
            time.sleep(2 * (k + 1))
    return {}


def _tiles(bbox, step: float = 0.003):
    w, s, e, n = bbox
    x = w
    while x < e:
        y = s
        while y < n:
            yield (x, y, min(x + step, e), min(y + step, n))
            y += step
        x += step


def list_images(bbox) -> list[dict]:
    """bbox 를 잘게 나눠(요청당 2000개 상한) 이미지 메타 수집."""
    seen: dict[str, dict] = {}
    for t in _tiles(bbox):
        d = _get("images", bbox=",".join(f"{v:.6f}" for v in t), limit=2000,
                 fields="id,captured_at,sequence,camera_type,computed_geometry,creator,compass_angle")
        for x in d.get("data", []):
            if x.get("computed_geometry"):
                seen[x["id"]] = x
    return list(seen.values())


def _hav(a, b) -> float:
    R = 6371000.0
    lo1, la1, lo2, la2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    return 2 * R * math.asin(math.sqrt(math.sin((la2 - la1) / 2) ** 2 +
                                       math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2))


def walking_sequences(images: list[dict], min_len: int = 10, speed=(0.5, 2.5), year: int | None = None):
    seqs = defaultdict(list)
    for x in images:
        if x.get("camera_type") not in ("perspective", None):
            continue
        if year and datetime.fromtimestamp(x["captured_at"] / 1000, timezone.utc).year != year:
            continue
        seqs[x["sequence"]].append(x)
    out = {}
    for s, xs in seqs.items():
        xs.sort(key=lambda x: x["captured_at"])
        sp = [_hav(a["computed_geometry"]["coordinates"], b["computed_geometry"]["coordinates"]) /
              ((b["captured_at"] - a["captured_at"]) / 1000)
              for a, b in zip(xs, xs[1:]) if b["captured_at"] > a["captured_at"]]
        if len(xs) >= min_len and sp:
            med = sorted(sp)[len(sp) // 2]
            if speed[0] <= med <= speed[1]:
                out[s] = xs
    return out


def download(seqs: dict[str, list[dict]], out: Path, size: int = 2048, min_gap_m: float = 1.0,
             workers: int = 4) -> int:
    """시퀀스 순서대로 저장. 거의 같은 위치(min_gap_m 미만) 연속 사진은 건너뜀(정지 구간). 이미 받은 파일은 건너뜀."""
    from concurrent.futures import ThreadPoolExecutor

    fdir = out / "frames"
    fdir.mkdir(parents=True, exist_ok=True)
    plan = []   # (name, image meta, sequence id) — 번호는 결정적이라 중단 후 재실행해도 같은 파일명
    for sid, xs in seqs.items():
        last = None
        for x in xs:
            c = x["computed_geometry"]["coordinates"]
            if last is not None and _hav(last, c) < min_gap_m:
                continue
            last = c
            plan.append((f"frame_{len(plan) + 1:06d}.jpg", x, sid))

    def fetch(item) -> bool:
        name, x, _ = item
        dst = fdir / name
        if dst.exists() and dst.stat().st_size > 0:
            return True
        for k in range(5):   # 503(혼잡) 등은 백오프 후 재시도, 끝내 실패하면 그 장만 건너뜀
            try:
                url = _get(x["id"], fields=f"thumb_{size}_url").get(f"thumb_{size}_url")
                if not url:
                    return False
                tmp = dst.with_suffix(".part")
                tmp.write_bytes(urllib.request.urlopen(url, timeout=60).read())
                tmp.replace(dst)
                return True
            except Exception:
                time.sleep(3 * (k + 1))
        return False

    with ThreadPoolExecutor(workers) as ex:
        ok = list(ex.map(fetch, plan))
    rows, attrib, t0 = [], [], None
    for (name, x, sid), good in zip(plan, ok):
        if not good:
            continue
        c = x["computed_geometry"]["coordinates"]
        ts = x["captured_at"] / 1000
        t0 = ts if t0 is None else t0
        creator = (x.get("creator") or {}).get("username", "")
        rows.append([name, f"{ts - t0:.2f}", datetime.fromtimestamp(ts, timezone.utc).isoformat(),
                     f"{c[1]:.7f}", f"{c[0]:.7f}", 1, x["id"], sid, creator])
        attrib.append({"frame": name, "image_id": x["id"], "creator": creator,
                       "url": f"https://www.mapillary.com/app/?pKey={x['id']}"})
    with open(out / "frames.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["frame", "t_sec", "utc", "lat", "lon", "gps_ok", "source", "sequence", "creator"])
        w.writerows(rows)
    (out / "attribution.json").write_text(json.dumps(
        {"license": "CC BY-SA 4.0", "source": "Mapillary", "images": attrib}, ensure_ascii=False, indent=1))
    return len(rows)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--area", choices=sorted(AREAS), default="jung_gu")
    ap.add_argument("--year", type=int, default=None)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--survey", action="store_true", help="연도별 보행 시퀀스 통계만")
    ap.add_argument("--max-seqs", type=int, default=0)
    args = ap.parse_args(argv)

    imgs = list_images(AREAS[args.area])
    seqs = walking_sequences(imgs, year=args.year)
    by_year = defaultdict(int)
    for xs in seqs.values():
        by_year[datetime.fromtimestamp(xs[0]["captured_at"] / 1000, timezone.utc).year] += len(xs)
    print(f"{args.area}: 전체 {len(imgs)}장, 보행 시퀀스 {len(seqs)}개, 연도별 보행 사진 {dict(sorted(by_year.items()))}")
    if args.survey:
        return
    if args.max_seqs:
        seqs = dict(sorted(seqs.items(), key=lambda kv: -len(kv[1]))[: args.max_seqs])
    n = download(seqs, args.out)
    print(f"저장 {n}장 / 계획 대비 누락은 재실행으로 이어받기 → {args.out}")


if __name__ == "__main__":
    main()
