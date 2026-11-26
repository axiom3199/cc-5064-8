"""表面体素化器：保守覆盖 -> 候选体素 -> 解析精测分类 必交/可能交。

输出为**表面占用**（surface occupancy）：只表示三角形表面穿过哪些体素，
不代表已获得内部实心体积；本库不做内部填充。

- must（必交）：候选体素经三角形-盒相交解析测试确认相交。
- may （可能交）：保守光栅化覆盖的全部候选体素（含 must）；
  may - must 即保守覆盖带来的伪占用（如薄三角贴着格角时的 eps 外扩格）。
- 退化投影（法向量近零、无法选轴）回退：直接在三角形包围盒内逐格
  做解析相交测试，must 与 may 相同。
"""
from dataclasses import dataclass, field

from .conservative import dominant_axis, project_triangle_coverage
from .geometry import tri_box_overlap, tri_normal, vlen, vsub
from .grid import Grid


@dataclass
class VoxelTable:
    """体素表：同时供轮廓预览（may 保守占格）与空腔连通测量使用。"""
    grid: Grid
    triangles: list
    must: set           # 必交体素 {(i,j,k)}
    may: set            # 可能交体素（保守覆盖，含 must）
    sources: dict       # (i,j,k) -> {三角形编号}
    raster: list        # 每个三角形的光栅调试信息
    degenerate: list    # 走退化回退的三角形编号

    @property
    def may_only(self):
        return self.may - self.must

    def stats(self):
        return {
            "must": len(self.must),
            "may": len(self.may),
            "may_only": len(self.may_only),
            "degenerate": len(self.degenerate),
        }


@dataclass
class Verification:
    """与独立三角形-盒相交参考的对照结果。"""
    missed: set          # 参考有、保守覆盖无：漏标（必须为空）
    extra: set           # 保守覆盖有、参考无：多标（保守伪占用）
    reference_count: int


class Voxelizer:
    def __init__(self, grid):
        self.grid = grid

    def voxelize(self, triangles):
        g = self.grid
        must = set()
        may = set()
        sources = {}
        raster = []
        degenerate = []
        half = (g.cell / 2.0,) * 3

        for tid, tri in enumerate(triangles):
            n = tri_normal(tri)
            edge_max = max(
                vlen(vsub(tri[1], tri[0])),
                vlen(vsub(tri[2], tri[1])),
                vlen(vsub(tri[0], tri[2])),
            )
            if edge_max == 0.0 or vlen(n) <= 1e-12 * edge_max * edge_max:
                # 退化投影回退：无法选轴，改为包围盒内逐格解析测试
                degenerate.append(tid)
                cells = self._fallback_cells(tri)
                raster.append({"tri": tid, "degenerate": True,
                               "cells": sorted(cells)})
                for c in cells:
                    may.add(c)
                    must.add(c)
                    sources.setdefault(c, set()).add(tid)
                continue

            axis = dominant_axis(n)
            coverages, tri2d, (u, v) = project_triangle_coverage(g, tri, axis)
            pixels = []
            for cov in coverages:
                k0, k1 = g.cell_range_closed(cov.dmin, cov.dmax, axis)
                k0, k1 = g.clamp(axis, k0, k1)
                cells = []
                for k in range(k0, k1 + 1):
                    vox = [0, 0, 0]
                    vox[u] = cov.i
                    vox[v] = cov.j
                    vox[axis] = k
                    vox = tuple(vox)
                    exact = tri_box_overlap(g.cell_center(*vox), half, tri)
                    may.add(vox)
                    if exact:
                        must.add(vox)
                    sources.setdefault(vox, set()).add(tid)
                    cells.append({"voxel": vox, "exact": exact})
                pixels.append({
                    "i": cov.i, "j": cov.j,
                    "dmin": cov.dmin, "dmax": cov.dmax,
                    "center_hit": cov.center_hit,
                    "cells": cells,
                })
            raster.append({"tri": tid, "degenerate": False, "axis": axis,
                           "uv": (u, v), "tri2d": tri2d, "pixels": pixels})

        return VoxelTable(g, list(triangles), must, may, sources,
                          raster, degenerate)

    def _fallback_cells(self, tri):
        """退化三角形回退：包围盒内逐格解析相交（闭集）。"""
        g = self.grid
        half = (g.cell / 2.0,) * 3
        ranges = []
        for a in range(3):
            lo = min(p[a] for p in tri)
            hi = max(p[a] for p in tri)
            k0, k1 = g.cell_range_closed(lo, hi, a)
            k0, k1 = g.clamp(a, k0, k1)
            ranges.append(range(k0, k1 + 1))
        cells = set()
        for i in ranges[0]:
            for j in ranges[1]:
                for k in ranges[2]:
                    if tri_box_overlap(g.cell_center(i, j, k), half, tri):
                        cells.add((i, j, k))
        return cells

    def verify(self, triangles, table=None):
        """对照独立参考（逐体素 tri_box_overlap）检查漏标与多标。"""
        g = self.grid
        if table is None:
            table = self.voxelize(triangles)
        half = (g.cell / 2.0,) * 3
        reference = set()
        for tri in triangles:
            ranges = []
            for a in range(3):
                lo = min(p[a] for p in tri)
                hi = max(p[a] for p in tri)
                k0, k1 = g.cell_range_closed(lo, hi, a)
                k0, k1 = g.clamp(a, k0, k1)
                ranges.append(range(k0, k1 + 1))
            for i in ranges[0]:
                for j in ranges[1]:
                    for k in ranges[2]:
                        if tri_box_overlap(g.cell_center(i, j, k), half, tri):
                            reference.add((i, j, k))
        return Verification(reference - table.may, table.may - reference,
                            len(reference))
