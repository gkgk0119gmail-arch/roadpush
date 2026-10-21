"""시뮬레이션 세션: AI Hub 연속 이미지를 신촌 링크 위 가상 보행 경로에 배치.

자가 촬영 영상이 들어오기 전 파이프라인·대시보드 검증용. GPS가 실제가 아니므로
세션 이름에 반드시 `sim_` 접두어를 붙이고, 앱과 보고서에서 "시뮬레이션"으로 표기한다.

AI Hub Surface/Polygon 폴더(예: Surface_001)는 한 번의 보행에서 뽑은 연속 프레임이다.
폴더 하나 = 연결된 링크 경로 하나. 보행 속도 1.2 m/s, 1 fps 가정.

출력은 frames.py 와 같은 레이아웃: <out>/frames/*.jpg, <out>/frames.csv

사용:
    python -m roadpush.simulate --src data/raw/aihub/extracted/surface --links data/links/sinchon.geojson \
        --out outputs/sim_aihub_s1 --folders 12 --seed 0
"""
from __future__ import annotations

import argparse
import csv
import os
import random
from collections import defaultdict
from pathlib import Path

import numpy as np
from shapely.geometry import LineString

WALK_HIGHWAY = {"footway", "residential", "living_street", "pedestrian", "tertiary", "secondary", "primary",
                "service", "unclassified"}


def _nodes(link_id: str) -> tuple[str, str]:
    p = link_id.split("_")
    return p[1], p[2]


def build_graph(links) -> dict[str, list[tuple[str, int]]]:
    """노드 → [(이웃 노드, 링크 행 번호)]"""
    g: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for i, r in enumerate(links.itertuples()):
        if r.highway not in WALK_HIGHWAY:
            continue
        u, v = _nodes(r.link_id)
        g[u].append((v, i))
        g[v].append((u, i))
    return g


def random_route(links, g, target_m: float, rng: random.Random, used: set[int]) -> list[tuple[int, bool]]:
    """길이 target_m 이상의 연결 경로. [(링크 행, 정방향 여부)]. 이미 쓴 링크는 피한다."""
    starts = [n for n, nb in g.items() if len(nb) >= 2]
    for _ in range(200):
        node = rng.choice(starts)
        route, seen, total = [], set(), 0.0
        while total < target_m:
            cand = [(v, i) for v, i in g[node] if i not in seen and i not in used]
            if not cand:
                break
            v, i = rng.choice(cand)
            u0, _ = _nodes(links.iloc[i].link_id)
            route.append((i, u0 == node))
            seen.add(i)
            total += float(links.iloc[i].length_m)
            node = v
        if total >= target_m:
            return route
    raise RuntimeError("경로를 찾지 못함 (target_m 이 너무 김)")


def route_line(links, route) -> LineString:
    coords = []
    for i, fwd in route:
        c = list(links.iloc[i].geometry.coords)
        # OSM geometry 방향이 u→v 라는 보장이 없으니 이전 끝점과 가까운 쪽을 시작으로
        if coords:
            last = coords[-1]
            d0 = (c[0][0] - last[0]) ** 2 + (c[0][1] - last[1]) ** 2
            d1 = (c[-1][0] - last[0]) ** 2 + (c[-1][1] - last[1]) ** 2
            if d1 < d0:
                c = c[::-1]
        elif not fwd:
            c = c[::-1]
        coords.extend(c if not coords else c[1:])
    return LineString(coords)


def main(argv: list[str] | None = None) -> None:
    import geopandas as gpd
    from pyproj import Transformer

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", required=True, type=Path, help="Surface_xxx 폴더들이 있는 곳")
    ap.add_argument("--links", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--folders", type=int, default=12)
    ap.add_argument("--max-frames", type=int, default=60, help="폴더당 최대 프레임")
    ap.add_argument("--speed", type=float, default=1.2)
    ap.add_argument("--seed", type=int, default=0, help="폴더(장면) 선택 시드")
    ap.add_argument("--route-seed", type=int, default=None,
                    help="경로 시드(기본=seed). 같은 값이면 같은 링크 경로 → 전·후 비교용 두 세션")
    ap.add_argument("--holdout-coco", type=Path, default=None,
                    help="이 COCO(valid)에 모든 이미지가 든 폴더만 사용 → 학습에 안 쓴 장면으로 데모")
    args = ap.parse_args(argv)

    rng = random.Random(args.seed)
    route_rng = random.Random(args.seed if args.route_seed is None else args.route_seed)
    links = gpd.read_file(args.links)
    g = build_graph(links)
    to_m = Transformer.from_crs("EPSG:4326", "EPSG:5179", always_xy=True)
    to_ll = Transformer.from_crs("EPSG:5179", "EPSG:4326", always_xy=True)

    folders = sorted(p for p in args.src.iterdir() if p.is_dir() and any(p.glob("*.jpg")))
    if args.holdout_coco:
        import json
        held = {im["file_name"] for im in json.loads(args.holdout_coco.read_text())["images"]}
        folders = [p for p in folders if all(i.name in held for i in p.glob("*.jpg"))]
    folders = rng.sample(folders, min(args.folders, len(folders)))
    fdir = args.out / "frames"
    fdir.mkdir(parents=True, exist_ok=True)
    # 경로를 먼저 고정 길이로 뽑아 두면 폴더가 달라도 route_seed 가 같을 때 같은 링크를 지난다
    used: set[int] = set()
    routes = []
    for _ in folders:
        r = random_route(links, g, args.max_frames * args.speed, route_rng, used)
        used.update(i for i, _ in r)
        routes.append(r)
    rows, k = [], 0
    for folder, route in zip(folders, routes):
        imgs = sorted(folder.glob("*.jpg"))[: args.max_frames]
        xy = np.asarray(route_line(links, route).coords)
        line_m = LineString(np.c_[to_m.transform(xy[:, 0], xy[:, 1])])
        for j, img in enumerate(imgs):
            q = line_m.interpolate(j * args.speed)
            lon, lat = to_ll.transform(q.x, q.y)
            k += 1
            name = f"frame_{k:06d}.jpg"
            dst = fdir / name
            if not dst.exists():
                os.symlink(img.resolve(), dst)
            rows.append([name, f"{k - 0.5:.2f}", "", f"{lat:.7f}", f"{lon:.7f}", 1, f"{folder.name}/{img.name}"])
    with open(args.out / "frames.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["frame", "t_sec", "utc", "lat", "lon", "gps_ok", "source"])
        w.writerows(rows)
    print(f"sim: folders={len(folders)} frames={len(rows)} links_used={len(used)} → {args.out}")


if __name__ == "__main__":
    main()
