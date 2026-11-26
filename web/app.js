"use strict";

const state = {
  scenes: [],
  scene: "duct_strip",
  res: 12,
  scale: 1.0,
  offset: [0, 0, 0],
  data: null,        // /api/voxelize 响应
  conn: null,        // /api/connectivity 响应
  selectedTri: 0,
  highlightVoxels: new Set(),  // "i,j,k"
  highlightVoxel: null,
  layer: Infinity,
};

const $ = (id) => document.getElementById(id);
const AXIS_NAMES = ["x", "y", "z"];

function showError(msg) {
  const b = $("error-banner");
  b.hidden = !msg;
  b.textContent = msg || "";
}

async function api(path, payload) {
  const resp = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
  return data;
}

async function loadScenes() {
  const resp = await fetch("/api/scenes");
  const data = await resp.json();
  state.scenes = data.scenes;
  const sel = $("scene");
  sel.innerHTML = "";
  for (const s of data.scenes) {
    const opt = document.createElement("option");
    opt.value = s.key;
    opt.textContent = s.name;
    sel.appendChild(opt);
  }
  sel.value = state.scene;
  onSceneMeta();
}

function onSceneMeta() {
  const meta = state.scenes.find((s) => s.key === state.scene);
  if (!meta) return;
  $("scene-desc").textContent = meta.description;
  $("res").disabled = meta.fixed_res;
  $("scale").disabled = !meta.scalable;
  $("res").value = meta.res;
  $("budget").parentElement.style.opacity = meta.has_connectivity ? 1 : 0.4;
  $("measure").disabled = !meta.has_connectivity;
}

async function regenerate() {
  showError("");
  state.conn = null;
  $("conn-result").textContent = "（未测量）";
  $("conn-result").className = "kv dim";
  try {
    const payload = {
      scene: state.scene,
      res: parseInt($("res").value, 10),
      offset: state.offset,
    };
    if (!$("scale").disabled) payload.scale = parseFloat($("scale").value);
    state.data = await api("/api/voxelize", payload);
    if (state.selectedTri >= state.data.triangles.length) state.selectedTri = 0;
    state.layer = Infinity;
    renderAll();
  } catch (e) {
    showError("体素化失败: " + e.message);
  }
}

function renderAll() {
  const d = state.data;
  if (!d) return;
  renderStats();
  renderTriSelect();
  renderRaster();
  renderVoxels();
  renderFaces();
  renderVoxelList();
}

function renderStats() {
  const d = state.data;
  const s = d.stats;
  const v = d.verification;
  const missedCls = v.missed.length ? "bad" : "ok";
  $("stats").innerHTML =
    `必交体素 must: <b>${s.must}</b>\n` +
    `可能交 may: <b>${s.may}</b>（含保守伪占用 may_only: <b class="${s.may_only ? "warn" : ""}">${s.may_only}</b>）\n` +
    `退化三角形: <b>${s.degenerate}</b>\n` +
    `参考对照: 漏标 <b class="${missedCls}">${v.missed.length}</b>，` +
    `多标 <b>${v.extra.length}</b>，参考体素 ${v.reference_count}\n` +
    `<span class="dim">${d.note}</span>`;
}

function renderTriSelect() {
  const d = state.data;
  const sel = $("tri-select");
  sel.innerHTML = "";
  d.raster.forEach((r, idx) => {
    const opt = document.createElement("option");
    opt.value = idx;
    opt.textContent = r.degenerate ? `面 #${r.tri}（退化）` : `面 #${r.tri}`;
    sel.appendChild(opt);
  });
  sel.value = state.selectedTri;
}

// ---------- 光栅调试视窗 ----------

function rasterTransform(d, r) {
  const cv = $("raster");
  const [u, v] = r.uv;
  const ou = d.grid.origin[u], ov = d.grid.origin[v];
  const eu = d.grid.n[u] * d.grid.cell, ev = d.grid.n[v] * d.grid.cell;
  const pad = 36;
  const s = Math.min((cv.width - 2 * pad) / eu, (cv.height - 2 * pad) / ev);
  return {
    s, u, v, ou, ov,
    x: (wu) => pad + (wu - ou) * s,
    y: (wv) => cv.height - pad - (wv - ov) * s,
    invX: (px) => ou + (px - pad) / s,
    invY: (py) => ov + (cv.height - pad - py) / s,
  };
}

