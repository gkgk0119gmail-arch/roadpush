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

import json
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

GRADE_COLOR = {"위험": "#d03b3b", "주의": "#fab219", "안전": "#0ca30c"}   # 상태색(dataviz 참조 팔레트), 툴팁에 등급 라벨 병기
CENTER = (37.5640, 126.9880)   # 데이터가 있으면 fit_bounds 로 덮어씀

st.set_page_config(page_title="RoadPush 보행공간 단절 위험도", page_icon="🚶", layout="wide")


# ---------------------------------------------------------------- 데이터

@st.cache_data
def sessions() -> list[str]:
    return sorted(p.parent.name for p in DATA.glob("*/links_scored.geojson"))


@st.cache_data
def load_scored(session: str) -> gpd.GeoDataFrame:
    return gpd.read_file(DATA / session / "links_scored.geojson")


@st.cache_data
def load_vlm(session: str) -> dict:
    p = DATA / session / "links_vlm.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


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
    m = folium.Map(location=CENTER, zoom_start=16, tiles="OpenStreetMap", control_scale=True)
    base = load_base_links()
    if base is not None:
        folium.GeoJson(base[["geometry"]], style_function=lambda _: {"color": "#bbbbbb", "weight": 1.5,
                                                                     "opacity": 0.6}).add_to(m)
    if len(gdf):
        g = gdf.copy()
        g["유형"] = g[type_col].map(TYPE_LABEL_KO)
        g["_color"] = [color_fn(r) if color_fn else GRADE_COLOR.get(r[grade_col], "#888") for _, r in g.iterrows()]
        g["공간"] = g["space_type_ko"] if "space_type_ko" in g else "-"
        fields = ["link_id", "name", score_col, grade_col, "유형", "공간", "n_frames"] + (tooltip_extra or [])
        aliases = ["링크", "도로명", "점수", "등급", "단절 유형", "공간 유형", "프레임"] + (tooltip_extra or [])
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
    c[1].metric("단절 유형", TYPE_LABEL_KO[r[type_col]], r.get("space_type_ko", ""), delta_color="off")
    c[2].metric("P10 / 중앙 비율", f"{r.p10_ratio:.2f} / {r.median_ratio:.2f}")
    c[3].metric(f"비율<θ 프레임", f"{r.frac_below * 100:.0f}%")
    if "median_free_width_m" in r and pd.notna(r.get("median_free_width_m")):
        st.caption(f"보조 지표(카메라 높이 1.3 m 가정): 통과 가능 폭 중앙값 {r.median_free_width_m:.2f} m · "
                   f"법정 유효폭 1.2 m 미만 프레임 {r.frac_below_legal * 100:.0f}% (절대폭 추정 가능 프레임 기준)")

    vlm = load_vlm(session)
    v = vlm.get("links", {}).get(lid)
    if v and v.get("memo"):
        m = v["memo"]
        st.info(f"**AI 점검 메모** ({m.get('priority', '-')})\n\n"
                f"- 원인: {m.get('cause', '-')}\n- 권고: {m.get('action', '-')}")
        conf = sorted({c for f in v["frames"] for c in f["confirmed"]})
        st.caption(f"멀티모달 LLM({vlm['meta']['model'].split('/')[-1]})이 측정값과 대표 프레임을 근거로 작성. "
                   f"세그멘테이션·LLM 모두 확인한 요소: {', '.join(conf) or '없음'} · "
                   f"세션 전체 세그–LLM 일치율 {vlm['meta']['seg_vlm_agreement']}")

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


METHOD_MD = """
#### 무엇을 재나
**유효보행폭 비율** = 실제로 지나갈 수 있는 최대 폭 ÷ 원래 보도 폭 (0~1). 화면 하단 여러 가로줄(스캔라인)에서 재고,
가장 좁은 두 줄의 평균(**병목**)을 프레임 값으로 쓴다. 원근 때문에 m 대신 **비율**이 기본(제안자 답변).
장애물 좌우에는 화면 폭 1%의 통과 여유를 둔다. **보행자·유모차 등 지나가는 사람은 장애물로 세지 않는다**(조치 대상 아님).

#### 단절 유형
| 유형 | 판정 |
|---|---|
| 보도 소멸 | 보도가 3프레임(≈3.6 m) 이상 연속으로 안 보임 (그보다 짧으면 횡단으로 보고 제외) |
| 폭 협소 | 비율 < θ(일반 0.5, 휠체어 0.7) 프레임이 20% 이상 |
| 공사·파손 / 단차·계단 | 하단 영역에서 해당 면 비중 ≥ 5% 프레임이 20% 이상 |
| 보차 혼용 | 보행 공간 안 차량·이륜차 프레임 비중 ≥ 30% (OSM 상 보도 분리 불확실 도로는 15%) |

**링크 점수** = 100 × [0.4·(1 − 하위10% 비율) + 0.3·(비율<θ 프레임 비중) + 0.3·유형 가중], 안전 <30 · 주의 30~60 · 위험 ≥60.
보조 지표: 카메라 높이 1.3 m 가정 절대 통과 폭, 법정 유효폭 1.2 m 미만 비중(점수 미반영).

#### 모델
- **RF-DETR-Seg Medium**(Apache 2.0, 35.7M) — AI Hub 인도보행 영상으로 파인튜닝. 보도면 9종 + 장애물 11종.
- **SAM 3**(teacher) — 텍스트 프롬프트 zero-shot 으로 결측 라벨 보강·비교. 배포물에 포함하지 않음.
- **Qwen3-VL**(Apache 2.0) — 측정값을 근거로 점검 메모 작성, 닫힌 질문으로 분할 결과와 교차검증. 메모는 사전 생성.

#### 데이터·출처
- 학습: AI Hub 인도보행 영상(한국지능정보사회진흥원), 이용약관 범위 내 사용.
- 거리 사진: © Mapillary contributors, **CC BY-SA 4.0** (얼굴·번호판 자동 블러).
- 보행 링크·지도: © OpenStreetMap contributors, **ODbL**.

#### 한계
- 공개 거리 사진은 촬영 시점·경로가 제각각이라 같은 구간의 전·후 비교에는 재촬영이 필요.
- 계단(학습 187건)·공사 구간은 학습 데이터가 적어 상대적으로 약함.
- 절대폭(m)은 카메라 높이 가정에 의존 → 참고용.
"""


def page_method():
    st.markdown(METHOD_MD)


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

if session and (DATA / session / "attribution.json").exists():
    st.caption("거리 사진: © Mapillary contributors, CC BY-SA 4.0 (보행 시퀀스, 실제 촬영 위치). "
               "얼굴·번호판은 Mapillary 자동 블러 처리.")
if session and session.startswith("sim_"):
    st.warning("시뮬레이션 세션: AI Hub 인도보행 영상(학습 미사용 폴더)을 신촌 링크 위 가상 보행 경로에 배치한 결과입니다. "
               "영상 분석은 실제이나 위치는 실제 촬영 위치가 아닙니다.", icon="⚠️")
tabs = st.tabs(["지도", "링크 상세", "전·후 비교", "이미지 업로드 추론", "방법·출처"])
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
with tabs[4]:
    page_method()
