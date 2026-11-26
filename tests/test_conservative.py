import unittest

from voxelizer.conservative import (dominant_axis, point_in_tri_2d,
                                    project_triangle_coverage)
from voxelizer.grid import Grid


class TestConservativeRaster(unittest.TestCase):
    def setUp(self):
        self.grid = Grid((0.0, 0.0, 0.0), 1.0, 16, 16, 16)

    def test_tiny_triangle_without_center_not_missed(self):
        # 细三角完全位于像素 (4,4) 内部、不含任何像素中心
        tri = ((4.10, 4.10, 2.0), (4.30, 4.12, 2.0), (4.12, 4.30, 2.0))
        cov, tri2d, (u, v) = project_triangle_coverage(self.grid, tri, 2)
        self.assertTrue(len(cov) >= 1, "不含中心点的细三角被遗漏")
        self.assertTrue(all(not c.center_hit for c in cov))
        self.assertEqual({(c.i, c.j) for c in cov}, {(4, 4)})

    def test_center_hit_subset_of_conservative(self):
        # 中心命中的像素必须是保守覆盖的子集
        tri = ((2.2, 2.1, 5.0), (7.8, 3.0, 5.0), (3.0, 8.4, 5.0))
        cov, tri2d, _ = project_triangle_coverage(self.grid, tri, 2)
        covered = {(c.i, c.j) for c in cov}
        for i in range(16):
            for j in range(16):
                if point_in_tri_2d((i + 0.5, j + 0.5), tri2d):
                    self.assertIn((i, j), covered)

    def test_extra_coverage_bounded_not_whole_bbox(self):
        # 大斜三角：覆盖有界，不把整个包围盒标成实体
        tri = ((0.5, 0.5, 0.5), (14.5, 0.5, 14.5), (0.5, 14.5, 14.5))
        cov, _, _ = project_triangle_coverage(self.grid, tri, 0)
        pixels = {(c.i, c.j) for c in cov}
        # 投影是直角三角形：远角像素 (14,0) 不得被标；覆盖严格小于包围盒
        self.assertNotIn((14, 0), pixels)
        self.assertLess(len(pixels), 15 * 15)
        for (i, j) in pixels:
            self.assertTrue(0 <= i <= 15 and 0 <= j <= 15)

    def test_depth_interval_exact_on_flat_triangle(self):
        tri = ((2.2, 2.2, 3.5), (6.8, 2.2, 3.5), (2.2, 6.8, 3.5))
        cov, _, _ = project_triangle_coverage(self.grid, tri, 2)
        self.assertTrue(cov)
        for c in cov:
            self.assertAlmostEqual(c.dmin, 3.5)
            self.assertAlmostEqual(c.dmax, 3.5)

    def test_depth_interval_within_triangle_extent(self):
        tri = ((2.0, 2.0, 1.0), (8.0, 2.0, 6.0), (2.0, 8.0, 4.0))
        cov, _, _ = project_triangle_coverage(self.grid, tri, 2)
        for c in cov:
            self.assertGreaterEqual(c.dmin, 1.0 - 1e-9)
            self.assertLessEqual(c.dmax, 6.0 + 1e-9)
            self.assertLessEqual(c.dmin, c.dmax)

    def test_dominant_axis(self):
        self.assertEqual(dominant_axis((0.0, 0.0, 5.0)), 2)
        self.assertEqual(dominant_axis((-4.0, 1.0, 2.0)), 0)
        self.assertEqual(dominant_axis((1.0, -3.0, 2.0)), 1)


if __name__ == "__main__":
    unittest.main()