function renderRaster() {
  const d = state.data;
  const r = d.raster[state.selectedTri];
  const cv = $("raster");
  const ctx = cv.getContext("2d");
  ctx.clearRect(0, 0, cv.width, cv.height);
  if (!r || r.degenerate) {
    ctx.fillStyle = "#8b98b5";
    ctx.font = "13px monospace";
    ctx.fillText("该三角形为退化投影，已走包围盒解析回退（无 2D 光栅）", 20, 30);
    $("raster-info").textContent = "退化回退";
    return;
  }
  const t = rasterTransform(d, r);
  const h = d.grid.cell;

  // 空间格
  ctx.strokeStyle = "#1c2740";
  ctx.lineWidth = 1;
  for (let i = 0; i <= d.grid.n[t.u]; i++) {
    const x = t.x(d.grid.origin[t.u] + i * h);
    ctx.beginPath(); ctx.moveTo(x, t.y(d.grid.origin[t.v]));
    ctx.lineTo(x, t.y(d.grid.origin[t.v] + d.grid.n[t.v] * h)); ctx.stroke();
  }
  for (let j = 0; j <= d.grid.n[t.v]; j++) {
    const y = t.y(d.grid.origin[t.v] + j * h);
    ctx.beginPath(); ctx.moveTo(t.x(d.grid.origin[t.u]), y);
    ctx.lineTo(t.x(d.grid.origin[t.u] + d.grid.n[t.u] * h), y); ctx.stroke();
  }

  // 保守覆盖像素
  for (const p of r.pixels) {
    const x0 = t.x(d.grid.origin[t.u] + p.i * h);
    const y0 = t.y(d.grid.origin[t.v] + (p.j + 1) * h);
    ctx.fillStyle = p.exact ? "rgba(59,130,246,0.45)" : "rgba(239,68,68,0.5)";
    ctx.fillRect(x0, y0, t.s * h, t.s * h);
  }
  // 像素中心命中
  for (const p of r.pixels) {
    if (!p.center_hit) continue;
    const cx = t.x(d.grid.origin[t.u] + (p.i + 0.5) * h);
    const cy = t.y(d.grid.origin[t.v] + (p.j + 0.5) * h);
    ctx.fillStyle = "#e8ecf5";
    ctx.beginPath(); ctx.arc(cx, cy, 2.5, 0, 7); ctx.fill();
  }
  // 三角形投影
  ctx.strokeStyle = "#f8fafc";
  ctx.lineWidth = 2;
  ctx.beginPath();
  r.tri2d.forEach((p, k) => {
    const x = t.x(p[0]), y = t.y(p[1]);
    if (k === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.closePath(); ctx.stroke();

  const axisName = AXIS_NAMES[r.axis];
  $("raster-info").textContent =
    `投影轴 ${axisName}，像素 ${r.pixels.length} 个（拖拽平移几何）`;
}

function rasterPick(evt) {
  const d = state.data;
  const r = d.raster[state.selectedTri];
  if (!r || r.degenerate) return null;
  const cv = $("raster");
  const rect = cv.getBoundingClientRect();
  const t = rasterTransform(d, r);
  const wu = t.invX(evt.clientX - rect.left);
  const wv = t.invY(evt.clientY - rect.top);
  const h = d.grid.cell;
  const i = Math.floor((wu - d.grid.origin[t.u]) / h);
  const j = Math.floor((wv - d.grid.origin[t.v]) / h);
  return { i, j, t };
}

// 拖拽平移几何
let dragStart = null;
$("raster").addEventListener("mousedown", (e) => {
  dragStart = { x: e.clientX, y: e.clientY };
});
$("raster").addEventListener("mouseup", (e) => {
  if (!dragStart) return;
  const d = state.data;
  const r = d.raster[state.selectedTri];
  if (r && !r.degenerate) {
    const t = rasterTransform(d, r);
    const du = (e.clientX - dragStart.x) / t.s;
    const dv = -(e.clientY - dragStart.y) / t.s;
    state.offset[t.u] += du;
    state.offset[t.v] += dv;
    syncOffsetInputs();
    regenerate();
  }
  dragStart = null;
});
$("raster").addEventListener("mousemove", (e) => {
  const d = state.data;
  if (!d) return;
  const r = d.raster[state.selectedTri];
  if (!r || r.degenerate) return;
  const pick = rasterPick(e);
  if (!pick) return;
  const p = r.pixels.find((p) => p.i === pick.i && p.j === pick.j);
  const info = $("raster-info");
  if (p) {
    info.textContent =
      `像素 (${p.i},${p.j}) 深度 [${p.dmin.toFixed(3)}, ${p.dmax.toFixed(3)}]` +
      ` 中心命中:${p.center_hit ? "是" : "否"} 解析:${p.exact ? "必交" : "可能交"}`;
  }
});

// ---------- 体素视图（等轴投影） ----------

function isoProject(d) {
  const cv = $("voxels");
  const nx = d.grid.n[0], ny = d.grid.n[1], nz = d.grid.n[2];
  // 自适应缩放，保证任意分辨率下空间格都在画布内
  const cw = Math.max(3, Math.min(13, (cv.width - 60) / (nx + ny),
                                  (cv.height - 60) / (0.54 * (nx + ny) + nz)));
  const ch = cw * 0.54, chh = cw;
  const pts = [];
  for (const [i, j, k] of [[0,0,0],[nx,0,0],[0,ny,0],[0,0,nz],[nx,ny,0],[nx,0,nz],[0,ny,nz],[nx,ny,nz]]) {
    pts.push([(i - j) * cw, (i + j) * ch - k * chh]);
  }
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  const ox = cv.width / 2 - (Math.min(...xs) + Math.max(...xs)) / 2;
  const oy = cv.height / 2 - (Math.min(...ys) + Math.max(...ys)) / 2;
  return (i, j, k) => [ox + (i - j) * cw, oy + (i + j) * ch - k * chh];
}

function drawCube(ctx, P, i, j, k, fill, stroke) {
  const p100 = P(i + 1, j, k), p010 = P(i, j + 1, k);
  const p110 = P(i + 1, j + 1, k);
  const p001 = P(i, j, k + 1), p101 = P(i + 1, j, k + 1);
  const p011 = P(i, j + 1, k + 1), p111 = P(i + 1, j + 1, k + 1);
  const faces = [
    [[p001, p101, p111, p011], fill.top],    // 顶
    [[p100, p110, p111, p101], fill.right],  // 右
    [[p010, p110, p111, p011], fill.left],   // 左
  ];
  for (const [poly, color] of faces) {
    ctx.beginPath();
    poly.forEach((p, idx) => (idx ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])));
    ctx.closePath();
    if (color) { ctx.fillStyle = color; ctx.fill(); }
    if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = 1; ctx.stroke(); }
  }
}

