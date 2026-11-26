// 客户端逻辑冒烟测试：mock DOM/fetch，加载 app.js，驱动 生成体素/连通测量。
// 用法: node tests/client_smoke.js <port>
const fs = require("fs");
const path = require("path");
const http = require("http");

const port = parseInt(process.argv[2] || "8123", 10);

function post(pathname, payload) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify(payload || {});
    const req = http.request(
      { host: "127.0.0.1", port, path: pathname, method: "POST",
        headers: { "Content-Type": "application/json" } },
      (res) => {
        let data = "";
        res.on("data", (c) => (data += c));
        res.on("end", () =>
          resolve({ ok: res.statusCode < 400, status: res.statusCode,
                    json: async () => JSON.parse(data) }));
      });
    req.on("error", reject);
    req.end(body);
  });
}

function get(pathname) {
  return new Promise((resolve, reject) => {
    http.get({ host: "127.0.0.1", port, path: pathname }, (res) => {
      let data = "";
      res.on("data", (c) => (data += c));
      res.on("end", () =>
        resolve({ ok: res.statusCode < 400, json: async () => JSON.parse(data) }));
    }).on("error", reject);
  });
}

// ---- 最小 DOM mock ----
const ctx2dCalls = { fillRect: 0, stroke: 0, fill: 0 };
function makeCtx() {
  return new Proxy({}, {
    get: (t, k) => {
      if (k in ctx2dCalls) return (...a) => { ctx2dCalls[k]++; };
      return (...a) => {};
    },
    set: () => true,
  });
}
function makeCanvas() {
  return { width: 540, height: 540, getContext: () => makeCtx(),
           addEventListener: () => {}, getBoundingClientRect: () =>
             ({ left: 0, top: 0 }) };
}
const elements = {};
function el(id) {
  if (!elements[id]) {
    elements[id] = {
      id, value: "12", textContent: "", innerHTML: "", disabled: false,
      hidden: true, className: "", max: 0, style: {},
      parentElement: { style: {} },
      children: [],
      appendChild(c) { this.children.push(c); },
      addEventListener: () => {},
      getContext: () => makeCtx(),
      getBoundingClientRect: () => ({ left: 0, top: 0 }),
      click: () => {},
    };
    if (id === "raster" || id === "voxels") {
      elements[id].width = 540; elements[id].height = 540;
    }
  }
  return elements[id];
}

global.document = {
  getElementById: el,
  createElement: (tag) => ({ tag, value: "", textContent: "", children: [],
                             className: "", click: () => {},
                             appendChild() {}, set innerHTML(v) {}, get innerHTML() { return ""; } }),
};
global.fetch = (url, opts) =>
  opts && opts.method === "POST" ? post(url, JSON.parse(opts.body)) : get(url);
global.URL = { createObjectURL: () => "", revokeObjectURL: () => {} };
global.Blob = class {};

const appSrc = fs.readFileSync(path.join(__dirname, "..", "web", "app.js"), "utf8");

async function main() {
  // 加载 app.js（顶层会执行 loadScenes().then(regenerate)）
  eval(appSrc + "\n;globalThis.state = state; globalThis.regenerate = regenerate;"
             + " globalThis.measure = measure;");
  await new Promise((r) => setTimeout(r, 800));

  const d = state.data;
  if (!d) throw new Error("voxelize 未返回数据");
  console.log("scene:", d.scene, "must:", d.stats.must, "may_only:", d.stats.may_only);
  if (d.verification.missed.length) throw new Error("存在漏标");
  if (ctx2dCalls.fillRect === 0) throw new Error("光栅视窗未绘制任何像素");
  console.log("raster fillRect calls:", ctx2dCalls.fillRect);

  // 切换到细三角场景
  state.scene = "tiny_corner";
  await regenerate();
  console.log("tiny_corner may:", state.data.stats.may,
              "may_only:", state.data.stats.may_only);
  if (state.data.stats.may < 1) throw new Error("细三角被遗漏");

  // 退化几何素材包案例：界面按钮走真实体素覆盖，不用固定数据冒充
  const before = ctx2dCalls.fillRect;
  for (const [scene, kind] of [["sheet_graze", "raster"],
                               ["incline_penetrate", "raster"],
                               ["axis_degenerate", "fallback"],
                               ["eps_hover", "raster"]]) {
    state.scene = scene;
    await regenerate();
    const d = state.data;
    if (d.verification.missed.length) throw new Error(`${scene} 存在漏标`);
    if (!d.must.length && !d.may.length) throw new Error(`${scene} 无占用`);
    const r0 = d.raster[0];
    if (kind === "raster" && (!r0.pixels || !r0.pixels.length))
      throw new Error(`${scene} 光栅视窗缺少真实覆盖像素`);
    if (kind === "fallback" && (!r0.degenerate || !r0.cells.length))
      throw new Error(`${scene} 退化回退数据缺失`);
    console.log(scene, "must:", d.stats.must, "may_only:", d.stats.may_only,
                kind === "raster" ? `pixels:${r0.pixels.length}`
                                  : `cells:${r0.cells.length}`);
  }
  if (ctx2dCalls.fillRect <= before)
    throw new Error("新案例未在光栅调试视窗绘制保守覆盖与空间格");

  // 连通测量（封孔纸）
  state.scene = "duct_paper";
  await regenerate();
  elements["budget"].value = "2";
  await measure();
  const conn = state.conn;
  console.log("duct_paper connectivity:", conn.status,
              "fine:", conn.fine_mesh_verdict, "agree:", conn.agrees_with_fine_mesh);
  if (conn.status !== "blocked") throw new Error("封孔纸应判定为隔断");

  // 连通测量（细斜片）
  state.scene = "duct_strip";
  await regenerate();
  await measure();
  console.log("duct_strip connectivity:", state.conn.status,
              "path len:", state.conn.path.length,
              "fine:", state.conn.fine_mesh_verdict);
  if (state.conn.status !== "connected") throw new Error("细斜片应判定为连通");
  if (!state.conn.path.length) throw new Error("缺少通路");

  // 错误路径：未知场景应触发错误横幅
  state.scene = "nonexistent";
  await regenerate();
  if (elements["error-banner"].hidden) throw new Error("异常未在界面提示");
  console.log("error banner shown:", elements["error-banner"].textContent);

  console.log("CLIENT SMOKE OK");
}

main().catch((e) => { console.error("FAIL:", e.message); process.exit(1); });
