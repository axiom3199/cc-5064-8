"""自制退化几何案例素材包：薄片、斜面、尖角与轴向退化。

每个案例都带**已知接触类型**（contact）：
- graze：擦边——几何恰好贴在格界/格点上（闭集双归属）；
- penetrate：穿入——几何真正穿入体素层，像素深度区间跨越格界；
- gap：留缝——几何悬在格界外一个小于外扩容差的间隙内，只有可能交。

素材尺度跨越三级网格（base / h=1，mid / h=0.5，fine / h=0.25，
层数 12 / 24 / 48），案例几何在三级网格间保持原尺度，因此"擦边"在
每一级都落在整数格界上，可核验接触类型在细分下的稳定性。

来源与参数随案例、样本一起保存（见 provenance / params 字段）；
体素占用只能由 Voxelizer 实际体素化得到，本模块不提供任何手填占用格。
"""
from dataclasses import dataclass

from .grid import Grid

# 三级网格：同一原点与几何尺度，边长 1 -> 1/2 -> 1/4
LEVELS = ("base", "mid", "fine")
BASE_N = 12


def grid_for_level(level):
    if level not in LEVELS:
        raise ValueError(f"未知网格级别: {level}（可选 {LEVELS}）")
    k = LEVELS.index(level)
    return Grid((0.0, 0.0, 0.0), 1.0 / (2 ** k),
                BASE_N * (2 ** k), BASE_N * (2 ** k), BASE_N * (2 ** k))


def all_grids():
    return {lv: grid_for_level(lv) for lv in LEVELS}


@dataclass(frozen=True)
class GeometryCase:
    key: str
    name: str
    description: str
    contact: str                 # graze | penetrate | gap
    params: dict                 # 几何来源参数（可重建）
    triangles: tuple             # ((p, p, p), ...)，元组保证不可变
    expect_degenerate: bool = False
    expect_axis: int = -1        # 期望投影轴；-1 表示退化回退（无投影轴）
    source: str = "voxelizer/cases.py"


def _quad(a, b, c, d):
    return ((a, b, c), (a, c, d))


def _box_tris(lo, hi):
    """轴对齐盒表面 12 个三角形（极薄盒即薄片实体）。"""
    c = [lo, (hi[0], lo[1], lo[2]), (hi[0], hi[1], lo[2]),
         (lo[0], hi[1], lo[2]), (lo[0], lo[1], hi[2]),
         (hi[0], lo[1], hi[2]), hi, (lo[0], hi[1], hi[2])]
    return (
        (c[0], c[2], c[1]), (c[0], c[3], c[2]),
        (c[4], c[5], c[6]), (c[4], c[6], c[7]),
        (c[0], c[1], c[5]), (c[0], c[5], c[4]),
        (c[2], c[7], c[6]), (c[2], c[3], c[7]),
        (c[1], c[2], c[6]), (c[1], c[6], c[5]),
        (c[0], c[4], c[7]), (c[0], c[7], c[3]),
    )


# ---------- 薄片（零厚度面） ----------

def case_sheet_graze():
    # 薄片恰好躺在格平面 z=7 上：闭集规则同时归属第 6、7 层 —— 擦边
    z = 7.0
    tris = _quad((2.0, 2.0, z), (10.0, 2.0, z),
                 (10.0, 10.0, z), (2.0, 10.0, z))
    return GeometryCase(
        "sheet_graze", "薄片擦边（贴格平面）",
        "零厚度薄片恰好躺在格平面 z=7 上，按闭集规则同时归属相邻两层，"
        "接触类型为擦边；三级网格下整数平面持久存在。",
        "graze", {"plane_axis": 2, "plane_value": z,
                  "x_range": [2.0, 10.0], "y_range": [2.0, 10.0]},
        tris, expect_axis=2)


