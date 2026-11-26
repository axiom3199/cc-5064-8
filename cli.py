#!/usr/bin/env python3
"""体素覆盖命令行（辅助工具）。

注意：命令行仅辅助体素覆盖；图形入口见 README（python3 server.py）。
输出为表面占用（surface occupancy），不代表内部实心体积。
"""
import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import rebuild_samples  # noqa: E402
from voxelizer import scenes  # noqa: E402
from voxelizer.bounds import run_study  # noqa: E402
from voxelizer.connectivity import fine_verdict, measure_connectivity  # noqa: E402
from voxelizer.voxelizer import Voxelizer  # noqa: E402

NOTE = ("表面占用（surface occupancy）：仅表示三角形表面穿过哪些体素，"
        "不代表已获得内部实心体积；本工具不做内部填充。")


def _scene(args):
    return scenes.get_scene(args.scene, res=getattr(args, "res", None),
                            scale=getattr(args, "scale", None),
                            offset=tuple(getattr(args, "offset", (0, 0, 0))))


def _table_dict(table, ver):
    return {
        "note": NOTE,
        "grid": {"origin": list(table.grid.origin), "cell": table.grid.cell,
                 "n": [table.grid.nx, table.grid.ny, table.grid.nz]},
        "stats": table.stats(),
        "must": sorted(table.must),
        "may": sorted(table.may),
        "may_only": sorted(table.may_only),
        "sources": {f"{i},{j},{k}": sorted(s)
                    for (i, j, k), s in table.sources.items()},
        "degenerate_triangles": table.degenerate,
        "verification": {
            "missed": sorted(ver.missed),
            "extra": sorted(ver.extra),
            "reference_count": ver.reference_count,
        },
    }


def cmd_voxelize(args):
    sc = _scene(args)
    v = Voxelizer(sc.grid)
    table = v.voxelize(sc.triangles)
    ver = v.verify(sc.triangles, table)
    out = _table_dict(table, ver)
    text = json.dumps(out, ensure_ascii=False, indent=1)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"体素数据已写入 {args.out}", file=sys.stderr)
    else:
        print(text)
    s = out["stats"]
    print(f"must={s['must']} may={s['may']} may_only={s['may_only']} "
          f"missed={len(out['verification']['missed'])} "
          f"extra={len(out['verification']['extra'])}", file=sys.stderr)
    return 0 if not ver.missed else 1


def cmd_connectivity(args):
    sc = _scene(args)
    if not sc.connectivity:
        print(f"场景 {args.scene} 无连通测量配置", file=sys.stderr)
        return 2
    conn = sc.connectivity
    r = measure_connectivity(sc.triangles, sc.grid, args.budget,
                             axis=conn["axis"],
                             start_layer=conn["start_layer"],
                             goal_layer=conn["goal_layer"])
    fine = fine_verdict(sc.triangles, sc.grid, axis=conn["axis"],
                        start_layer=conn["start_layer"],
                        goal_layer=conn["goal_layer"])
    out = {
        "status": r.status, "levels": r.levels, "budget": r.budget,
        "message": r.message,
        "frontier": r.frontier,
        "undecided_cells": r.undecided_cells,
        "path": r.path,
        "fine_mesh_verdict": fine,
        "agrees_with_fine_mesh": r.status == fine,
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


def cmd_verify(args):
    sc = _scene(args)
    v = Voxelizer(sc.grid)
    table = v.voxelize(sc.triangles)
    ver = v.verify(sc.triangles, table)
    out = {
        "scene": args.scene,
        "missed": sorted(ver.missed),
        "extra": sorted(ver.extra),
        "reference_count": ver.reference_count,
        "may_count": len(table.may),
        "ok": not ver.missed,
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0 if not ver.missed else 1


def cmd_samples(args):
    if args.check:
        problems = rebuild_samples.check()
        if problems:
            for p in problems:
                print(f"FAIL: {p}", file=sys.stderr)
            return 1
        print("OK: 入库体素样本与当前体素化器输出一致")
        return 0
    manifest = rebuild_samples.rebuild()
    print(f"重建 {manifest['count']} 个真实体素样本（{len(manifest['levels'])} 级网格）")
    return 0


def cmd_bounds(args):
    studies = run_study()
    out = [asdict(s) for s in studies]
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0 if all(s.applicability != "review" for s in studies) else 1


def main(argv=None):
    p = argparse.ArgumentParser(
        description="保守光栅化表面体素化（命令行仅辅助体素覆盖；"
                    "图形入口：python3 server.py）")
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("voxelize", help="生成表面占用体素数据")
    v.add_argument("--scene", required=True, choices=list(scenes._BUILDERS))
    v.add_argument("--res", type=int, default=None)
    v.add_argument("--scale", type=float, default=None)
    v.add_argument("--offset", nargs=3, type=float, default=(0.0, 0.0, 0.0),
                   metavar=("DX", "DY", "DZ"))
    v.add_argument("--out", default=None, help="输出 JSON 文件（默认 stdout）")
    v.set_defaults(fn=cmd_voxelize)

    c = sub.add_parser("connectivity", help="空腔连通测量（含细网格复验）")
    c.add_argument("--scene", required=True,
                   choices=["duct_strip", "duct_paper", "duct_open"])
    c.add_argument("--budget", type=int, default=1, help="细分预算（层数）")
    c.set_defaults(fn=cmd_connectivity)

    f = sub.add_parser("verify", help="对照三角形-盒相交参考检查漏标/多标")
    f.add_argument("--scene", required=True, choices=list(scenes._BUILDERS))
    f.add_argument("--res", type=int, default=None)
    f.add_argument("--scale", type=float, default=None)
    f.set_defaults(fn=cmd_verify)

    sm = sub.add_parser("samples", help="重建/校验入库体素几何样本（辅助）")
    sm.add_argument("--check", action="store_true",
                    help="只校验入库样本与当前体素化器输出，不写文件")
    sm.set_defaults(fn=cmd_samples)

    bd = sub.add_parser("bounds", help="三级网格独立细分的接触上下界研究")
    bd.set_defaults(fn=cmd_bounds)

    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
