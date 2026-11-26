import random
import unittest

from voxelizer.geometry import point_triangle_distance
from voxelizer.grid import Grid
from voxelizer.voxelizer import Voxelizer


class TestReferenceCrossCheck(unittest.TestCase):
    def test_random_triangles_no_missed_and_extra_close(self):
        # 随机三角形：对照独立三角形-盒相交参考，
        # 不得漏标；多标（伪占用）必须贴着三角形（eps 量级）
        rng = random.Random(20261125)
        grid = Grid((0.0, 0.0, 0.0), 1.0, 12, 12, 12)
        v = Voxelizer(grid)
        tris = []
        for _ in range(200):
            tri = tuple((rng.uniform(1, 11), rng.uniform(1, 11),
                         rng.uniform(1, 11)) for _ in range(3))
            tris.append(tri)
        table = v.voxelize(tris)
        ver = v.verify(tris, table)
        self.assertEqual(ver.missed, set(), f"漏标: {sorted(ver.missed)[:5]}")
        h = grid.cell
        for c in ver.extra:
            lo = grid.cell_lo(*c)
            ctr = grid.cell_center(*c)
            # 多标体素必须紧邻某个三角形（保守 eps 外扩量级）
            d = min(point_triangle_distance(ctr, tri) for tri in tris)
            self.assertLess(d, h, f"多标体素 {c} 离所有三角形过远")

    def test_random_degenerate_and_tiny(self):
        rng = random.Random(7)
        grid = Grid((0.0, 0.0, 0.0), 1.0, 10, 10, 10)
        v = Voxelizer(grid)
        tris = []
        for _ in range(50):
            p = (rng.uniform(1, 9), rng.uniform(1, 9), rng.uniform(1, 9))
            q = (rng.uniform(1, 9), rng.uniform(1, 9), rng.uniform(1, 9))
            m = tuple((p[i] + q[i]) / 2 for i in range(3))
            tris.append((p, q, m))  # 共线退化
        for _ in range(50):
            p = (rng.uniform(1, 8.9), rng.uniform(1, 8.9), rng.uniform(1, 8.9))
            tri = tuple((p[0] + rng.uniform(0, 0.1), p[1] + rng.uniform(0, 0.1),
                         p[2] + rng.uniform(0, 0.1)) for _ in range(3))
            tris.append(tri)  # 极细小
        table = v.voxelize(tris)
        ver = v.verify(tris, table)
        self.assertEqual(ver.missed, set(), f"漏标: {sorted(ver.missed)[:5]}")


if __name__ == "__main__":
    unittest.main()
