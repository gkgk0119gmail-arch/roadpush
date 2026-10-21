"""frames.csv + frame_results.jsonl → 링크 스냅 → 링크 점수 GeoJSON.

출력:
    <run>/frames_linked.csv          프레임별 link_id·dist·ratio·tags
    <run>/links_scored.geojson       점수 있는 링크 (프로필별 score/grade/primary_type)

사용:
    python -m roadpush.aggregate --run outputs/20261022_sinchon/a --links data/links/sinchon.geojson \
        --session 20261022_am
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from .links import LinkSnapper
from .scoring import PEDESTRIAN, WHEELCHAIR, FrameAnalysis, score_links


def load_frame_results(path: Path) -> dict[str, FrameAnalysis]:
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            out[r["frame"]] = FrameAnalysis(r["ratio"], r["min_ratio"], r["sidewalk_present"], r["tags"],
                                            r.get("n_obstacles_on_sidewalk", 0))
    return out


def link_frames(frames_csv: Path, results: dict[str, FrameAnalysis], snapper: LinkSnapper):
    """gps_ok 프레임만 스냅. (link_id → [FrameAnalysis]), 행 목록 반환."""
    by_link: dict[str, list[FrameAnalysis]] = defaultdict(list)
    rows = []
    with open(frames_csv, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            fa = results.get(r["frame"])
            if fa is None or r["gps_ok"] != "1":
                continue
            s = snapper.snap(float(r["lon"]), float(r["lat"]))
            rows.append({**r, "link_id": s.link_id or "", "dist_m": round(s.dist_m, 2),
                         "ratio": round(fa.ratio, 3), "tags": "|".join(fa.tags)})
            if s.link_id:
                by_link[s.link_id].append(fa)
    return by_link, rows


def write_scored_geojson(links_path: Path, by_link, out: Path, session: str) -> int:
    import geopandas as gpd

    links = gpd.read_file(links_path).set_index("link_id")
    ped = {s.link_id: s for s in score_links(by_link, PEDESTRIAN)}
    wc = {s.link_id: s for s in score_links(by_link, WHEELCHAIR)}
    rows = []
    for lid, s in ped.items():
        w = wc[lid]
        d = s.to_dict()
        d.pop("type_fracs")
        rows.append({**d, **{f"wc_{k}": v for k, v in (("score", w.score), ("grade", w.grade),
                                                        ("primary_type", w.primary_type))},
                     "session": session, "name": links.at[lid, "name"], "highway": links.at[lid, "highway"],
                     "length_m": links.at[lid, "length_m"], "geometry": links.at[lid, "geometry"]})
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    out.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(out, driver="GeoJSON")
    return len(gdf)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True, type=Path)
    ap.add_argument("--links", required=True, type=Path)
    ap.add_argument("--session", default="s1", help="촬영 회차/시간대 (전·후 비교 키)")
    ap.add_argument("--max-dist", type=float, default=15.0)
    args = ap.parse_args(argv)

    results = load_frame_results(args.run / "frame_results.jsonl")
    snapper = LinkSnapper.from_geojson(args.links, args.max_dist)
    by_link, rows = link_frames(args.run / "frames.csv", results, snapper)
    if rows:
        with open(args.run / "frames_linked.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    n = write_scored_geojson(args.links, by_link, args.run / "links_scored.geojson", args.session)
    snapped = sum(1 for r in rows if r["link_id"])
    print(f"frames={len(results)} gps_ok={len(rows)} snapped={snapped} links_scored={n}")


if __name__ == "__main__":
    main()
