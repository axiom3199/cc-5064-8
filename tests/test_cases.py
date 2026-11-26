import unittest

from voxelizer.bounds import (TOUCH_TOL, ContactEvidence, contact_evidence,
                              run_study, study_case)
from voxelizer.cases import (LEVELS, _BUILDERS, get_case, grid_for_level,
                             list_cases)
from voxelizer.voxelizer import Voxelizer


class TestGeometryCases(unittest.TestCase):
    def test_case_inventory_covers_required_families(self):
        keys = set(_BUILDERS)
        # 薄片、斜面、尖角、轴向退化、极薄面五大族都要有
        for prefix in ("sheet", "incline", "spike", "axis", "wafer"):
            self.assertTrue(any(k.startswith(prefix) for k in keys), prefix)
        # 三类已知接触类型都要出现
        contacts = {c.contact for c in list_cases()}
        self.assertEqual(contacts, {"graze", "penetrate", "gap"})

    def test_provenance_and_params_saved(self):
        for case in list_cases():
            self.assertTrue(case.source.endswith("cases.py"))
            self.assertIsInstance(case.params, dict)
            self.assertGreater(len(case.params), 0)
            for tri in case.triangles:
                self.assertEqual(len(tri), 3)
                for p in tri:
                    self.assertEqual(len(p), 3)

    def test_three_grid_levels_span_octaves(self):
        cells = [grid_for_level(lv).cell for lv in LEVELS]
        self.assertEqual(cells, [1.0, 0.5, 0.25])
        ns = [grid_for_level(lv).nx for lv in LEVELS]
        self.assertEqual(ns, [12, 24, 48])


class TestRealVoxelizationPerCase(unittest.TestCase):
    def test_no_missed_at_every_level(self):
        # 漏覆盖在任何级别都必须为空（闭集保守性）
        for case in list_cases():
            for lv in LEVELS:
                g = grid_for_level(lv)
                v = Voxelizer(g)
                table = v.voxelize(list(case.triangles))
                ver = v.verify(list(case.triangles), table)
                self.assertEqual(ver.missed, set(),
                                 f"{case.key}@{lv} 漏标 {sorted(ver.missed)[:3]}")
                self.assertLessEqual(table.must, table.may)

    def test_extra_voxels_are_real_may_only(self):
        # 多余体素必须正好等于 may_only，且能被解析参考否证
        for case in list_cases():
            g = grid_for_level("base")
            v = Voxelizer(g)
            table = v.voxelize(list(case.triangles))
            ver = v.verify(list(case.triangles), table)
            self.assertEqual(ver.extra, table.may_only, case.key)

    def test_degenerate_cases_use_fallback(self):
        for key in ("axis_degenerate", "axis_dup_point", "spike_graze"):
            case = get_case(key)
            self.assertTrue(case.expect_degenerate)
            table = Voxelizer(grid_for_level("base")).voxelize(
                list(case.triangles))
            self.assertEqual(table.degenerate, list(range(len(case.triangles))))


class TestContactEvidence(unittest.TestCase):
    def _evidence(self, key, lv="base"):
        case = get_case(key)
        g = grid_for_level(lv)
        table = Voxelizer(g).voxelize(list(case.triangles))
        return contact_evidence(case, g, table)

    def test_graze_cases_show_touch_not_straddle(self):
        for key in ("sheet_graze", "wafer_graze", "incline_graze"):
            ev = self._evidence(key)
            self.assertEqual(ev.straddle_pixels, 0, key)
            self.assertGreater(ev.touch_pixels, 0, key)
            self.assertEqual(ev.observed, "graze", key)

    def test_penetrate_cases_show_straddle(self):
        for key in ("sheet_penetrate", "incline_penetrate",
                    "spike_penetrate"):
            for lv in LEVELS:
                ev = self._evidence(key, lv)
                self.assertGreater(ev.straddle_pixels, 0, f"{key}@{lv}")
                self.assertEqual(ev.observed, "penetrate", f"{key}@{lv}")

    def test_gap_case_distinguished_from_graze_by_real_output(self):
        # 擦边与留缝几何形状相同，只差 4e-10 间隙：
        # 真实体素输出里留缝产生 may_only，擦边没有
        gap = self._evidence("eps_hover", "base")
        graze = self._evidence("sheet_graze", "base")
        self.assertGreater(gap.hover_voxels, 0)
        self.assertEqual(gap.observed, "gap")
        self.assertEqual(graze.hover_voxels, 0)
        self.assertEqual(graze.observed, "graze")

    def test_degenerate_graze_uses_boundary_points(self):
        for key in ("axis_degenerate", "axis_dup_point", "spike_graze"):
            ev = self._evidence(key)
            self.assertGreater(ev.boundary_points, 0, key)
            self.assertEqual(ev.observed, "graze", key)

    def test_touch_tolerance_is_much_smaller_than_fine_cell(self):
        self.assertLess(TOUCH_TOL, grid_for_level("fine").cell / 100)


class TestSubdivisionBounds(unittest.TestCase):
    def test_study_all_cases_classified(self):
        for st in run_study():
            self.assertIn(st.applicability, ("valid", "limited"))
            self.assertEqual(len(st.levels), 3)
            for lv in st.levels:
                self.assertEqual(lv["missed"], 0, st.key)

    def test_penetrate_bounds_monotone_and_resolution_independent(self):
        st = study_case("incline_penetrate")
        for lv in st.levels:
            self.assertEqual(lv["evidence"]["observed"], "penetrate")
        extras = [lv["extra"] for lv in st.levels]
        dists = [lv["max_extra_distance"] for lv in st.levels]
        for i in range(2):
            self.assertLessEqual(extras[i + 1], extras[i])
            self.assertLessEqual(dists[i + 1], dists[i] + 1e-12)

    def test_gap_bounds_limit_revealed_by_refinement(self):
        # 留缝案例：粗/中网格有 may_only，细分到 h=0.25 后伪占用消失
        st = study_case("eps_hover")
        self.assertEqual(st.applicability, "limited")
        self.assertGreater(st.levels[0]["evidence"]["hover_voxels"], 0)
        self.assertGreater(st.levels[1]["evidence"]["hover_voxels"], 0)
        self.assertEqual(st.levels[2]["evidence"]["hover_voxels"], 0)
        self.assertEqual(st.levels[2]["evidence"]["observed"], "graze")

    def test_graze_double_attribution_persists_under_refinement(self):
        # 闭集双归属是接触语义，不应被细分消掉
        st = study_case("sheet_graze")
        z_layers = set()
        case = get_case("sheet_graze")
        for lv in LEVELS:
            g = grid_for_level(lv)
            table = Voxelizer(g).voxelize(list(case.triangles))
            z_layers.update(c[2] for c in table.must)
        # 每一级都应同时含 z=7 平面的两侧层
        for lv, scale in zip(LEVELS, (1, 2, 4)):
            g = grid_for_level(lv)
            table = Voxelizer(g).voxelize(list(case.triangles))
            k = 7 * scale
            self.assertIn(k - 1, {c[2] for c in table.must})
            self.assertIn(k, {c[2] for c in table.must})


if __name__ == "__main__":
    unittest.main()
