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


if __name__ == "__main__":
    unittest.main()
