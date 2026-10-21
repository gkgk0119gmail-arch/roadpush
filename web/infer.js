// 브라우저 안 추론: RF-DETR-Seg ONNX(onnxruntime-web) + 유효보행폭 비율.
// 파이썬 기준 구현(src/roadpush/width_ratio.py, scoring.analyze_frame)을 그대로 옮겼다. 상수도 동일.
"use strict";

const RP = (() => {
  const INPUT = 432, MEAN = [0.485, 0.456, 0.406], STD = [0.229, 0.224, 0.225];
  const AW = 480;                               // 분석 해상도(가로). 파이썬 1920 기준 상수를 비례 축소
  const SCALE = AW / 1920;
  const WALKABLE = new Set(["sidewalk", "braille_guide_blocks", "manhole_grating"]);
  const BLOCKING_SURFACES = new Set(["tree_zone"]);
  const OBSTACLES = new Set(["car", "truck_bus", "two_wheeler", "bollard", "pole", "barricade", "movable_signage",
    "potted_plant", "person", "other_fixed", "other_moving"]);
  const TRANSIENT = new Set(["person", "other_moving"]);
  const VEHICLES = new Set(["car", "truck_bus", "two_wheeler"]);
  const ROWS = [0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9];
  const COLORS = {
    sidewalk: [60, 180, 75], braille_guide_blocks: [255, 225, 25], roadway: [128, 128, 128], alley: [170, 110, 40],
    bike_lane: [0, 130, 200], stairs: [145, 30, 180], repair_zone: [245, 130, 48], manhole_grating: [70, 240, 240],
    tree_zone: [128, 0, 0],
  };
  const OBST_RGB = [230, 25, 75], TRANS_RGB = [190, 160, 255];
  let sessions = null, names = null;

  async function load(base, onProgress) {
    if (sessions) return;
    ort.env.wasm.wasmPaths = "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.20.1/dist/";
    const meta = await (await fetch(base + "models/meta.json")).json();
    names = meta.class_names;
    sessions = [];
    for (const [i, f] of meta.files.entries()) {
      const buf = await fetchWithProgress(base + "models/" + f, (p) => onProgress(i, meta.files.length, p));
      sessions.push(await ort.InferenceSession.create(buf, { executionProviders: ["wasm"] }));
    }
  }

  async function fetchWithProgress(url, cb) {
    const r = await fetch(url);
    const total = +r.headers.get("content-length") || 0;
    const reader = r.body.getReader(); const chunks = []; let got = 0;
    for (;;) {
      const { done, value } = await reader.read(); if (done) break;
      chunks.push(value); got += value.length; cb(total ? got / total : 0);
    }
    const out = new Uint8Array(got); let o = 0; for (const c of chunks) { out.set(c, o); o += c.length; }
    return out.buffer;
  }

  function toTensor(img) {
    const c = document.createElement("canvas"); c.width = c.height = INPUT;
    const g = c.getContext("2d"); g.drawImage(img, 0, 0, INPUT, INPUT);
    const d = g.getImageData(0, 0, INPUT, INPUT).data, n = INPUT * INPUT, x = new Float32Array(3 * n);
    for (let i = 0; i < n; i++) for (let ch = 0; ch < 3; ch++) x[ch * n + i] = (d[i * 4 + ch] / 255 - MEAN[ch]) / STD[ch];
    return new ort.Tensor("float32", x, [1, 3, INPUT, INPUT]);
  }

  // 108x108 마스크 로짓 → AW x AH 이진 마스크 (bilinear, 로짓>0)
  function upsample(logits, off, mh, mw, W, H) {
    const out = new Uint8Array(W * H);
    for (let y = 0; y < H; y++) {
      const sy = Math.min(mh - 1, Math.max(0, (y + 0.5) * mh / H - 0.5)), y0 = Math.floor(sy), y1 = Math.min(mh - 1, y0 + 1), fy = sy - y0;
      for (let x = 0; x < W; x++) {
        const sx = Math.min(mw - 1, Math.max(0, (x + 0.5) * mw / W - 0.5)), x0 = Math.floor(sx), x1 = Math.min(mw - 1, x0 + 1), fx = sx - x0;
        const a = logits[off + y0 * mw + x0], b = logits[off + y0 * mw + x1], c = logits[off + y1 * mw + x0], d = logits[off + y1 * mw + x1];
        out[y * W + x] = (a * (1 - fx) * (1 - fy) + b * fx * (1 - fy) + c * (1 - fx) * fy + d * fx * fy) > 0 ? 1 : 0;
      }
    }
    return out;
  }

  async function segment(img, threshold = 0.4) {
    const W = AW, H = Math.round(AW * img.naturalHeight / img.naturalWidth);
    const feeds = { input: toTensor(img) }, inst = [];
    for (const s of sessions) {
      const r = await s.run(feeds);
      const lg = r.labels.data, mk = r.masks.data, [, Q, C] = r.labels.dims, [, , mh, mw] = r.masks.dims;
      for (let q = 0; q < Q; q++) for (let c = 0; c < C && c < names.length; c++) {
        const p = 1 / (1 + Math.exp(-lg[q * C + c]));
        if (p > threshold) inst.push({ cls: names[c], score: p, mask: upsample(mk, q * mh * mw, mh, mw, W, H) });
      }
    }
    return { inst, W, H };
  }

  // ---------------- 유효보행폭 (width_ratio.py)
  function footpoint(m, W, H) {
    for (let y = H - 1; y >= 0; y--) {
      const xs = []; for (let x = 0; x < W; x++) if (m[y * W + x]) xs.push(x);
      if (xs.length) return [y, xs[xs.length >> 1]];
    }
    return null;
  }
  function nearWalk(walk, W, H, y, x, r) {
    for (let yy = Math.max(0, y - r); yy <= Math.min(H - 1, y + r); yy++)
      for (let xx = Math.max(0, x - r); xx <= Math.min(W - 1, x + r); xx++) if (walk[yy * W + xx]) return true;
    return false;
  }
  function onWalk(walk, list, W, H, r) {
    const out = new Uint8Array(W * H); const kept = [];
    for (const it of list) {
      const fp = footpoint(it.mask, W, H);
      if (fp && nearWalk(walk, W, H, fp[0], fp[1], r)) { for (let i = 0; i < out.length; i++) out[i] |= it.mask[i]; kept.push(it); }
    }
    return [out, kept];
  }
  function runs(a) {
    const r = []; let s = -1;
    for (let i = 0; i <= a.length; i++) { const v = i < a.length && a[i]; if (v && s < 0) s = i; if (!v && s >= 0) { r.push([s, i]); s = -1; } }
    return r;
  }
  function rowRatio(S, O, minPx, gap, minShare = 0.25) {
    let Od = O;
    if (gap > 0) { Od = new Uint8Array(O.length); for (let i = 0; i < O.length; i++) if (O[i]) for (let k = Math.max(0, i - gap); k <= Math.min(O.length - 1, i + gap); k++) Od[k] = 1; }
    const U = S.map((v, i) => v | Od[i]); let best = null, key = [-1, -1];
    for (const [a, b] of runs(U)) {
      let ns = 0; for (let i = a; i < b; i++) ns += S[i];
      if (ns > key[0] || (ns === key[0] && b - a > key[1])) { key = [ns, b - a]; best = [a, b]; }
    }
    if (!best || key[0] < minPx || key[0] < minShare * key[1]) return null;
    const [a, b] = best; let free = 0;
    for (const [s, e] of runs(Array.from({ length: b - a }, (_, i) => S[a + i] && !Od[a + i] ? 1 : 0))) free = Math.max(free, e - s);
    return free / (b - a);
  }

  function analyze(seg) {
    const { inst, W, H } = seg, N = W * H, r = Math.max(1, Math.round(15 * SCALE));
    const by = (pred) => inst.filter((i) => pred(i.cls));
    let walk = new Uint8Array(N); for (const i of by((c) => WALKABLE.has(c))) for (let k = 0; k < N; k++) walk[k] |= i.mask[k];
    const [tr] = onWalk(walk, by((c) => TRANSIENT.has(c)), W, H, r); for (let k = 0; k < N; k++) walk[k] |= tr[k];
    const [obst, kept] = onWalk(walk, by((c) => (OBSTACLES.has(c) || BLOCKING_SURFACES.has(c)) && !TRANSIENT.has(c)), W, H, r);
    const minPx = Math.max(4, Math.round(40 * SCALE)), gap = Math.round(0.01 * W);
    const ratios = [];
    for (const f of ROWS) {
      const y = Math.min(H - 1, Math.round(H * f));
      const v = rowRatio(walk.subarray(y * W, (y + 1) * W), obst.subarray(y * W, (y + 1) * W), minPx, gap);
      if (v !== null) ratios.push(v);
    }
    const present = ratios.length >= Math.ceil(0.5 * ROWS.length);
    const sorted = ratios.slice().sort((a, b) => a - b);
    const ratio = present ? (sorted[0] + (sorted.length > 1 ? sorted[1] : sorted[0])) / 2 : 0;
    const tags = []; if (!present) tags.push("vanish");
    const band0 = Math.floor(H * 0.5); let wb = 0; for (let k = band0 * W; k < N; k++) wb += walk[k];
    for (const [cls, tag] of [["repair_zone", "repair"], ["stairs", "stairs"]]) {
      let a = 0; for (const i of by((c) => c === cls)) for (let k = band0 * W; k < N; k++) a += i.mask[k];
      if (a && a / Math.max(1, wb + a) >= 0.05) tags.push(tag);
    }
    const nVeh = kept.filter((i) => VEHICLES.has(i.cls)).length;
    if (nVeh && present) tags.push("shared");
    return { ratio, present, tags, nObstacles: kept.length, nVehicles: nVeh, walk, obst };
  }

  function render(canvas, img, seg) {
    const { inst, W, H } = seg; canvas.width = W; canvas.height = H;
    const g = canvas.getContext("2d"); g.drawImage(img, 0, 0, W, H);
    const im = g.getImageData(0, 0, W, H), d = im.data;
    for (const it of inst) {
      const col = COLORS[it.cls] || (TRANSIENT.has(it.cls) ? TRANS_RGB : OBST_RGB);
      for (let k = 0; k < W * H; k++) if (it.mask[k]) {
        d[k * 4] = d[k * 4] * 0.55 + col[0] * 0.45; d[k * 4 + 1] = d[k * 4 + 1] * 0.55 + col[1] * 0.45; d[k * 4 + 2] = d[k * 4 + 2] * 0.55 + col[2] * 0.45;
      }
    }
    g.putImageData(im, 0, 0);
    g.strokeStyle = "rgba(255,255,0,.55)"; g.lineWidth = 1;
    for (const f of ROWS) { const y = Math.round(H * f) + 0.5; g.beginPath(); g.moveTo(0, y); g.lineTo(W, y); g.stroke(); }
  }

  return { load, segment, analyze, render, COLORS, OBST_RGB, TRANS_RGB };
})();
