"""정적 웹앱(HF Static Space, 무료) 배포 폴더 생성: web/* + 사전 계산 데이터 + ONNX 모델.

HF Spaces 는 Gradio/Docker 를 무료 CPU 에서 더 이상 호스팅하지 않음(PRO 필요) → 서버 없는 정적 사이트.
업로드 분석은 onnxruntime-web 으로 브라우저 안에서 실행(web/infer.js, 파이썬 width_ratio 와 동일 로직).

사용:
    python scripts/build_static.py --out dist/static \
        --session mly_junggu_2025:"명동 2025 (Mapillary 실사진)" --session mly_junggu_2017:"을지로 2017 (Mapillary 실사진)" \
        --links data/links/jung_gu.geojson --onnx outputs/onnx/surface/rfdetr-seg-medium.onnx outputs/onnx/obstacle/rfdetr-seg-medium.onnx
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEEP = ["link_id", "name", "highway", "length_m", "n_frames", "score", "grade", "primary_type", "primary_type_ko",
        "space_type", "space_type_ko", "p10_ratio", "median_ratio", "frac_below", "wc_score", "wc_grade",
        "wc_primary_type", "median_free_width_m", "frac_below_legal"]

README = """---
title: RoadPush 보행공간 단절 위험도
emoji: 🚶
colorFrom: green
colorTo: red
sdk: static
pinned: false
license: apache-2.0
---

