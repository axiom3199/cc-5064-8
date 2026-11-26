"""统一的空间格规则。

体素为闭集：[origin + i*h, origin + (i+1)*h]；位于共享边界面/边/角上的
几何同时归属相邻两侧的体素。体素化器、参考校验、连通测量与界面必须
共用同一 Grid 的 cell_range_closed 做"区间 -> 层号"映射，保证投影轴、
深度区间与体素边界归属规则完全一致。
"""
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Grid:
    origin: tuple = (0.0, 0.0, 0.0)
    cell: float = 1.0
    nx: int = 16
    ny: int = 16
    nz: int = 16
    eps: float = 1e-9  # 保守外扩量，用于吸收浮点误差（只会多标，不会漏标）

    def axis_n(self, axis):
        return (self.nx, self.ny, self.nz)[axis]

    def axis_lo(self, axis, i):
        return self.origin[axis] + i * self.cell

    def axis_hi(self, axis, i):
        return self.origin[axis] + (i + 1) * self.cell

    def cell_range_closed(self, lo, hi, axis):
        """闭区间 [lo, hi] 覆盖的层号 [k0, k1]（含两端）。

        区间端点恰好落在层界上时，两侧层号都包含（闭集归属规则）；
        eps 外扩保证浮点误差下保守方向永远是多标而非漏标。
        """
        o = self.origin[axis]
        h = self.cell
        k0 = math.ceil((lo - o) / h - self.eps) - 1
        k1 = math.floor((hi - o) / h + self.eps)
        return k0, k1

    def clamp(self, axis, k0, k1):
        n = self.axis_n(axis)
        return max(0, k0), min(n - 1, k1)

    def in_bounds(self, c):
        return 0 <= c[0] < self.nx and 0 <= c[1] < self.ny and 0 <= c[2] < self.nz

    def cell_center(self, i, j, k):
        o = self.origin
        h = self.cell
        return (o[0] + (i + 0.5) * h, o[1] + (j + 0.5) * h, o[2] + (k + 0.5) * h)

    def cell_lo(self, i, j, k):
        o = self.origin
        h = self.cell
        return (o[0] + i * h, o[1] + j * h, o[2] + k * h)

    def refined(self):
        """细分一层：边长减半，各轴层数翻倍。"""
        return Grid(self.origin, self.cell / 2.0,
                    self.nx * 2, self.ny * 2, self.nz * 2, self.eps)
