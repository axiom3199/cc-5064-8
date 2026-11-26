#!/usr/bin/env python3
"""体素几何样本重建脚本（真实体素化，严禁手填占用格）。

对 voxelizer/cases.py 的每个几何案例，在三级网格（base/mid/fine）上
调用 Voxelizer 实际体素化，生成可直接加载的体素样本 JSON，并写出：
- samples/voxels/<case>__<level>.json：单个样本（尺度、投影轴、
  参考相交数据、漏覆盖/多余体素、接触证据全部来自实际执行）；
- samples/manifest.json：样本清单与重建指纹（sha256），--check 用它
  核验入库样本未被手改、且当前体素化器能复现约定结果。

用法：
  python3 scripts/rebuild_samples.py            # 重建全部样本
  python3 scripts/rebuild_samples.py --check    # 只校验，不写文件
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from voxelizer.bounds import contact_evidence  # noqa: E402
from voxelizer.cases import LEVELS, get_case, grid_for_level, list_cases  # noqa: E402
from voxelizer.geometry import tri_box_overlap  # noqa: E402
from voxelizer.voxelizer import Voxelizer  # noqa: E402

SAMPLE_DIR = ROOT / "samples" / "voxels"
MANIFEST = ROOT / "samples" / "manifest.json"
SCHEMA_VERSION = 1


def reference_voxels(triangles, grid):
    """独立参考：包围盒内逐体素做三角形-盒解析相交（SAT 闭集）。"""
    half = (grid.cell / 2.0,) * 3
    ref = set()
    for tri in triangles:
        ranges = []
        for a in range(3):
            lo = min(p[a] for p in tri)
            hi = max(p[a] for p in tri)
            k0, k1 = grid.cell_range_closed(lo, hi, a)
            k0, k1 = grid.clamp(a, k0, k1)
            ranges.append(range(k0, k1 + 1))
        for i in ranges[0]:
            for j in ranges[1]:
                for k in ranges[2]:
                    if tri_box_overlap(grid.cell_center(i, j, k), half, tri):
                        ref.add((i, j, k))
    return ref


def _axes(table):
    """每个源面实际使用的投影轴；退化回退记 None。"""
    out = {}
    for r in table.raster:
        out[str(r["tri"])] = None if r["degenerate"] else r["axis"]
    return out


def build_sample(case, level):
    """对一个案例的一级网格执行真实体素化，组装样本字典。"""
    grid = grid_for_level(level)
    voxelizer = Voxelizer(grid)
    triangles = list(case.triangles)
    table = voxelizer.voxelize(triangles)
    verification = voxelizer.verify(triangles, table)
    evidence = contact_evidence(case, grid, table)
    return {
        "schema_version": SCHEMA_VERSION,
        "case": case.key,
        "level": level,
        "provenance": {
            "source": case.source,
            "builder": "scripts/rebuild_samples.py",
            "generator": "voxelizer.voxelizer.Voxelizer.voxelize",
            "reference": "voxelizer.geometry.tri_box_overlap (SAT 闭集)",
            "params": case.params,
        },
        "scale": {"level": level, "cell": grid.cell,
                  "n": [grid.nx, grid.ny, grid.nz],
                  "origin": list(grid.origin),
                  "level_index": LEVELS.index(level)},
        "grid": {"origin": list(grid.origin), "cell": grid.cell,
                 "n": [grid.nx, grid.ny, grid.nz]},
        "contact": {"declared": case.contact,
                    "observed": evidence.observed,
                    "evidence": evidence.as_dict()},
        "projection_axes": _axes(table),
        "triangles": [[list(p) for p in tri] for tri in triangles],
        "occupancy": {
            "must": sorted(table.must),
            "may": sorted(table.may),
            "may_only": sorted(table.may_only),
            "degenerate_triangles": list(table.degenerate),
        },
        "reference_intersection": {
            "voxels": sorted(reference_voxels(triangles, grid)),
            "count": verification.reference_count,
        },
        "verification": {
            "missed": sorted(verification.missed),
            "extra": sorted(verification.extra),
            "reference_count": verification.reference_count,
        },
        "stats": table.stats(),
    }


def _canonical_bytes(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _fingerprint(obj):
    return hashlib.sha256(_canonical_bytes(obj)).hexdigest()


def rebuild():
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    entries = []
    for case in list_cases():
        for level in LEVELS:
            sample = build_sample(case, level)
            name = f"{case.key}__{level}.json"
            path = SAMPLE_DIR / name
            path.write_text(json.dumps(sample, ensure_ascii=False, indent=1),
                            encoding="utf-8")
            entries.append({
                "file": f"voxels/{name}",
                "case": case.key,
                "level": level,
                "contact": case.contact,
                "observed": sample["contact"]["observed"],
                "cell": sample["scale"]["cell"],
                "must": sample["stats"]["must"],
                "may": sample["stats"]["may"],
                "may_only": sample["stats"]["may_only"],
                "missed": len(sample["verification"]["missed"]),
                "extra": len(sample["verification"]["extra"]),
                "sha256": _fingerprint(sample),
            })
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "levels": list(LEVELS),
        "base_n": 12,
        "count": len(entries),
        "samples": entries,
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    return manifest


def check():
    """复算全部样本并与入库文件、清单指纹比对；返回问题列表。"""
    problems = []
    if not MANIFEST.exists():
        return [f"缺少清单 {MANIFEST}（先运行 rebuild）"]
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    seen = set()
    for entry in manifest["samples"]:
        path = ROOT / "samples" / entry["file"]
        seen.add(entry["file"])
        if not path.exists():
            problems.append(f"缺少样本文件 {entry['file']}")
            continue
        stored = json.loads(path.read_text(encoding="utf-8"))
        if _fingerprint(stored) != entry["sha256"]:
            problems.append(f"样本被篡改或与清单指纹不符: {entry['file']}")
        # 不允许手填占用：用当前体素化器重新执行并逐项对照。
        # JSON 往返把元组/集合规范化为列表，与入库文件的类型对齐。
        case = get_case(entry["case"])
        fresh = json.loads(json.dumps(build_sample(case, entry["level"]),
                                      ensure_ascii=False))
        for field_ in ("occupancy", "verification", "projection_axes",
                       "reference_intersection", "stats", "contact",
                       "scale", "grid"):
            if stored.get(field_) != fresh[field_]:
                problems.append(f"{entry['file']} 的 {field_} 无法由当前"
                                f"体素化器复现（疑似手填或实现漂移）")
    on_disk = {f"voxels/{p.name}" for p in SAMPLE_DIR.glob("*.json")}
    orphan = on_disk - seen
    if orphan:
        problems.append(f"存在清单外样本: {sorted(orphan)}")
    return problems


def main():
    ap = argparse.ArgumentParser(description="体素几何样本重建/校验")
    ap.add_argument("--check", action="store_true",
                    help="只校验入库样本与当前体素化器输出，不写文件")
    args = ap.parse_args()
    if args.check:
        problems = check()
        if problems:
            for p in problems:
                print(f"FAIL: {p}", file=sys.stderr)
            return 1
        print(f"OK: {MANIFEST.relative_to(ROOT)} 全部样本与当前体素化器一致")
        return 0
    manifest = rebuild()
    print(f"重建 {manifest['count']} 个体素样本 -> {SAMPLE_DIR.relative_to(ROOT)}/")
    print(f"清单 -> {MANIFEST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
