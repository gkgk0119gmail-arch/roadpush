"""RoadPush 대시보드 (지자체·도로관리기관 담당자용).

데이터 폴더(ROADPUSH_DATA, 기본 app/data) 아래 세션별:
    <session>/links_scored.geojson   aggregate.py 결과
    <session>/frames_linked.csv
    <session>/overlay/*.jpg
배경 링크: ROADPUSH_LINKS (기본 data/links/sinchon.geojson → app/data/links.geojson)
업로드 추론 모델: ROADPUSH_CKPT (+ ROADPUSH_SIZE)

실행: env -u PYTHONPATH streamlit run app/app.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import folium
import geopandas as gpd
import numpy as np
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from roadpush.scoring import TYPE_LABEL_KO  # noqa: E402

DATA = Path(os.environ.get("ROADPUSH_DATA", ROOT / "app" / "data"))
LINKS = Path(os.environ.get("ROADPUSH_LINKS", DATA / "links.geojson"))
CKPT = os.environ.get("ROADPUSH_CKPT", str(ROOT / "app" / "model" / "roadpush_seg.pth")).split(",")
SIZE = os.environ.get("ROADPUSH_SIZE", "medium")

GRADE_COLOR = {"위험": "#d7263d", "주의": "#f4a259", "안전": "#2a9d8f"}
CENTER = (37.5585, 126.9375)

st.set_page_config(page_title="RoadPush 보행공간 단절 위험도", page_icon="🚶", layout="wide")


# ---------------------------------------------------------------- 데이터

@st.cache_data
def sessions() -> list[str]:
    return sorted(p.parent.name for p in DATA.glob("*/links_scored.geojson"))


@st.cache_data
def load_scored(session: str) -> gpd.GeoDataFrame:
    return gpd.read_file(DATA / session / "links_scored.geojson")


@st.cache_data
def load_frames(session: str) -> pd.DataFrame:
    p = DATA / session / "frames_linked.csv"
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


@st.cache_data
def load_base_links() -> gpd.GeoDataFrame | None:
    return gpd.read_file(LINKS) if LINKS.exists() else None


def cols_for(profile: str) -> tuple[str, str, str]:
    return ("wc_score", "wc_grade", "wc_primary_type") if profile == "휠체어" else ("score", "grade", "primary_type")


# ---------------------------------------------------------------- 지도

def link_map(gdf: gpd.GeoDataFrame, score_col: str, grade_col: str, type_col: str,
             color_fn=None, tooltip_extra=None, height: int = 560):
    m = folium.Map(location=CENTER, zoom_start=16, tiles="cartodbpositron", control_scale=True)
    base = load_base_links()
    if base is not None:
        folium.GeoJson(base[["geometry"]], style_function=lambda _: {"color": "#bbbbbb", "weight": 1.5,
                                                                     "opacity": 0.6}).add_to(m)
    if len(gdf):
        g = gdf.copy()
        g["유형"] = g[type_col].map(TYPE_LABEL_KO)
        g["_color"] = [color_fn(r) if color_fn else GRADE_COLOR.get(r[grade_col], "#888") for _, r in g.iterrows()]
        fields = ["link_id", "name", score_col, grade_col, "유형", "n_frames"] + (tooltip_extra or [])
        aliases = ["링크", "도로명", "점수", "등급", "단절 유형", "프레임"] + (tooltip_extra or [])
        folium.GeoJson(
            g[fields + ["_color", "geometry"]],
            style_function=lambda f: {"color": f["properties"]["_color"], "weight": 7, "opacity": 0.9},
            highlight_function=lambda _: {"weight": 11},
            tooltip=folium.GeoJsonTooltip(fields=fields, aliases=aliases),
        ).add_to(m)
        b = g.total_bounds
        m.fit_bounds([[b[1], b[0]], [b[3], b[2]]])
    return st_folium(m, height=height, use_container_width=True, returned_objects=["last_object_clicked_tooltip"])


def clicked_link(ret) -> str | None:
    tip = (ret or {}).get("last_object_clicked_tooltip")
    if not tip:
        return None
    for line in str(tip).splitlines():
        line = line.strip()
        if line.startswith("osm_") or line.startswith("seoul_"):
            return line
    return None


# ---------------------------------------------------------------- 화면

def page_overview(session: str, profile: str, types: list[str]):
    score_col, grade_col, type_col = cols_for(profile)
    gdf = load_scored(session)
    view = gdf[gdf[type_col].isin(types)] if types else gdf

    c = st.columns(5)
    km = lambda d: d.length_m.sum() / 1000  # noqa: E731
    c[0].metric("분석 링크", f"{len(gdf)}개", f"{km(gdf):.2f} km")
    for i, g in enumerate(("위험", "주의", "안전"), start=1):
        d = gdf[gdf[grade_col] == g]
        c[i].metric(g, f"{len(d)}개", f"{km(d):.2f} km", delta_color="off")
    c[4].metric("평균 유효보행폭 비율", f"{gdf.median_ratio.mean():.2f}")

    left, right = st.columns([3, 2])
    with left:
        ret = link_map(view, score_col, grade_col, type_col)
        sel = clicked_link(ret)
        if sel:
            st.session_state["link"] = sel
    with right:
        st.subheader("조치 우선순위")
        t = view.sort_values(score_col, ascending=False)[["link_id", "name", score_col, grade_col, type_col,
                                                          "p10_ratio", "length_m"]].copy()
        t[type_col] = t[type_col].map(TYPE_LABEL_KO)
        t.columns = ["링크", "도로명", "점수", "등급", "유형", "P10 비율", "길이(m)"]
        st.dataframe(t.head(30), hide_index=True, width="stretch", height=500)
        st.download_button("CSV 내려받기", t.to_csv(index=False).encode("utf-8-sig"),
                           f"roadpush_{session}_{profile}.csv", "text/csv")


def page_detail(session: str, profile: str):
    score_col, grade_col, type_col = cols_for(profile)
    gdf = load_scored(session)
    ids = gdf.sort_values(score_col, ascending=False).link_id.tolist()
    if not ids:
        st.info("점수가 계산된 링크가 없습니다.")
        return
    cur = st.session_state.get("link")
    lid = st.selectbox("링크", ids, index=ids.index(cur) if cur in ids else 0,
                       format_func=lambda i: f"{i}  ({gdf.set_index('link_id').at[i, 'name'] or '이름 없음'})")
    r = gdf.set_index("link_id").loc[lid]
    c = st.columns(4)
    c[0].metric("점수", f"{r[score_col]:.1f}", r[grade_col], delta_color="off")
    c[1].metric("단절 유형", TYPE_LABEL_KO[r[type_col]])
    c[2].metric("P10 / 중앙 비율", f"{r.p10_ratio:.2f} / {r.median_ratio:.2f}")
    c[3].metric(f"비율<θ 프레임", f"{r.frac_below * 100:.0f}%")

    fr = load_frames(session)
    fr = fr[fr.link_id == lid] if len(fr) else fr
    if len(fr):
        st.line_chart(fr.set_index("t_sec")[["ratio"]], height=200)
        imgs = [DATA / session / "overlay" / f for f in fr.frame if (DATA / session / "overlay" / f).exists()]
        if imgs:
            st.caption("대표 프레임 (마스크 오버레이, 비율 낮은 순)")
            order = fr.set_index("frame").ratio.to_dict()
            imgs = sorted(imgs, key=lambda p: order.get(p.name, 1))[:6]
            cols = st.columns(3)
            for i, p in enumerate(imgs):
                cols[i % 3].image(str(p), caption=f"{p.name}  ratio={order.get(p.name, 0):.2f}")


def page_compare(profile: str):
    ss = sessions()
    if len(ss) < 2:
        st.info("전·후 비교에는 세션이 2개 이상 필요합니다 (같은 구간 재촬영).")
        return
    c = st.columns(2)
    a = c[0].selectbox("조치 전", ss, index=0)
    b = c[1].selectbox("조치 후", ss, index=len(ss) - 1)
    score_col, grade_col, type_col = cols_for(profile)
    A, B = load_scored(a).set_index("link_id"), load_scored(b).set_index("link_id")
    common = A.index.intersection(B.index)
    if not len(common):
        st.warning("두 세션에 공통 링크가 없습니다.")
        return
    d = B.loc[common].copy()
    d["before"] = A.loc[common, score_col]
    d["delta"] = d[score_col] - d["before"]
    d = gpd.GeoDataFrame(d.reset_index(), geometry="geometry", crs="EPSG:4326")

    def color(r):
        return "#2a9d8f" if r["delta"] <= -10 else "#d7263d" if r["delta"] >= 10 else "#999999"

    m = st.columns(3)
    m[0].metric("개선 링크(−10 이하)", int((d.delta <= -10).sum()))
    m[1].metric("악화 링크(+10 이상)", int((d.delta >= 10).sum()))
    m[2].metric("평균 변화", f"{d.delta.mean():+.1f}")
    link_map(d, score_col, grade_col, type_col, color_fn=color, tooltip_extra=["before", "delta"], height=480)
    t = d[["link_id", "name", "before", score_col, "delta"]].sort_values("delta")
    t.columns = ["링크", "도로명", "전", "후", "변화"]
    st.dataframe(t, hide_index=True, width="stretch")


@st.cache_resource
def predictor():
    from roadpush.infer import Predictor
    return Predictor(CKPT, SIZE)


def page_upload():
    st.write("보행 시점 사진을 올리면 보도·장애물을 분할하고 유효보행폭 비율을 계산합니다.")
    if not all(Path(c).exists() for c in CKPT):
        st.warning(f"모델 파일이 없습니다: {CKPT}")
        return
    f = st.file_uploader("이미지", type=["jpg", "jpeg", "png"])
    samples = sorted((ROOT / "app" / "samples").glob("*.jpg"))
    pick = st.selectbox("또는 예시 이미지", ["(선택 안 함)"] + [p.name for p in samples])
    src = f if f is not None else (ROOT / "app" / "samples" / pick if pick != "(선택 안 함)" else None)
    if src is None:
        return
    from PIL import Image
    from roadpush.infer import render_overlay
    img = np.asarray(Image.open(src).convert("RGB"))
    with st.spinner("추론 중 (CPU에서 수 초)"):
        fa, cm, _ = predictor().analyze(img)
    c = st.columns([3, 1])
    c[0].image(render_overlay(img, cm, fa), width="stretch")
    c[1].metric("유효보행폭 비율", f"{fa.ratio:.2f}")
    c[1].metric("최소 스캔라인", f"{fa.min_ratio:.2f}")
    c[1].metric("보도 위 장애물", f"{fa.n_obstacles_on_sidewalk}개")
    c[1].write("태그: " + (", ".join(TYPE_LABEL_KO[t] for t in fa.tags) or "없음"))
    c[1].json({k: len(v) for k, v in cm.items()})


# ---------------------------------------------------------------- main

st.title("RoadPush · 보행공간 단절 위험도")
st.caption("보행 촬영 영상 → AI 분할 → 유효보행폭 비율 → 도로 링크별 단절 위험도. 대상: 지자체·도로관리기관 담당자")

ss = sessions()
with st.sidebar:
    st.header("설정")
    session = st.selectbox("촬영 세션", ss) if ss else None
    profile = st.radio("판정 프로필", ["일반 보행자", "휠체어"], horizontal=True,
                       help="휠체어: 유효폭 임계 0.5→0.7, 단차·계단 가중 상향 (확장 기능)")
    types = st.multiselect("단절 유형", list(TYPE_LABEL_KO), default=list(TYPE_LABEL_KO),
                           format_func=TYPE_LABEL_KO.get)
    st.divider()
    st.caption("점수 = 100×[0.4·(1−P10 비율) + 0.3·비율<θ 프레임 비중 + 0.3·유형 가중]\n\n"
               "등급: 안전 <30 · 주의 30~60 · 위험 ≥60")

if session and session.startswith("sim_"):
    st.warning("시뮬레이션 세션: AI Hub 인도보행 영상(학습 미사용 폴더)을 신촌 링크 위 가상 보행 경로에 배치한 결과입니다. "
               "영상 분석은 실제이나 위치는 실제 촬영 위치가 아닙니다.", icon="⚠️")
tabs = st.tabs(["지도", "링크 상세", "전·후 비교", "이미지 업로드 추론"])
if session is None:
    for t in tabs[:3]:
        t.info(f"분석 결과가 없습니다: {DATA}")
else:
    with tabs[0]:
        page_overview(session, profile, types)
    with tabs[1]:
        page_detail(session, profile)
    with tabs[2]:
        page_compare(profile)
with tabs[3]:
    page_upload()
