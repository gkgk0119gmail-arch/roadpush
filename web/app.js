// RoadPush 정적 대시보드: 사전 계산된 세션 데이터(data/) + 브라우저 추론(infer.js)
"use strict";

const BASE = "./";
const GRADE_COLOR = { 위험: "#d03b3b", 주의: "#fab219", 안전: "#0ca30c" };
const TYPE_KO = { noview: "바닥이 보이지 않음(측정 불가)", vanish: "보도 소멸", narrow: "폭 협소", repair: "공사·파손", stairs: "단차·계단", shared: "보차 혼용", none: "이상 없음" };
const state = { sessions: [], s: null, profile: "ped", links: null, frames: {}, memos: {}, layer: null, base: null, sel: null };
const $ = (q) => document.querySelector(q);
const esc = (t) => String(t == null ? "" : t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// ---------------- 탭
document.querySelectorAll("#tabs button").forEach((b) => b.onclick = () => showTab(b.dataset.tab));
function showTab(t) {
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === t));
  document.querySelectorAll(".tab").forEach((s) => s.classList.toggle("on", s.id === "tab-" + t));
  if (t === "map" && map) setTimeout(() => map.invalidateSize(), 50);
}
document.querySelectorAll("#profile button").forEach((b) => b.onclick = () => {
  state.profile = b.dataset.p;
  document.querySelectorAll("#profile button").forEach((x) => x.classList.toggle("on", x === b));
  renderAll();
});

// ---------------- 데이터
const map = L.map("map", { zoomControl: true }).setView([37.564, 126.988], 16);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap contributors" }).addTo(map);
const legend = L.control({ position: "bottomleft" });
legend.onAdd = () => {
  const d = L.DomUtil.create("div", "maplegend");
  d.innerHTML = Object.entries(GRADE_COLOR).map(([g, c]) => `<div><i style="background:${c}"></i>${g}</div>`).join("") +
    '<div><i style="background:#9c9a92;height:3px"></i>촬영 안 됨(측정 불가)</div>';
  return d;
};
legend.addTo(map);

async function init() {
  const meta = await (await fetch(BASE + "data/sessions.json")).json();
  state.sessions = meta.sessions;
  const sel = $("#session");
  sel.innerHTML = meta.sessions.map((s) => `<option value="${s.id}">${esc(s.title)}</option>`).join("");
  sel.onchange = () => loadSession(sel.value);
  state.base = await (await fetch(BASE + "data/base_links.geojson")).json();
  L.geoJSON(state.base, { style: { color: "#9c9a92", weight: 1.2, opacity: 0.6 }, interactive: false }).addTo(map);
  $("#method").innerHTML = meta.method_html;
  $("#samples").innerHTML = (meta.samples || []).map((f) => `<button data-s="${f}">예시 ${esc(f.split("/").pop())}</button>`).join("");
  document.querySelectorAll("#samples button").forEach((b) => b.onclick = () => runUpload(BASE + b.dataset.s));
  await loadSession(meta.sessions[0].id);
}

async function loadSession(id) {
  state.s = state.sessions.find((s) => s.id === id);
  const p = BASE + "data/" + id + "/";
  const [links, frames, memos] = await Promise.all([
    fetch(p + "links.geojson").then((r) => r.json()),
    fetch(p + "frames.json").then((r) => r.json()),
    fetch(p + "memos.json").then((r) => r.ok ? r.json() : {}).catch(() => ({})),
  ]);
  Object.assign(state, { links, frames, memos, sel: null });
  $("#attrib").innerHTML = state.s.attribution ? "거리 사진: © Mapillary contributors, CC BY-SA 4.0 (실제 촬영 위치)" :
    (state.s.simulation ? '<span class="warn">시뮬레이션: 위치는 가상</span>' : "");
  renderAll(true);
}

// ---------------- 지도·통계·우선순위
const F = () => state.profile === "wc" ? { s: "wc_score", g: "wc_grade", t: "wc_primary_type" } : { s: "score", g: "grade", t: "primary_type" };

