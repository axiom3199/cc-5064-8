import unittest

from voxelizer.geometry import (point_triangle_distance, tri_box_overlap,
                                tri_normal, vlen)


class TestTriBoxOverlap(unittest.TestCase):
    def test_face_touch_counts(self):
        # 三角形躺在盒面上：闭集语义算相交
        tri = ((0.25, 0.25, 0.5), (0.75, 0.25, 0.5), (0.5, 0.75, 0.5))
        self.assertTrue(tri_box_overlap((0.5, 0.5, 0.5), (0.5, 0.5, 0.5), tri))

    def test_corner_touch_counts(self):
        # 三角形仅接触盒角 (1,1,1)
        tri = ((1.0, 1.0, 1.0), (2.0, 1.5, 1.5), (1.5, 2.0, 1.5))
        self.assertTrue(tri_box_overlap((0.5, 0.5, 0.5), (0.5, 0.5, 0.5), tri))

    def test_clear_miss(self):
        tri = ((2.0, 2.0, 2.0), (3.0, 2.0, 2.0), (2.0, 3.0, 2.0))
        self.assertFalse(tri_box_overlap((0.5, 0.5, 0.5), (0.5, 0.5, 0.5), tri))

    def test_edge_cross(self):
        tri = ((0.5, -1.0, 0.2), (0.5, 2.0, 0.2), (0.5, 0.5, 0.8))
        self.assertTrue(tri_box_overlap((0.5, 0.5, 0.5), (0.5, 0.5, 0.5), tri))

    def test_degenerate_segment(self):
        # 退化三角形（共线）穿过盒
        tri = ((0.5, 0.5, -1.0), (0.5, 0.5, 2.0), (0.5, 0.5, 0.5))
        self.assertTrue(tri_box_overlap((0.5, 0.5, 0.5), (0.5, 0.5, 0.5), tri))
        # 退化三角形在盒外
        tri2 = ((3.0, 3.0, 3.0), (4.0, 4.0, 4.0), (3.5, 3.5, 3.5))
        self.assertFalse(tri_box_overlap((0.5, 0.5, 0.5), (0.5, 0.5, 0.5), tri2))

    def test_normal_and_distance(self):
        tri = ((0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (0.0, 2.0, 0.0))
        n = tri_normal(tri)
        self.assertAlmostEqual(vlen(n), 4.0)  # 2 倍面积
        self.assertAlmostEqual(point_triangle_distance((0.5, 0.5, 1.0), tri), 1.0)
        self.assertAlmostEqual(point_triangle_distance((3.0, 0.0, 0.0), tri), 1.0)


if __name__ == "__main__":
    unittest.main()
