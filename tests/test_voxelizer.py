import unittest

from voxelizer import scenes
from voxelizer.grid import Grid
from voxelizer.voxelizer import Voxelizer


class TestVoxelizer(unittest.TestCase):
    def test_marks_cells_between_vertices_not_only_vertex_cells(self):
        # 不能只把模型顶点所在格子点亮：跨越多个格的三角形，
        # 顶点格之间的格也必须被标记
        grid = Grid((0.0, 0.0, 0.0), 1.0, 12, 12, 12)
        tri = [((2.2, 2.2, 5.5), (8.8, 2.2, 5.5), (2.2, 8.8, 5.5))]
        table = Voxelizer(grid).voxelize(tri)
        vertex_cells = {(2, 2, 5), (8, 2, 5), (2, 8, 5)}
        self.assertIn((4, 4, 5), table.may)
        self.assertIn((5, 2, 5), table.may)
        self.assertTrue(len(table.may) > len(vertex_cells))

    def test_boundary_attribution_triangle_on_grid_plane(self):
        # 三角形躺在格平面 z=3 上：闭集归属规则 -> z 层 2 和 3 都有
        sc = scenes.get_scene("grid_point_tri")
        table = Voxelizer(sc.grid).voxelize(sc.triangles)
        zs = {c[2] for c in table.may}
        self.assertEqual(zs, {2, 3})

    def test_degenerate_triangle_fallback(self):
        # 共线退化三角形：回退路径，沿段标记且不漏标
        grid = Grid((0.0, 0.0, 0.0), 1.0, 8, 8, 8)
        tri = [((1.5, 1.5, 1.5), (5.5, 1.5, 1.5), (3.5, 1.5, 1.5))]
        v = Voxelizer(grid)
        table = v.voxelize(tri)
        self.assertEqual(table.degenerate, [0])
        xs = {c[0] for c in table.may}
        self.assertEqual(xs, {1, 2, 3, 4, 5})
        ver = v.verify(tri, table)
        self.assertEqual(ver.missed, set())

    def test_may_superset_of_must_and_sources_consistent(self):
        for key in ("duct_strip", "duct_paper", "tiny_corner",
                    "grid_point_tri", "tetra", "cube"):
            sc = scenes.get_scene(key)
            table = Voxelizer(sc.grid).voxelize(sc.triangles)
            self.assertLessEqual(table.must, table.may, key)
            for c, srcs in table.sources.items():
                self.assertIn(c, table.may, key)
                self.assertTrue(srcs, key)
                for s in srcs:
                    self.assertLess(s, len(sc.triangles), key)

    def test_no_missed_against_reference_all_scenes(self):
        for key in ("duct_strip", "duct_paper", "duct_open", "tiny_corner",
                    "grid_point_tri", "tetra", "cube"):
            sc = scenes.get_scene(key)
            v = Voxelizer(sc.grid)
            table = v.voxelize(sc.triangles)
            ver = v.verify(sc.triangles, table)
            self.assertEqual(ver.missed, set(), f"{key} 漏标 {ver.missed}")

    def test_scales_no_missed(self):
        # 不同尺度模型：0.1 / 1 / 10 倍均不得漏标
        for key in ("tetra", "cube"):
            counts = []
            for s in (0.1, 1.0, 10.0):
                sc = scenes.get_scene(key, scale=s)
                v = Voxelizer(sc.grid)
                table = v.voxelize(sc.triangles)
                ver = v.verify(sc.triangles, table)
                self.assertEqual(ver.missed, set(), f"{key}@{s} 漏标")
                counts.append(len(table.must))
            # 同一相对分辨率下，占用规模应相近
            self.assertLess(abs(counts[0] - counts[1]) / max(counts[1], 1), 0.2)
            self.assertLess(abs(counts[2] - counts[1]) / max(counts[1], 1), 0.2)

    def test_eps_boundary_may_only_recorded_separately(self):
        # 薄三角贴着格界（距离 < eps）：保守外扩产生伪占用，
        # 必须作为 可能交(may_only) 单独记录，且解析测试不确认
        sc = scenes.get_scene("eps_graze")
        table = Voxelizer(sc.grid).voxelize(sc.triangles)
        above = {c for c in table.may if c[2] == 7}
        self.assertTrue(above, "eps 外扩应保守多标上一层")
        self.assertTrue(above.isdisjoint(table.must),
                        "伪占用不得混入必交")
        self.assertLessEqual(above, table.may_only)
        # 与解析交集核对：多标 == may_only，漏标为空
        ver = Voxelizer(sc.grid).verify(sc.triangles, table)
        self.assertEqual(ver.missed, set())
        self.assertEqual(ver.extra, table.may_only)


if __name__ == "__main__":
    unittest.main()