function renderAll(fit) {
  const f = F(), feats = state.links.features;
  if (state.layer) map.removeLayer(state.layer);
  state.layer = L.geoJSON(state.links, {
    style: (ft) => ({ color: GRADE_COLOR[ft.properties[f.g]] || "#888", weight: 7, opacity: 0.9 }),
    onEachFeature: (ft, layer) => {
      const p = ft.properties;
      layer.bindTooltip(`<b>${esc(p.name || "이름 없음")}</b><br>${p[f.s].toFixed(0)}점 · ${p[f.g]} · ${TYPE_KO[p[f.t]]}<br>공간: ${esc(p.space_type_ko || "-")}`);
      layer.on("click", () => selectLink(p.link_id));
    },
  }).addTo(map);
  if (fit) map.fitBounds(state.layer.getBounds(), { padding: [20, 20] });
  const km = (arr) => (arr.reduce((a, x) => a + x.properties.length_m, 0) / 1000).toFixed(2);
  const by = (g) => feats.filter((x) => x.properties[f.g] === g);
  const shared = feats.filter((x) => x.properties.space_type === "shared").length;
  $("#stats").innerHTML = [
    ["분석 링크", `${feats.length}개`, `${km(feats)} km`],
    ["위험", `${by("위험").length}개`, `${km(by("위험"))} km`],
    ["주의", `${by("주의").length}개`, `${km(by("주의"))} km`],
    ["안전", `${by("안전").length}개`, `${km(by("안전"))} km`],
    ["보차 혼용", `${shared}개`, "보행 공간 안 차량"],
  ].map(([l, v, s]) => `<div class="stat"><div class="l">${l}</div><div class="v">${v}</div><div class="l">${s}</div></div>`).join("");
  const rows = feats.slice().sort((a, b) => b.properties[f.s] - a.properties[f.s]).slice(0, 25);
  $("#prio tbody").innerHTML = rows.map((x) => {
    const p = x.properties;
    return `<tr data-id="${p.link_id}"><td>${esc(p.name || "이름 없음")}</td><td>${p[f.s].toFixed(0)}</td>
      <td><span class="badge ${p[f.g]}">${p[f.g]}</span></td><td>${TYPE_KO[p[f.t]]}</td></tr>`;
  }).join("");
  document.querySelectorAll("#prio tbody tr").forEach((tr) => tr.onclick = () => selectLink(tr.dataset.id, true));
  if (state.sel) renderDetail(state.sel);
}

function selectLink(id, go) {
  state.sel = id; renderDetail(id);
  if (go) showTab("detail");
}

