"""신촌 촬영 계획 지도: 목적별 대상 도로를 색으로 표시 → GeoJSON + 지도 HTML.

자동 경로 연결은 하지 않는다. OSM 에서 보도가 이름 없는 footway 로 따로 그려지고 연세로 등이 조각나 있어
도로명 기반 경로가 엉뚱해짐. 촬영자는 아래 순서대로 걷고, GPX 는 aggregate 단계에서 링크에 자동 스냅된다.

순서·목적 (대비가 드러나게):
    1 연세로        기준선   차 없는 거리, 넓은 보도
    2 연세로4길·명물길·연세로2길  골목   주정차·입간판·적치물, 보도 소멸
    3 신촌로        간선     버스정류장·가로수로 보도 협소
    4 이화여대길    협소     좁은 보도·노점

사용:
    python scripts/plan_route.py --out data/links/shoot_plan.geojson --html docs/shoot_plan.html
"""
from __future__ import annotations

import argparse
from pathlib import Path

PLAN = [
    ("연세로", "기준선: 차 없는 거리·넓은 보도", "#2a9d8f"),
    ("연세로4길", "골목: 주정차·입간판·보도 소멸", "#e76f51"),
    ("명물길", "골목: 주정차·입간판·보도 소멸", "#e76f51"),
    ("연세로2길", "골목: 주정차·입간판·보도 소멸", "#e76f51"),
    ("신촌로", "간선: 버스정류장·가로수로 보도 협소", "#264653"),
    ("이화여대길", "협소: 좁은 보도·노점", "#9b5de5"),
]
CENTER = (126.9395, 37.5585)
RADIUS_DEG = 0.0065          # 약 600~700 m


def main(argv: list[str] | None = None) -> None:
    import folium
    import geopandas as gpd
    import pandas as pd

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--links", type=Path, default=Path("data/links/sinchon.geojson"))
    ap.add_argument("--out", type=Path, default=Path("data/links/shoot_plan.geojson"))
    ap.add_argument("--html", type=Path, default=Path("docs/shoot_plan.html"))
    args = ap.parse_args(argv)

    links = gpd.read_file(args.links)
    c = links.to_crs(5179).geometry.centroid.to_crs(4326)
    near = ((c.x - CENTER[0]) ** 2 + (c.y - CENTER[1]) ** 2) < RADIUS_DEG ** 2
    parts = []
    for k, (street, purpose, color) in enumerate(PLAN, start=1):
        sub = links[near & (links.name == street)].copy()
        sub["order"], sub["purpose"], sub["color"] = k, purpose, color
        parts.append(sub)
    plan = gpd.GeoDataFrame(pd.concat(parts), crs=links.crs)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    plan.to_file(args.out, driver="GeoJSON")

    m = folium.Map(location=(CENTER[1], CENTER[0]), zoom_start=16, tiles="OpenStreetMap")
    folium.GeoJson(links[near][["geometry"]], style_function=lambda _: {"color": "#999", "weight": 1}).add_to(m)
    folium.GeoJson(plan[["order", "name", "purpose", "color", "geometry"]],
                   style_function=lambda f: {"color": f["properties"]["color"], "weight": 7, "opacity": 0.85},
                   tooltip=folium.GeoJsonTooltip(["order", "name", "purpose"], ["순서", "도로", "목적"])).add_to(m)
    for k, (street, purpose, color) in enumerate(PLAN, start=1):
        g = plan[plan.name == street]
        if len(g):
            p = g.geometry.union_all().centroid
            folium.Marker((p.y, p.x), tooltip=f"{k}. {street} — {purpose}", icon=folium.DivIcon(
                html=f'<div style="font:bold 13px sans-serif;background:#fff;border:2px solid {color};'
                     f'border-radius:10px;padding:1px 6px;white-space:nowrap">{k}. {street}</div>')).add_to(m)
    args.html.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(args.html))
    print(plan.groupby(["order", "name"]).length_m.sum().round(0).to_string())
    print(f"합계 {plan.length_m.sum() / 1000:.2f} km (양쪽 보도·골목 왕복 포함 시 약 1.5~2배)")


if __name__ == "__main__":
    main()
