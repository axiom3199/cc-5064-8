#!/usr/bin/env python3
"""体素覆盖图形界面入口。

用法: python3 server.py [--port 8000]
然后浏览器打开 http://127.0.0.1:8000/

保守覆盖与空间格均由服务器实际运算；异常以 JSON 错误返回、由界面提示。
"""
import argparse
import json
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from voxelizer import scenes
from voxelizer.connectivity import fine_verdict, measure_connectivity
from voxelizer.voxelizer import Voxelizer

WEB = Path(__file__).parent / "web"
NOTE = ("表面占用（surface occupancy）：仅表示三角形表面穿过哪些体素，"
        "不代表已获得内部实心体积；本工具不做内部填充。")

MAX_RES = 48


def _clamp_res(res):
    if res is None:
        return None
    return max(4, min(MAX_RES, int(res)))


def api_scenes():
    return {"scenes": scenes.list_scenes(), "note": NOTE}


def api_voxelize(payload):
    sc = scenes.get_scene(
        payload.get("scene", ""),
        res=_clamp_res(payload.get("res")),
        scale=payload.get("scale"),
        offset=tuple(payload.get("offset", (0.0, 0.0, 0.0))),
    )
    v = Voxelizer(sc.grid)
    table = v.voxelize(sc.triangles)
    ver = v.verify(sc.triangles, table)
    raster = []
    for r in table.raster:
        if r["degenerate"]:
            raster.append({"tri": r["tri"], "degenerate": True,
                           "cells": [list(c) for c in r["cells"]]})
            continue
        pixels = []
        for p in r["pixels"]:
            pixels.append({
                "i": p["i"], "j": p["j"],
                "dmin": p["dmin"], "dmax": p["dmax"],
                "center_hit": p["center_hit"],
                "exact": any(c["exact"] for c in p["cells"]),
                "cells": [[*c["voxel"], int(c["exact"])] for c in p["cells"]],
            })
        raster.append({"tri": r["tri"], "degenerate": False,
                       "axis": r["axis"], "uv": list(r["uv"]),
                       "tri2d": [list(p) for p in r["tri2d"]],
                       "pixels": pixels})
    return {
        "note": NOTE,
        "scene": sc.key,
        "grid": {"origin": list(table.grid.origin), "cell": table.grid.cell,
                 "n": [table.grid.nx, table.grid.ny, table.grid.nz]},
        "triangles": [[list(p) for p in tri] for tri in sc.triangles],
        "stats": table.stats(),
        "must": sorted(table.must),
        "may": sorted(table.may),
        "may_only": sorted(table.may_only),
        "sources": {f"{i},{j},{k}": sorted(s)
                    for (i, j, k), s in table.sources.items()},
        "degenerate": table.degenerate,
        "verification": {"missed": sorted(ver.missed),
                         "extra": sorted(ver.extra),
                         "reference_count": ver.reference_count},
        "raster": raster,
        "connectivity": sc.connectivity,
    }


def api_connectivity(payload):
    sc = scenes.get_scene(
        payload.get("scene", ""),
        offset=tuple(payload.get("offset", (0.0, 0.0, 0.0))),
    )
    if not sc.connectivity:
        raise ValueError(f"场景 {sc.key} 无连通测量配置")
    budget = max(0, min(3, int(payload.get("budget", 1))))
    conn = sc.connectivity
    r = measure_connectivity(sc.triangles, sc.grid, budget,
                             axis=conn["axis"],
                             start_layer=conn["start_layer"],
                             goal_layer=conn["goal_layer"])
    fine = fine_verdict(sc.triangles, sc.grid, axis=conn["axis"],
                        start_layer=conn["start_layer"],
                        goal_layer=conn["goal_layer"])
    return {
        "status": r.status,
        "levels": r.levels,
        "budget": r.budget,
        "message": r.message,
        "grid": {"origin": list(r.grid.origin), "cell": r.grid.cell,
                 "n": [r.grid.nx, r.grid.ny, r.grid.nz]},
        "frontier": r.frontier,
        "undecided_cells": r.undecided_cells,
        "path": r.path,
        "fine_mesh_verdict": fine,
        "agrees_with_fine_mesh": r.status == fine,
    }


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path, content_type):
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/scenes":
            self._send_json(api_scenes())
            return
        if path in ("/", "/index.html"):
            self._send_file(WEB / "index.html", "text/html; charset=utf-8")
        elif path == "/app.js":
            self._send_file(WEB / "app.js", "text/javascript; charset=utf-8")
        elif path == "/style.css":
            self._send_file(WEB / "style.css", "text/css; charset=utf-8")
        else:
            self.send_error(404)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
            path = urlparse(self.path).path
            if path == "/api/voxelize":
                self._send_json(api_voxelize(payload))
            elif path == "/api/connectivity":
                self._send_json(api_connectivity(payload))
            else:
                self.send_error(404)
        except ValueError as e:
            self._send_json({"error": str(e)}, status=400)
        except Exception as e:  # 异常由体素覆盖界面提示
            traceback.print_exc()
            self._send_json({"error": f"内部错误: {e}"}, status=500)

    def log_message(self, fmt, *args):
        pass


def main():
    ap = argparse.ArgumentParser(description="体素覆盖图形界面入口")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"体素覆盖界面: http://{args.host}:{args.port}/")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