def case_sheet_penetrate():
    # 薄片深度从 3.3 连续变到 5.1、穿过格平面 z=4/5，且没有顶点落在
    # 整数 z 上：覆盖像素的深度区间严格跨越层界 —— 穿入
    tris = ((2.0, 2.0, 3.3), (10.0, 2.0, 5.1), (2.0, 10.0, 3.9)),
    return GeometryCase(
        "sheet_penetrate", "薄片穿入（跨层倾斜）",
        "倾斜薄片的深度从 3.3 连续变到 5.1、穿过格平面 z=4 与 z=5，"
        "且无顶点贴整数层，像素深度区间严格跨越层界，接触类型为穿入，"
        "与贴格平面的擦边用真实体素输出区分。",
        "penetrate", {"z_vertex": [3.3, 5.1, 3.9]},
        tris, expect_axis=2)


def case_eps_hover():
    # 薄片悬在格平面 z=7 之下 4e-10：小于网格 eps 外扩量 -> 只有可能交
    z = 7.0 - 4e-10
    tris = _quad((2.0, 2.0, z), (10.0, 2.0, z),
                 (10.0, 10.0, z), (2.0, 10.0, z))
    return GeometryCase(
        "eps_hover", "薄片留缝（eps 悬空间隙）",
        "薄片与格平面间隙 4e-10，小于保守外扩量：第 7 层只被标为可能交"
        "（may_only），解析测试不确认；细分无法把绝对浮点容差吸走，"
        "用于标定独立细分上下界的适用范围。",
        "gap", {"plane_axis": 2, "plane_value": z, "gap": 4e-10},
        tris, expect_axis=2)


# ---------- 极薄面（真实厚度薄盒） ----------

def case_wafer_graze():
    # 厚度 1e-3 的薄盒跨在格平面 z=7 上：真实穿入相邻两层，但厚度远小于格宽
    t = 1e-3
    lo = (2.0, 2.0, 7.0 - t / 2.0)
    hi = (10.0, 10.0, 7.0 + t / 2.0)
    tris = _box_tris(lo, hi)
    return GeometryCase(
        "wafer_graze", "极薄面（薄盒跨格界）",
        "厚度 1e-3 的薄盒跨在格平面 z=7 两侧，三级网格下厚度均远小于格宽"
        "（1、0.5、0.25），演示极薄实体的擦边式占用而不依赖零厚度。",
        "graze", {"thickness": t, "center_plane": 7.0,
                  "footprint": [[2.0, 10.0], [2.0, 10.0]]},
        tris, expect_axis=2)


# ---------- 斜面 ----------

def case_incline_graze():
    # 45° 斜面过格点 (2,2,4) 且整体位于切平面一侧、只在该点贴格点 —— 擦边
    tris = ((2.0, 2.0, 4.0), (9.0, 2.0, 11.0), (2.0, 9.0, 4.0)),
    return GeometryCase(
        "incline_graze", "斜面擦边（45° 过格点）",
        "45° 斜面经过格点 (2,2,4) 且整体位于切平面一侧，仅在格点处接触，"
        "解析参考必须包含该格点体素，接触类型为擦边。",
        "graze", {"anchor": [2.0, 2.0, 4.0], "slope": 1.0},
        tris, expect_axis=2)


def case_incline_penetrate():
    # 45° 斜面两端分别落在 z=3.2 与 z=4.8 的层内，连续穿过 z=4 —— 穿入
    tris = ((2.0, 2.0, 3.2), (9.0, 2.0, 10.2), (2.0, 9.0, 3.2)),
    return GeometryCase(
        "incline_penetrate", "斜面穿入（45° 跨层）",
        "45° 斜面深度从 3.2 连续升至 10.2、穿过多个格平面，"
        "穿入体素的像素深度区间严格跨越层界，与斜面擦边形成对照。",
        "penetrate", {"z_lo": 3.2, "z_hi": 10.2, "slope": 1.0},
        tris, expect_axis=2)


# ---------- 尖角 ----------

