import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import rebuild_samples  # noqa: E402
from voxelizer.cases import LEVELS, _BUILDERS, get_case, grid_for_level  # noqa: E402
from voxelizer.voxelizer import Voxelizer  # noqa: E402

SAMPLE_DIR = ROOT / "samples" / "voxels"
MANIFEST = ROOT / "samples" / "manifest.json"


def _load_manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


class TestSampleAssetPack(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = _load_manifest()

    def test_manifest_covers_every_case_and_level(self):
        self.assertEqual(self.manifest["count"],
                         len(_BUILDERS) * len(LEVELS))
        seen = {(e["case"], e["level"]) for e in self.manifest["samples"]}
        for key in _BUILDERS:
            for lv in LEVELS:
                self.assertIn((key, lv), seen)

    def test_sample_files_physically_exist(self):
        # 体素几何样本必须真实存在于磁盘，可被体素覆盖直接加载
        for entry in self.manifest["samples"]:
            path = ROOT / "samples" / entry["file"]
            self.assertTrue(path.exists(), entry["file"])
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertGreater(len(data["occupancy"]["must"])
                               + len(data["occupancy"]["may_only"]), 0)

    def test_samples_record_scale_axis_and_reference(self):
        for entry in self.manifest["samples"]:
            data = json.loads((ROOT / "samples" / entry["file"]).read_text())
            self.assertEqual(set(data["scale"]),
                             {"level", "cell", "n", "origin", "level_index"})
            self.assertIn("projection_axes", data)
            self.assertTrue(data["projection_axes"])
            ref = data["reference_intersection"]
            self.assertEqual(len(ref["voxels"]), ref["count"])
            self.assertEqual(ref["count"],
                             data["verification"]["reference_count"])
            self.assertIn("provenance", data)
            self.assertTrue(data["provenance"]["params"])

    def test_no_hand_filled_occupancy_recompute_matches(self):
        # 用当前体素化器重新执行，占用/参考/漏覆盖/多余体素必须逐项吻合；
        # 任何手填或篡改都会在这里暴露
        problems = rebuild_samples.check()
        self.assertEqual(problems, [], "\n".join(problems))

    def test_missed_always_empty_and_extra_equals_may_only(self):
        for entry in self.manifest["samples"]:
            data = json.loads((ROOT / "samples" / entry["file"]).read_text())
            self.assertEqual(data["verification"]["missed"], [], entry["file"])
            self.assertEqual(data["verification"]["extra"],
                             data["occupancy"]["may_only"], entry["file"])
            self.assertEqual(data["stats"]["may"],
                             data["stats"]["must"] + data["stats"]["may_only"])

    def test_observed_contact_agrees_with_declared_or_documented_flip(self):
        for entry in self.manifest["samples"]:
            data = json.loads((ROOT / "samples" / entry["file"]).read_text())
            declared, observed = (data["contact"]["declared"],
                                  data["contact"]["observed"])
            if declared == "gap":
                # 留缝在最细网格被分辨为擦边，是细分适用边界，允许翻转
                self.assertIn(observed, ("gap", "graze"))
            else:
                self.assertEqual(observed, declared, entry["file"])

    def test_tampering_is_detected(self):
        # 防伪报：改掉一个占用格，--check 必须报错
        entry = self.manifest["samples"][0]
        path = ROOT / "samples" / entry["file"]
        original = path.read_text(encoding="utf-8")
        data = json.loads(original)
        data["occupancy"]["must"].append([99, 99, 99])
        try:
            path.write_text(json.dumps(data), encoding="utf-8")
            problems = rebuild_samples.check()
            self.assertTrue(any(entry["file"] in p for p in problems))
        finally:
            path.write_text(original, encoding="utf-8")
        self.assertEqual(rebuild_samples.check(), [])

    def test_samples_load_through_grid_contract(self):
        # 直接加载样本并按样本里的尺度重建 Grid，占用层号都在界内
        for entry in self.manifest["samples"][:6]:
            data = json.loads((ROOT / "samples" / entry["file"]).read_text())
            n = data["grid"]["n"]
            for c in data["occupancy"]["may"]:
                self.assertEqual(len(c), 3)
                for a in range(3):
                    self.assertTrue(0 <= c[a] < n[a])

    def test_fresh_voxelizer_on_case_matches_committed_sample(self):
        # 独立复算一条样本，不经过 rebuild_samples，交叉防自证
        case = get_case("sheet_penetrate")
        g = grid_for_level("mid")
        table = Voxelizer(g).voxelize(list(case.triangles))
        data = json.loads((SAMPLE_DIR / "sheet_penetrate__mid.json")
                          .read_text(encoding="utf-8"))
        self.assertEqual(sorted(table.may),
                         [tuple(c) for c in data["occupancy"]["may"]])
        self.assertEqual(sorted(table.must),
                         [tuple(c) for c in data["occupancy"]["must"]])


if __name__ == "__main__":
    unittest.main()