// ---------------- 링크 상세
function spark(fr) {
  // 가로축 = 촬영 순서(프레임 번호). 한 링크에 여러 날 촬영이 섞이면 시간축은 뭉개진다.
  if (!fr.length) return "";
  const d = fr.slice().sort((a, b) => a.t - b.t);
  const W = 640, H = 140, pl = 34, pr = 12, pt = 10, pb = 22, n = Math.max(1, d.length - 1);
  const x = (i) => pl + (W - pl - pr) * i / n, y = (r) => pt + (H - pt - pb) * (1 - r);
  const pts = d.map((v, i) => `${x(i).toFixed(1)},${y(v.r).toFixed(1)}`).join(" ");
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:760px;height:auto" role="img" aria-label="유효보행폭 비율 타임라인">
    ${[0, 0.5, 1].map((g) => `<line x1="${pl}" x2="${W - pr}" y1="${y(g)}" y2="${y(g)}" stroke="#e4e3df"/><text x="${pl - 6}" y="${y(g) + 4}" text-anchor="end">${g.toFixed(1)}</text>`).join("")}
    <line x1="${pl}" x2="${W - pr}" y1="${y(0.5)}" y2="${y(0.5)}" stroke="#d03b3b" stroke-dasharray="4 4" opacity=".7"/>
    <text x="${W - pr}" y="${y(0.5) - 5}" text-anchor="end">θ 0.5</text>
    <polyline points="${pts}" fill="none" stroke="#2a78d6" stroke-width="2"/>
    ${d.map((v, i) => `<circle cx="${x(i).toFixed(1)}" cy="${y(v.r).toFixed(1)}" r="4" fill="#2a78d6" stroke="#fcfcfb" stroke-width="2"><title>${v.f} 비율 ${v.r.toFixed(2)}</title></circle>`).join("")}
    <text x="${pl}" y="${H - 5}">촬영 순서 →  (${d.length}프레임)</text></svg>`;
}

function renderDetail(id) {
  const ft = state.links.features.find((x) => x.properties.link_id === id);
  if (!ft) return;
  // 측정 불가(바닥 안 보임) 프레임은 점수 계산에서 빠지므로 화면에서도 뺀다
  const p = ft.properties, f = F(), fr = (state.frames[id] || []).filter((d) => !(d.tags || "").includes("noview")), m = state.memos[id];
  const thumbs = fr.slice().sort((a, b) => a.r - b.r).slice(0, 6);
  $("#detail").innerHTML = `
    <h2>${esc(p.name || "이름 없음")} <span class="badge ${p[f.g]}">${p[f.g]}</span></h2>
    <div class="statgrid">${[
      ["점수", p[f.s].toFixed(1)], ["단절 유형", TYPE_KO[p[f.t]]], ["공간 유형", p.space_type_ko || "-"],
      ["하위10% / 중앙 비율", `${p.p10_ratio.toFixed(2)} / ${p.median_ratio.toFixed(2)}`],
      ["비율<0.5 프레임", `${(p.frac_below * 100).toFixed(0)}%`], ["프레임", p.n_frames],
    ].map(([l, v]) => `<div class="stat"><div class="l">${l}</div><div class="v" style="font-size:20px">${esc(v)}</div></div>`).join("")}</div>
    ${p.median_free_width_m != null ? `<p class="muted small">보조 지표(카메라 높이 1.3 m 가정): 통과 가능 폭 중앙값 ${p.median_free_width_m.toFixed(2)} m · 1.2 m 미만 ${(p.frac_below_legal * 100).toFixed(0)}%</p>` : ""}
    ${m && m.cause ? `<div class="memo"><b>AI 점검 메모</b> (${esc(m.priority || "-")})<br>원인: ${esc(m.cause)}<br>권고: ${esc(m.action)}
      <div class="muted small">멀티모달 LLM(Qwen3-VL-8B)이 측정값·대표 프레임을 근거로 작성. 분할·LLM 모두 확인한 요소: ${esc((m.confirmed || []).join(", ") || "없음")}</div></div>` : ""}
    <h3>유효보행폭 비율 (촬영 순서)</h3>${spark(fr)}
    <h3>대표 프레임 (비율 낮은 순)</h3>
    <div class="thumbs">${thumbs.map((d) => `<figure><img loading="lazy" src="${BASE}data/${state.s.id}/overlay/${d.f}" alt="${d.f}">
      <figcaption>${d.f} · 비율 ${d.r.toFixed(2)} ${d.tags ? "· " + esc(d.tags) : ""}</figcaption></figure>`).join("")}</div>`;
}

// ---------------- 사진 분석 (브라우저 추론)
let modelsReady = null;
$("#file").onchange = (e) => { const f = e.target.files[0]; if (f) runUpload(URL.createObjectURL(f)); };
async function runUpload(src) {
  const st = $("#ustatus");
  try {
    if (!modelsReady) {
      modelsReady = RP.load(BASE, (i, n, p) => st.textContent = `AI 모델 내려받는 중 ${i + 1}/${n} … ${(p * 100).toFixed(0)}%`);
    }
    await modelsReady;
    const img = new Image(); img.crossOrigin = "anonymous"; img.src = src; await img.decode();
    st.textContent = "분석 중 (브라우저 CPU, 수 초~수십 초)…";
    const t = performance.now(); const seg = await RP.segment(img); const a = RP.analyze(seg);
    RP.render($("#ucanvas"), img, seg);
    const cnt = {}; seg.inst.forEach((i) => cnt[i.cls] = (cnt[i.cls] || 0) + 1);
    st.textContent = `완료 (${((performance.now() - t) / 1000).toFixed(1)}초)`;
    $("#uresult").innerHTML = `
      <div class="stat"><div class="l">유효보행폭 비율(병목)</div><div class="v">${a.present ? a.ratio.toFixed(2) : a.tags.includes("noview") ? "측정 불가" : "보도 없음"}</div></div>
      <p>단절 태그: ${a.tags.map((x) => TYPE_KO[x]).join(", ") || "없음"}<br>보도 위 장애물 ${a.nObstacles}개 · 보행 공간 안 차량 ${a.nVehicles}대</p>
      <div class="legend">${Object.entries({ 보도: RP.COLORS.sidewalk, 차도: RP.COLORS.roadway, 골목: RP.COLORS.alley, 점자블록: RP.COLORS.braille_guide_blocks,
        "맨홀·배수구": RP.COLORS.manhole_grating, 장애물: RP.OBST_RGB, "보행자(제외)": RP.TRANS_RGB }).map(([k, c]) => `<span><i style="background:rgb(${c})"></i>${k}</span>`).join("")}</div>
      <p class="muted small">검출: ${Object.entries(cnt).map(([k, v]) => `${k} ${v}`).join(", ") || "없음"}<br>노란 선 = 폭을 재는 스캔라인</p>`;
  } catch (err) {
    st.textContent = "오류: " + err.message; console.error(err); modelsReady = null;
  }
}

init().catch((e) => { $("#stats").innerHTML = `<p>데이터를 불러오지 못했습니다: ${esc(e.message)}</p>`; });
