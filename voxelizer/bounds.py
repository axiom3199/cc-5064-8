"""接触类型证据与独立细分上下界研究。

接触类型用**真实体素输出**区分，而不是靠案例标签断言：
- straddle（穿入证据）：非退化三角形的某个覆盖像素，深度区间严格跨越
  格界（dmin < B < dmax，留容差），说明表面真正穿入相邻体素；
- touch（擦边证据）：深度区间端点恰好落在格界上（闭集双归属），
  但不跨越；退化回退则用段端点落在格点/格界上的数量作证；
- hover（留缝证据）：保守覆盖里出现解析不确认的 may_only 体素，
  即表面与格界的间隙被保守外扩吞掉。

独立细分：三级网格（h=1, 0.5, 0.25）各自独立重新体素化，记录
must/may/may_only、漏标（必须恒为空）、多标到表面的最大距离与
接触证据，据此标定"用细分建立接触上下界"的适用范围。
"""
from dataclasses import asdict, dataclass

from .cases import LEVELS, get_case, grid_for_level
from .geometry import point_triangle_distance
from .voxelizer import Voxelizer

# 接触判定只认真正的贴界：远小于最细网格（h=0.25）的一个相对小量
TOUCH_TOL = 1e-7


@dataclass
class ContactEvidence:
    contact: str               # 案例声明的接触类型（graze/penetrate/gap）
    straddle_pixels: int = 0   # 深度区间严格跨越格界的像素
    touch_pixels: int = 0      # 深度端点落在格界上的像素
    hover_voxels: int = 0      # may_only 体素数
    boundary_points: int = 0   # 退化回退：落在格点/格界上的几何顶点
    degenerate: bool = False

    @property
    def observed(self):
        """从体素输出观察到的接触类型。"""
        if self.straddle_pixels:
            return "penetrate"
        if self.hover_voxels:
            return "gap"
        if self.touch_pixels or self.boundary_points:
            return "graze"
        return "interior"

    def as_dict(self):
        d = asdict(self)
        d["observed"] = self.observed
        return d


def _on_boundary(value, grid, axis):
    k0, k1 = grid.cell_range_closed(value, value, axis)
    return k0 != k1


def contact_evidence(case, grid, table):
    """从一次真实体素化的输出提取接触证据。"""
    ev = ContactEvidence(contact=case.contact,
                         degenerate=case.expect_degenerate)
    if case.expect_degenerate:
        for tri in case.triangles:
            for p in tri:
                if all(_on_boundary(p[a], grid, a) for a in range(3)):
                    ev.boundary_points += 1
        ev.hover_voxels = len(table.may_only)
        return ev

    for r in table.raster:
        if r["degenerate"]:
            continue
        axis = r["axis"]
        h = grid.cell
        for p in r["pixels"]:
            dmin, dmax = p["dmin"], p["dmax"]
            k0 = int((dmin - grid.origin[axis]) / h)
            k1 = int((dmax - grid.origin[axis]) / h)
            straddled = False
            for k in range(k0, k1 + 2):
                b = grid.origin[axis] + k * h
                if dmin + TOUCH_TOL < b < dmax - TOUCH_TOL:
                    ev.straddle_pixels += 1
                    straddled = True
                    break
            if straddled:
                continue
            near_lo = abs(dmin - (grid.origin[axis] +
                                  round((dmin - grid.origin[axis]) / h) * h))
            near_hi = abs(dmax - (grid.origin[axis] +
                                  round((dmax - grid.origin[axis]) / h) * h))
            if near_lo <= TOUCH_TOL or near_hi <= TOUCH_TOL:
                ev.touch_pixels += 1
    ev.hover_voxels = len(table.may_only)
    return ev


@dataclass
class LevelResult:
    level: str
    cell: float
    n: list
    must: int
    may: int
    may_only: int
    missed: int
    extra: int
    reference_count: int
    max_extra_distance: float
    evidence: dict


@dataclass
class CaseStudy:
    key: str
    contact: str
    levels: list
    applicability: str
    detail: str


def _max_extra_distance(grid, extra, triangles):
    if not extra:
        return 0.0
    worst = 0.0
    for c in extra:
        ctr = grid.cell_center(*c)
        d = min(point_triangle_distance(ctr, t) for t in triangles)
        worst = max(worst, d)
    return worst


def study_case(key):
    """对单个案例在三级网格上独立体素化，建立接触上下界证据。"""
    case = get_case(key)
    levels = []
    for lv in LEVELS:
        g = grid_for_level(lv)
        v = Voxelizer(g)
        table = v.voxelize(list(case.triangles))
        ver = v.verify(list(case.triangles), table)
        ev = contact_evidence(case, g, table)
        levels.append(LevelResult(
            level=lv, cell=g.cell, n=[g.nx, g.ny, g.nz],
            must=len(table.must), may=len(table.may),
            may_only=len(table.may_only),
            missed=len(ver.missed), extra=len(ver.extra),
            reference_count=ver.reference_count,
            max_extra_distance=_max_extra_distance(g, ver.extra,
                                                   list(case.triangles)),
            evidence=ev.as_dict()))
    applicability, detail = _applicability(case, levels)
    return CaseStudy(key, case.contact,
                     [asdict(x) for x in levels], applicability, detail)


def _applicability(case, levels):
    """根据三级证据给出细分上下界的适用范围结论。levels 为 LevelResult。"""
    observed = [lv.evidence["observed"] for lv in levels]
    no_miss = all(lv.missed == 0 for lv in levels)
    extras = [lv.extra for lv in levels]
    dists = [lv.max_extra_distance for lv in levels]
    hovers = [lv.evidence["hover_voxels"] for lv in levels]

    if case.contact == "gap":
        if hovers[-1] == 0 and hovers[0] > 0 and no_miss:
            return ("limited",
                    "留缝间隙（4e-10）小于粗网格的绝对外扩容差，粗层与中层"
                    "出现 may_only 伪占用；细到 h=0.25 后容差相对格宽可忽略，"
                    "伪占用消失、接触还原为贴界擦边。细分上下界只在间隙大于"
                    "该级容差时可分离真接触与留缝，更细前只能给出保守上界。")
        if all(h > 0 for h in hovers) and no_miss:
            return ("limited",
                    "留缝间隙小于绝对外扩容差，may_only 带在三级网格均不消失："
                    "细分能收缩几何带宽，却不能消除浮点容差级的可能交，"
                    "上下界在该尺度下无法判定为确定自由。")
    if case.contact == "penetrate":
        shrinks = all(extras[i + 1] <= extras[i]
                      and dists[i + 1] <= dists[i] + 1e-12
                      for i in range(len(extras) - 1))
        always_penetrates = all(o == "penetrate" for o in observed)
        if always_penetrates and no_miss and shrinks:
            return ("valid",
                    "三级网格均观察到跨层穿入证据且无漏标，多标数量与到表面的"
                    "最大距离随细分单调不增：细分建立的 must/may 上下界有效，"
                    "穿入结论与分辨率无关。")
    if case.contact == "graze":
        never_gap = all(o != "gap" for o in observed)
        if never_gap and no_miss:
            return ("valid",
                    "擦边接触在三级网格均被解析参考确认（闭集双归属）、无漏标："
                    "细分保持必交下界覆盖贴界格，接触结论稳定；双归属本身"
                    "不会因细分消失，这是闭集语义而非保守伪占用。")
    return ("review", "三级证据不一致或出现漏标，需人工复核。")


def run_study(keys=None):
    if keys is None:
        from .cases import _BUILDERS
        keys = list(_BUILDERS)
    return [study_case(k) for k in keys]