def case_spike_graze():
    # 轴向细针（退化三角形）：针尖恰好顶在格点 (6,6,6)，针身沿 z 轴下行，
    # 无横向移动，只在针尖与整数层处接触，三级网格均为纯擦边
    tip = (6.0, 6.0, 6.0)
    base = (6.0, 6.0, 3.0)
    tris = ((tip, base, base),)
    return GeometryCase(
        "spike_graze", "尖角擦边（针尖顶格点）",
        "轴向细针的针尖恰好顶在格点 (6,6,6)，针身沿 z 轴下行、无横向移动；"
        "退化为线段走解析回退，针尖端体素经解析确认相交且接触为擦边。",
        "graze", {"tip": list(tip), "base": list(base), "shape": "needle"},
        tris, expect_degenerate=True, expect_axis=-1)


def case_spike_penetrate():
    # 实体细针平移 0.3：针尖进入层内、针身斜跨多个格平面 —— 穿入
    tip = (6.3, 6.3, 6.3)
    base_a = (5.9, 6.1, 2.1)
    base_b = (6.7, 6.1, 2.1)
    base_c = (6.3, 6.7, 2.1)
    tris = (
        (tip, base_a, base_b),
        (tip, base_b, base_c),
        (tip, base_c, base_a),
        (base_a, base_c, base_b),
    )
    return GeometryCase(
        "spike_penetrate", "尖角穿入（针尖入层）",
        "实体细针的针尖进入体素内部、三条棱斜向穿过多个格平面，穿入证据为"
        "深度区间跨越层界的像素，与尖角擦边仅差一个平移，且为非退化三角化。",
        "penetrate", {"tip": list(tip), "base_z": 2.1,
                      "base_radius": 0.4, "shape": "solid_needle"},
        tris, expect_axis=2)


# ---------- 轴向退化（共线/重合，法向量为零，走包围盒解析回退） ----------

def case_axis_degenerate():
    # 共线三角形：段从 (2,4,4) 到 (10,8,8)，端点与中点均落在格点上
    p = (2.0, 4.0, 4.0)
    q = (10.0, 8.0, 8.0)
    m = (6.0, 6.0, 6.0)
    tris = ((p, q, m),)
    return GeometryCase(
        "axis_degenerate", "轴向退化（共线段穿格点）",
        "共线退化三角形无法选投影轴，走包围盒逐格解析回退；"
        "线段端点与中点都在格点上，回退路径同样遵守闭集归属、不得漏标。",
        "graze", {"segment": [list(p), list(q)], "midpoint": list(m)},
        tris, expect_degenerate=True, expect_axis=-1)


def case_axis_dup_point():
    # 重合点三角形：退化为沿 x 轴的线段，起点在格点上
    p = (3.0, 5.0, 5.0)
    q = (9.0, 5.0, 5.0)
    tris = ((p, q, q),)
    return GeometryCase(
        "axis_dup_point", "轴向退化（重合点段）",
        "两个顶点重合的三角形退化为沿 x 轴的线段，同样走解析回退；"
        "起点位于格点，核验退化回退在三轴方向上的层号归属。",
        "graze", {"segment": [list(p), list(q)], "duplicated": "v1=v2"},
        tris, expect_degenerate=True, expect_axis=-1)


_BUILDERS = {
    "sheet_graze": case_sheet_graze,
    "sheet_penetrate": case_sheet_penetrate,
    "eps_hover": case_eps_hover,
    "wafer_graze": case_wafer_graze,
    "incline_graze": case_incline_graze,
    "incline_penetrate": case_incline_penetrate,
    "spike_graze": case_spike_graze,
    "spike_penetrate": case_spike_penetrate,
    "axis_degenerate": case_axis_degenerate,
    "axis_dup_point": case_axis_dup_point,
}


def list_cases():
    return [b() for b in _BUILDERS.values()]


def get_case(key):
    if key not in _BUILDERS:
        raise ValueError(f"未知几何案例: {key}")
    return _BUILDERS[key]()