function renderVoxels() {
  const d = state.data;
  const cv = $("voxels");
  const ctx = cv.getContext("2d");
  ctx.clearRect(0, 0, cv.width, cv.height);
  const P = isoProject(d);
  const [nx, ny, nz] = d.grid.n;

  // 空间格外框
  const corners = [[0,0,0],[nx,0,0],[0,ny,0],[0,0,nz],[nx,ny,0],[nx,0,nz],[0,ny,nz],[nx,ny,nz]];
  const edges = [[0,1],[0,2],[0,3],[1,4],[1,5],[2,4],[2,6],[3,5],[3,6],[4,7],[5,7],[6,7]];
  ctx.strokeStyle = "#2a3550";
  for (const [a, b] of edges) {
    const pa = P(...corners[a]), pb = P(...corners[b]);
    ctx.beginPath(); ctx.moveTo(pa[0], pa[1]); ctx.lineTo(pb[0], pb[1]); ctx.stroke();
  }

  const maxLayer = state.layer === Infinity ? nz - 1 : state.layer;
  const mayOnly = new Set(d.may_only.map((c) => c.join(",")));
  const must = d.must.filter((c) => c[2] <= maxLayer);
  const may = d.may_only.filter((c) => c[2] <= maxLayer);
  const all = [
    ...may.map((c) => ({ c, kind: "may" })),
    ...must.map((c) => ({ c, kind: "must" })),
  ];
  all.sort((a, b) => {
    const sa = a.c[0] + a.c[1] + a.c[2], sb = b.c[0] + b.c[1] + b.c[2];
    return sa - sb || a.c[2] - b.c[2];
  });

  for (const { c, kind } of all) {
    const key = c.join(",");
    const hl = state.highlightVoxels.has(key) || state.highlightVoxel === key;
    if (kind === "may") {
      drawCube(ctx, P, c[0], c[1], c[2],
        { top: null, right: null, left: null },
        hl ? "#f59e0b" : "rgba(239,68,68,0.55)");
    } else {
      drawCube(ctx, P, c[0], c[1], c[2],
        hl
          ? { top: "#fcd34d", right: "#f59e0b", left: "#b45309" }
          : { top: "#7db3fb", right: "#3b82f6", left: "#2b5cb8" },
        "#0b0f1a");
    }
  }

  // 通路（连通测量）
  if (state.conn && state.conn.path && state.conn.path.length) {
    const g = state.conn.grid;
    const ratio = g.cell / d.grid.cell;  // 细分格 -> 基格坐标映射
    for (const c of state.conn.path) {
      const i = c[0] * ratio, j = c[1] * ratio, k = c[2] * ratio;
      if (k > maxLayer) continue;
      drawCube(ctx, P, i, j, k,
        { top: "rgba(34,197,94,0.85)", right: "rgba(34,197,94,0.6)", left: "rgba(21,128,61,0.6)" },
        "#0b0f1a");
    }
  }
  $("layer").max = nz - 1;
  $("layer").value = maxLayer;
  $("layer-val").textContent = maxLayer;
}

