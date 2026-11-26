import json
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

import server


def _post(port, path, payload):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


class TestServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.srv.server_address[1]
        cls.thread = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_scenes(self):
        with urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}/api/scenes") as resp:
            data = json.loads(resp.read())
        keys = [s["key"] for s in data["scenes"]]
        self.assertIn("duct_strip", keys)
        self.assertIn("note", data)
        # 退化几何素材包必须通过图形入口暴露，而不是只存在于命令行
        for key in ("sheet_graze", "sheet_penetrate", "eps_hover",
                    "wafer_graze", "incline_graze", "incline_penetrate",
                    "spike_graze", "spike_penetrate",
                    "axis_degenerate", "axis_dup_point"):
            self.assertIn(key, keys)

    def test_voxelize_contract(self):
        status, d = _post(self.port, "/api/voxelize", {"scene": "duct_strip"})
        self.assertEqual(status, 200)
        for field in ("must", "may", "may_only", "sources", "raster",
                      "verification", "grid", "triangles", "note"):
            self.assertIn(field, d)
        self.assertEqual(d["verification"]["missed"], [])
        r = d["raster"][0]
        self.assertIn("axis", r)
        self.assertIn("pixels", r)
        p = r["pixels"][0]
        for field in ("i", "j", "dmin", "dmax", "center_hit", "exact"):
            self.assertIn(field, p)

    def test_connectivity_contract(self):
        status, d = _post(self.port, "/api/connectivity",
                          {"scene": "duct_paper", "budget": 2})
        self.assertEqual(status, 200)
        self.assertEqual(d["status"], "blocked")
        self.assertEqual(d["fine_mesh_verdict"], "blocked")
        status, d = _post(self.port, "/api/connectivity",
                          {"scene": "duct_strip", "budget": 2})
        self.assertEqual(d["status"], "connected")
        self.assertTrue(d["path"])

    def test_error_surfaced(self):
        status, d = _post(self.port, "/api/voxelize", {"scene": "nope"})
        self.assertEqual(status, 400)
        self.assertIn("error", d)
        # 孔道场景分辨率固定，越界修改应报错并由界面提示
        status, d = _post(self.port, "/api/voxelize",
                          {"scene": "duct_strip", "res": 24})
        self.assertEqual(status, 400)
        self.assertIn("error", d)

    def test_offset_moves_geometry(self):
        _, d0 = _post(self.port, "/api/voxelize", {"scene": "tetra"})
        _, d1 = _post(self.port, "/api/voxelize",
                      {"scene": "tetra", "offset": [1.0, 0.0, 0.0]})
        self.assertNotEqual(d0["must"], d1["must"])

    def test_degenerate_geometry_cases_served_live(self):
        # 新退化几何案例必须经服务器实际体素化，不能回固定数据
        for scene, expect_deg in (("sheet_graze", 0),
                                  ("sheet_penetrate", 0),
                                  ("axis_degenerate", 1),
                                  ("spike_graze", 1),
                                  ("eps_hover", 0)):
            status, d = _post(self.port, "/api/voxelize", {"scene": scene})
            self.assertEqual(status, 200, scene)
            self.assertEqual(d["scene"], scene)
            self.assertEqual(d["verification"]["missed"], [], scene)
            self.assertEqual(len(d["degenerate"]), expect_deg, scene)
            self.assertTrue(d["must"] or d["may"], scene)
            # 光栅调试数据真实存在：非退化给像素，退化给回退格
            r0 = d["raster"][0]
            if r0["degenerate"]:
                self.assertTrue(r0["cells"])
            else:
                self.assertIn("axis", r0)
                self.assertTrue(r0["pixels"])

    def test_graze_vs_gap_distinguished_in_served_output(self):
        _, graze = _post(self.port, "/api/voxelize",
                         {"scene": "sheet_graze"})
        _, gap = _post(self.port, "/api/voxelize", {"scene": "eps_hover"})
        self.assertEqual(graze["may_only"], [])
        self.assertTrue(gap["may_only"])
        self.assertEqual(len(gap["verification"]["extra"]),
                         len(gap["may_only"]))

    def test_offset_regenerates_new_case_coverage(self):
        # 界面拖拽平移几何后必须重新运算出不同的保守覆盖
        _, d0 = _post(self.port, "/api/voxelize",
                      {"scene": "incline_penetrate"})
        _, d1 = _post(self.port, "/api/voxelize",
                      {"scene": "incline_penetrate",
                       "offset": [0.37, 0.0, 0.0]})
        self.assertNotEqual(d0["may"], d1["may"])
        self.assertEqual(d1["verification"]["missed"], [])


if __name__ == "__main__":
    unittest.main()
