import unittest

from voxelizer import scenes
from voxelizer.connectivity import fine_verdict, measure_connectivity
from voxelizer.voxelizer import Voxelizer

# 缝隙对角带在粗层（h=1, z 层 6）的候选格：{|i-j|<=1}, i,j in 2..9
SLOT_BAND = {(i, j, 6) for i in range(2, 10) for j in range(2, 10)
             if abs(i - j) <= 1}


def _conn_kwargs(sc):
    c = sc.connectivity
    return dict(axis=c["axis"], start_layer=c["start_layer"],
                goal_layer=c["goal_layer"])


class TestConnectivity(unittest.TestCase):
    def test_coarse_same_candidate_ring(self):
        # 细斜片与封孔纸在粗层得到相同的一圈候选格
        strip = scenes.get_scene("duct_strip")
        paper = scenes.get_scene("duct_paper")
        t_strip = Voxelizer(strip.grid).voxelize(strip.triangles)
        t_paper = Voxelizer(paper.grid).voxelize(paper.triangles)
        self.assertEqual(t_strip.may, t_paper.may)
        self.assertLessEqual(SLOT_BAND, t_strip.may)

    def test_tight_budget_both_undecided_same_region(self):
        # 缩紧细分预算（0）：两张纸都未决，且未决区域相同
        results = {}
        for key in ("duct_strip", "duct_paper"):
            sc = scenes.get_scene(key)
            r = measure_connectivity(sc.triangles, sc.grid, budget=0,
                                     **_conn_kwargs(sc))
            results[key] = r
            self.assertEqual(r.status, "undecided", key)
        self.assertEqual(set(results["duct_strip"].undecided_cells),
                         set(results["duct_paper"].undecided_cells))
        self.assertLessEqual(SLOT_BAND,
                             set(results["duct_strip"].undecided_cells))

    def test_budget_resolves_strip_connected_paper_blocked(self):
        # 细斜片：细分到第 2 层露出通道 -> 连通
        sc = scenes.get_scene("duct_strip")
        r = measure_connectivity(sc.triangles, sc.grid, budget=2,
                                 **_conn_kwargs(sc))
        self.assertEqual(r.status, "connected")
        self.assertGreaterEqual(r.levels, 1)
        self.assertTrue(r.path)

        # 封孔纸：任意预算都隔断
        for budget in (1, 2):
            sc = scenes.get_scene("duct_paper")
            r = measure_connectivity(sc.triangles, sc.grid, budget=budget,
                                     **_conn_kwargs(sc))
            self.assertEqual(r.status, "blocked", f"budget={budget}")

    def test_blocked_verdict_is_budget_qualified(self):
        # 预算不足时细斜片在粗层看似隔断（budget-qualified 结论），
        # 细网格复验揭示通道 —— 说明为何必须用细网格复验
        sc = scenes.get_scene("duct_strip")
        r = measure_connectivity(sc.triangles, sc.grid, budget=1,
                                 **_conn_kwargs(sc))
        self.assertEqual(r.status, "blocked")
        self.assertEqual(fine_verdict(sc.triangles, sc.grid,
                                      **_conn_kwargs(sc)), "connected")

    def test_open_duct_connected(self):
        sc = scenes.get_scene("duct_open")
        r = measure_connectivity(sc.triangles, sc.grid, budget=1,
                                 **_conn_kwargs(sc))
        self.assertEqual(r.status, "connected")

    def test_fine_mesh_verification_agrees(self):
        # 用细网格求出的通路复验两张纸的结论
        sc = scenes.get_scene("duct_strip")
        self.assertEqual(fine_verdict(sc.triangles, sc.grid,
                                      **_conn_kwargs(sc)), "connected")
        sc = scenes.get_scene("duct_paper")
        self.assertEqual(fine_verdict(sc.triangles, sc.grid,
                                      **_conn_kwargs(sc)), "blocked")

    def test_path_is_valid_and_free(self):
        sc = scenes.get_scene("duct_strip")
        r = measure_connectivity(sc.triangles, sc.grid, budget=2,
                                 **_conn_kwargs(sc))
        self.assertEqual(r.status, "connected")
        table = Voxelizer(r.grid).voxelize(sc.triangles)
        for a, b in zip(r.path, r.path[1:]):
            d = sum(abs(a[i] - b[i]) for i in range(3))
            self.assertEqual(d, 1, "通路必须 6-连通")
        for c in r.path:
            self.assertNotIn(c, table.may, "通路必须完全在保守覆盖之外")


if __name__ == "__main__":
    unittest.main()