RoadPush — 보행 촬영 영상으로 도로 링크별 유효보행폭 비율과 단절 위험도를 산출하는 PoC
(2026 AI 라이프 솔루션 챌린지). 서버 없는 정적 웹앱: 분석 결과는 사전 계산, 사진 분석은 브라우저(onnxruntime-web)에서 실행.
"""

METHOD_HTML = """
<h3>무엇을 재나</h3>
<p><b>유효보행폭 비율</b> = 실제로 지나갈 수 있는 최대 폭 ÷ 원래 보도 폭 (0~1). 화면 하단 여러 가로줄(스캔라인)에서 재고,
가장 좁은 두 줄의 평균(<b>병목</b>)을 프레임 값으로 쓴다. 원근 때문에 m 대신 <b>비율</b>이 기본(아이디어 제안자 답변).
장애물 좌우에는 화면 폭 1%의 통과 여유를 둔다. <b>보행자·유모차 등 지나가는 사람은 장애물로 세지 않는다</b>(조치 대상 아님).</p>
<h3>단절 유형</h3>
<table><tr><th>유형</th><th>판정</th></tr>
<tr><td>보도 소멸</td><td>보도가 3프레임(≈3.6 m) 이상 연속으로 안 보임 (짧으면 횡단으로 보고 제외)</td></tr>
<tr><td>폭 협소</td><td>비율 &lt; θ(일반 0.5, 휠체어 0.7) 프레임이 20% 이상</td></tr>
<tr><td>공사·파손 / 단차·계단</td><td>하단 영역에서 해당 면 비중 ≥ 5% 프레임이 20% 이상</td></tr>
<tr><td>보차 혼용</td><td>보행 공간 안 차량·이륜차 프레임 비중 ≥ 30% (OSM 상 보도 분리 불확실 도로는 15%)</td></tr></table>
<p><b>링크 점수</b> = 100 × [0.4·(1 − 하위10% 비율) + 0.3·(비율&lt;θ 프레임 비중) + 0.3·유형 가중] · 안전 &lt;30 · 주의 30~60 · 위험 ≥60</p>
<h3>모델</h3>
<ul><li><b>RF-DETR-Seg Medium</b>(Apache 2.0) 두 개 — 보도면 9종, 장애물 11종. AI Hub 인도보행 영상으로 파인튜닝.
AI Hub 검증셋(촬영 폴더 단위 분리)에서 유효보행폭 비율 오차 0.017, 장애물 mIoU 0.74.</li>
<li><b>SAM 3</b> — 라벨링 teacher·zero-shot 비교용(비율 오차 0.11). 배포물 미포함.</li>
<li><b>Qwen3-VL-8B</b>(Apache 2.0) — 측정값을 근거로 점검 메모 작성, 분할 결과와 교차검증한 사실만 사용. 메모는 사전 생성.</li></ul>
<h3>데이터·출처</h3>
<ul><li>학습: AI Hub 인도보행 영상(한국지능정보사회진흥원)</li>
<li>거리 사진: © Mapillary contributors, CC BY-SA 4.0 (얼굴·번호판 자동 블러)</li>
<li>보행 링크·지도: © OpenStreetMap contributors, ODbL</li></ul>
<h3>한계</h3>
<ul><li>공개 거리 사진은 촬영 시점·경로가 제각각이라 같은 구간 전·후 비교는 재촬영 필요</li>
<li>계단 등 학습 데이터가 적은 유형은 상대적으로 약함 · 절대폭(m)은 카메라 높이 가정에 의존(참고용)</li>
<li>브라우저 분석은 기기 성능에 따라 수 초~수십 초</li></ul>
"""


def _round_geom(g):
    def r(c):
        return [round(c[0], 6), round(c[1], 6)] if isinstance(c[0], (int, float)) else [r(x) for x in c]
    return {**g, "coordinates": r(g["coordinates"])}


def nearby_names(gj: dict, base_links: Path, max_m: float = 50.0) -> dict[str, str]:
    """이름 없는 링크(OSM 보행로·골목) → 가장 가까운 이름 있는 링크의 도로명 + ' 인근'. 담당자가 위치를 알아보게."""
    import geopandas as gpd
    from shapely.geometry import shape

    named = gpd.read_file(base_links)
    named = named[named["name"].fillna("") != ""].to_crs(5179)
    tree = named.sindex
    out = {}
    for f in gj["features"]:
        p = f["properties"]
        if p.get("name"):
            continue
        g = gpd.GeoSeries([shape(f["geometry"])], crs=4326).to_crs(5179).iloc[0]
        idx = tree.query(g.buffer(max_m))
        if len(idx):
            cand = named.iloc[idx]
            near = cand.iloc[cand.distance(g).argmin()]
            out[p["link_id"]] = f"{near['name']} 인근"
    return out


def build_session(src: Path, out: Path, width: int, base_links: Path | None = None) -> int:
    from PIL import Image

    out.mkdir(parents=True, exist_ok=True)
    gj = json.loads((src / "links_scored.geojson").read_text())
    fill = nearby_names(gj, base_links) if base_links else {}
    feats = []
    for f in gj["features"]:
        p = {k: f["properties"].get(k) for k in KEEP}
        if not p.get("name") and p["link_id"] in fill:
            p["name"] = fill[p["link_id"]]
        feats.append({"type": "Feature", "properties": p, "geometry": _round_geom(f["geometry"])})
    (out / "links.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))

    frames = defaultdict(list)
    with open(src / "frames_linked.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["link_id"]:
                frames[r["link_id"]].append({"f": r["frame"], "t": float(r["t_sec"]), "r": float(r["ratio"]),
                                             "tags": r.get("tags", "")})
    (out / "frames.json").write_text(json.dumps(frames, ensure_ascii=False))

    vlm = src / "links_vlm.json"
    if vlm.exists():
        d = json.loads(vlm.read_text())["links"]
        memos = {k: {**v.get("memo", {}), "confirmed": sorted({c for fr in v.get("frames", []) for c in fr["confirmed"]})}
                 for k, v in d.items() if v.get("memo")}
        (out / "memos.json").write_text(json.dumps(memos, ensure_ascii=False))

    used = {d["f"] for lst in frames.values() for d in lst}
    od = out / "overlay"
    od.mkdir(exist_ok=True)
    n = 0
    for fn in sorted(used):
        p = src / "overlay" / fn
        if p.exists():
            im = Image.open(p).convert("RGB")
            im.resize((width, round(im.height * width / im.width))).save(od / fn, quality=72)
            n += 1
    if (src / "attribution.json").exists():
        shutil.copy2(src / "attribution.json", out / "attribution.json")
    return n


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "dist" / "static")
    ap.add_argument("--session", action="append", required=True, help="<app/data 세션 id>:<제목>")
    ap.add_argument("--data", type=Path, default=ROOT / "app" / "data")
    ap.add_argument("--links", type=Path, default=ROOT / "data/links/downtown.geojson",
                    help="배경 링크 + 이름 없는 링크의 인근 도로명 조회용")
    ap.add_argument("--onnx", nargs="+", type=Path, required=True)
    ap.add_argument("--meta", type=Path, default=ROOT / "outputs/onnx/meta.json")
    ap.add_argument("--samples", nargs="*", type=Path, default=[])
    ap.add_argument("--width", type=int, default=480)   # HF Space 1 GB 한도
    args = ap.parse_args(argv)

    out = args.out
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "web", out)
    data = out / "data"
    data.mkdir()
    base = json.loads(args.links.read_text())
    base = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {},
                                                        "geometry": _round_geom(f["geometry"])} for f in base["features"]]}
    (data / "base_links.geojson").write_text(json.dumps(base))
    sessions = []
    for spec in args.session:
        sid, _, title = spec.partition(":")
        n = build_session(args.data / sid, data / sid, args.width, args.links)
        sessions.append({"id": sid, "title": title or sid, "attribution": (args.data / sid / "attribution.json").exists(),
                         "simulation": sid.startswith("sim_")})
        print(f"  {sid}: overlay {n}장")
    samples = []
    (out / "samples").mkdir()
    for s in args.samples:
        shutil.copy2(s, out / "samples" / s.name)
        samples.append(f"samples/{s.name}")
    (data / "sessions.json").write_text(json.dumps({"sessions": sessions, "method_html": METHOD_HTML, "samples": samples},
                                                   ensure_ascii=False))
    md = out / "models"
    md.mkdir()
    files = []
    for i, p in enumerate(args.onnx):
        name = f"model_{i}.onnx"
        shutil.copy2(p, md / name)
        files.append(name)
    meta = json.loads(args.meta.read_text())
    (md / "meta.json").write_text(json.dumps({**meta, "files": files}, ensure_ascii=False))
    (out / "README.md").write_text(README, encoding="utf-8")
    (out / ".gitattributes").write_text("*.onnx filter=lfs diff=lfs merge=lfs -text\n*.jpg filter=lfs diff=lfs merge=lfs -text\n")
    total = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(f"정적 사이트: {out} ({total / 2**20:.0f} MB)")


if __name__ == "__main__":
    main()