// ---------- 源面 / 体素列表 ----------

function invertSources() {
  const byTri = new Map();
  for (const [key, tris] of Object.entries(state.data.sources)) {
    for (const t of tris) {
      if (!byTri.has(t)) byTri.set(t, []);
      byTri.get(t).push(key);
    }
  }
  return byTri;
}

function renderFaces() {
  const d = state.data;
  const byTri = invertSources();
  const box = $("faces");
  box.innerHTML = "";
  d.triangles.forEach((tri, idx) => {
    const div = document.createElement("div");
    div.className = "item";
    const n = (byTri.get(idx) || []).length;
    const deg = d.degenerate.includes(idx) ? "（退化）" : "";
    div.textContent = `面 #${idx}${deg} → ${n} 体素`;
    div.onclick = () => {
      state.selectedTri = idx;
      $("tri-select").value = idx;
      state.highlightVoxels = new Set(byTri.get(idx) || []);
      state.highlightVoxel = null;
      renderRaster();
      renderVoxels();
      renderFaces();
    };
    if (idx === state.selectedTri && state.highlightVoxels.size) div.classList.add("active");
    box.appendChild(div);
  });
}

function renderVoxelList() {
  const d = state.data;
  const box = $("voxel-list");
  box.innerHTML = "";
  const cells = d.must.slice(0, 400);
  for (const c of cells) {
    const key = c.join(",");
    const div = document.createElement("div");
    div.className = "item";
    div.textContent = `(${c[0]}, ${c[1]}, ${c[2]}) ← 面 ${d.sources[key].join(", ")}`;
    div.onclick = () => {
      state.highlightVoxel = key;
      state.highlightVoxels = new Set();
      renderVoxels();
      renderVoxelList();
    };
    if (state.highlightVoxel === key) div.classList.add("active");
    box.appendChild(div);
  }
  if (d.must.length > cells.length) {
    const div = document.createElement("div");
    div.className = "dim";
    div.textContent = `… 共 ${d.must.length} 个，仅列前 ${cells.length}`;
    box.appendChild(div);
  }
}

// ---------- 连通测量 ----------

async function measure() {
  showError("");
  try {
    const res = await api("/api/connectivity", {
      scene: state.scene,
      budget: parseInt($("budget").value, 10),
      offset: state.offset,
    });
    state.conn = res;
    const cls = res.status === "connected" ? "ok" : res.status === "blocked" ? "warn" : "bad";
    const agree = res.agrees_with_fine_mesh
      ? '<span class="ok">与细网格复验一致</span>'
      : `<span class="bad">与细网格复验(${res.fine_mesh_verdict})不一致：预算不足，结论仅供参考</span>`;
    $("conn-result").className = "kv";
    $("conn-result").innerHTML =
      `结论: <b class="${cls}">${res.status}</b>（细分 ${res.levels} 层 / 预算 ${res.budget}）\n` +
      `${res.message}\n` +
      `决定通断的候选格: <b>${res.frontier.length}</b>，未决区域: <b>${res.undecided_cells.length}</b>\n` +
      `细网格复验: <b>${res.fine_mesh_verdict}</b> ${agree}`;
    renderVoxels();
  } catch (e) {
    showError("连通测量失败: " + e.message);
  }
}

// ---------- 事件 ----------

function syncOffsetInputs() {
  $("dx").value = state.offset[0].toFixed(2);
  $("dy").value = state.offset[1].toFixed(2);
  $("dz").value = state.offset[2].toFixed(2);
}

$("scene").addEventListener("change", () => {
  state.scene = $("scene").value;
  state.offset = [0, 0, 0];
  state.selectedTri = 0;
  state.highlightVoxels = new Set();
  state.highlightVoxel = null;
  syncOffsetInputs();
  onSceneMeta();
  regenerate();
});
$("regen").addEventListener("click", () => {
  state.offset = [parseFloat($("dx").value) || 0,
                  parseFloat($("dy").value) || 0,
                  parseFloat($("dz").value) || 0];
  regenerate();
});
$("tri-select").addEventListener("change", () => {
  state.selectedTri = parseInt($("tri-select").value, 10);
  renderRaster();
});
$("layer").addEventListener("input", () => {
  state.layer = parseInt($("layer").value, 10);
  renderVoxels();
});
$("measure").addEventListener("click", measure);
$("download").addEventListener("click", () => {
  if (!state.data) return;
  const blob = new Blob([JSON.stringify(state.data, null, 1)],
                        { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `voxels_${state.scene}.json`;
  a.click();
  URL.revokeObjectURL(a.href);
});

loadScenes().then(regenerate).catch((e) => showError("初始化失败: " + e.message));
