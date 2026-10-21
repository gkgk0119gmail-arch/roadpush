"""보행 링크 추출과 GPS 점 → 링크 스냅.

분석 단위는 도로 링크(제안자 답변). 서울시 도보네트워크(OA-21208)는 API 키가 필요해서
기본은 OSM 보행 네트워크(osmnx, ODbL)를 쓰고, 같은 GeoJSON 스키마로 저장한다.

GeoJSON 링크 스키마 (EPSG:4326):
    link_id : str     "osm_<u>_<v>" (무방향, u<v)
    name    : str     도로명(없으면 "")
    highway : str     OSM highway 태그 대표값
    length_m: float
    geometry: LineString

사용:
    python -m roadpush.links --area sinchon --out data/links/sinchon.geojson
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from pyproj import Transformer
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

# (west, south, east, north) WGS84
AREAS: dict[str, tuple[float, float, float, float]] = {
    "sinchon": (126.930, 37.553, 126.946, 37.563),   # 신촌역~연세대 정문~이대 앞
    "yeouido": (126.915, 37.518, 126.935, 37.530),
}

# 실외 보행과 무관한 태그
EXCLUDE_HIGHWAY = {"corridor", "elevator", "proposed", "construction"}

# 미터 계산용 (Korea 2000 / Unified CS)
_TO_M = Transformer.from_crs("EPSG:4326", "EPSG:5179", always_xy=True)


def _first(v) -> str:
    if isinstance(v, (list, tuple)):
        return str(v[0]) if v else ""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return ""
    return str(v)


def fetch_osm_links(bbox: tuple[float, float, float, float]):
    """OSM 보행 네트워크 → 무방향 링크 GeoDataFrame."""
    import geopandas as gpd
    import osmnx as ox

    G = ox.graph_from_bbox(bbox, network_type="walk", simplify=True)
    edges = ox.graph_to_gdfs(G, nodes=False).reset_index()
    rows, seen, n_pair = [], set(), {}
    for r in edges.itertuples(index=False):
        hw = _first(r.highway)
        if hw in EXCLUDE_HIGHWAY:
            continue
        u, v = sorted((int(r.u), int(r.v)))
        key = (u, v, round(float(r.length), 1))   # 양방향 중복 제거, 평행 엣지는 길이로 구분
        if key in seen:
            continue
        seen.add(key)
        k = n_pair.get((u, v), 0)
        n_pair[(u, v)] = k + 1
        lid = f"osm_{u}_{v}" if k == 0 else f"osm_{u}_{v}_{k}"
        rows.append({"link_id": lid, "name": _first(getattr(r, "name", "")), "highway": hw,
                     "length_m": round(float(r.length), 2), "geometry": r.geometry})
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")


# ---------------------------------------------------------------- 스냅

@dataclass
class Snap:
    link_id: str | None
    dist_m: float
    offset_m: float      # 링크 시작점부터 투영 위치까지 거리


class LinkSnapper:
    """GPS 점을 최근접 링크로. max_dist_m 넘으면 link_id=None (PLAN 10장: 15m)."""

    def __init__(self, link_ids: list[str], lines_wgs84: list[LineString], max_dist_m: float = 15.0):
        self.link_ids = list(link_ids)
        self.lines = [self._to_m(g) for g in lines_wgs84]
        self.tree = STRtree(self.lines)
        self.max_dist_m = max_dist_m

    @staticmethod
    def _to_m(g: LineString) -> LineString:
        xs, ys = _TO_M.transform(*np.asarray(g.coords).T)
        return LineString(np.c_[xs, ys])

    @classmethod
    def from_geojson(cls, path: str | Path, max_dist_m: float = 15.0) -> "LinkSnapper":
        import geopandas as gpd
        g = gpd.read_file(path)
        return cls(g["link_id"].tolist(), list(g.geometry), max_dist_m)

    def snap(self, lon: float, lat: float) -> Snap:
        x, y = _TO_M.transform(lon, lat)
        p = Point(x, y)
        i = self.tree.query_nearest(p, max_distance=self.max_dist_m, return_distance=False)
        if len(i) == 0:
            return Snap(None, float("inf"), 0.0)
        i = int(i[0])
        line = self.lines[i]
        return Snap(self.link_ids[i], float(line.distance(p)), float(line.project(p)))

    def snap_many(self, lonlat: np.ndarray) -> list[Snap]:
        return [self.snap(float(lo), float(la)) for lo, la in lonlat]


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--area", choices=sorted(AREAS), default="sinchon")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    out = args.out or Path(f"data/links/{args.area}.geojson")
    links = fetch_osm_links(AREAS[args.area])
    out.parent.mkdir(parents=True, exist_ok=True)
    links.to_file(out, driver="GeoJSON")
    print(f"{args.area}: links={len(links)} total={links.length_m.sum() / 1000:.1f}km → {out}")
    print(links.highway.value_counts().head(8).to_string())


if __name__ == "__main__":
    main()
