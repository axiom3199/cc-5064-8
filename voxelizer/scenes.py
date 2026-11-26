"""演示/测试场景。

孔道场景（duct_*）：z=6.13 处有一堵墙，墙上开了一条对角缝隙
（|y-x| <= 0.8 截断于 [3,9]^2 的六边形槽），缝隙在粗层（h=1）恰好
对应 {|i-j|<=1} 这一圈对角候选格。
- duct_strip：细斜片沿缝隙对角线放置、在格角 (k,k) 处擦过，并不封死缝隙；
- duct_paper：纸精确裁成缝隙形状，封死孔道；
二者在粗层得到相同的一圈候选格，连通测量必须细分才能区分。
- duct_open：无遮挡对照组。
"""
from dataclasses import dataclass, replace

from .grid import Grid

DUCT_Z = 6.13
SLOT_LO = 3.0     # 缝隙限制在 [3,9]^2 内
SLOT_HI = 9.0
SLOT_HALF = 0.8   # 缝隙半宽（|y-x| <= 0.8）
# 细斜片：|y-x-0.3| <= 0.3，下缘贴在 diagonal y=x 上、在格角 (k,k) 擦过，
# 只占缝隙的一侧，并未封死孔道
STRIP_OFF = 0.3
STRIP_HALF = 0.3


@dataclass
class Scene:
    key: str
    name: str
    description: str
    triangles: list
    grid: Grid
    connectivity: dict  # {"axis", "start_layer", "goal_layer"} 或 None
    scalable: bool = False
    fixed_res: bool = False


def _quad(a, b, c, d):
    return [(a, b, c), (a, c, d)]


def _slot_hexagon(z):
    """缝隙六边形：|y-x| <= SLOT_HALF 截断于 [3,9]^2。"""
    lo, hi, w = SLOT_LO, SLOT_HI, SLOT_HALF
    return [(lo, lo, z), (lo + w, lo, z), (hi, hi - w, z),
            (hi, hi, z), (hi - w, hi, z), (lo, lo + w, z)]


def _wall_tris():
    """[0,12]^2 平面减去缝隙六边形，z=DUCT_Z。"""
    z = DUCT_Z
    lo, hi, w = SLOT_LO, SLOT_HI, SLOT_HALF
    tris = []
    tris += _quad((0, 0, z), (12, 0, z), (12, lo, z), (0, lo, z))     # 下
    tris += _quad((0, hi, z), (12, hi, z), (12, 12, z), (0, 12, z))   # 上
    tris += _quad((0, lo, z), (lo, lo, z), (lo, hi, z), (0, hi, z))   # 左
    tris += _quad((hi, lo, z), (12, lo, z), (12, hi, z), (hi, hi, z))  # 右
    # [3,9]^2 内、缝隙两侧的两个三角形
    tris.append(((lo + w, lo, z), (hi, lo, z), (hi, hi - w, z)))
    tris.append(((lo, lo + w, z), (lo, hi, z), (hi - w, hi, z)))
    return tris


def _duct_grid():
    return Grid((0.0, 0.0, 0.0), 1.0, 12, 12, 12)


def _connectivity_cfg():
    return {"axis": 2, "start_layer": 0, "goal_layer": None}


def scene_duct_strip():
    # 细斜片：|y-x-0.3| <= 0.3 的斜带，下缘恰好贴在 diagonal y=x 上、
    # 在格角 (3,3),(4,4),...,(9,9) 处擦过，两端埋入墙内
    z = DUCT_Z
    lo = SLOT_LO - STRIP_OFF + 0.2   # 2.9，端头埋入墙内
    hi = SLOT_HI + STRIP_OFF - 0.1   # 9.2
    a = (lo, lo, z)
    b = (hi, hi, z)
    c = (hi, hi + 2 * STRIP_HALF, z)
    d = (lo, lo + 2 * STRIP_HALF, z)
    tris = _wall_tris() + _quad(a, b, c, d)
    return Scene("duct_strip", "细斜片（格角擦过）",
                 "细斜片贴对角线放置、下缘在格角擦过，粗层候选格与封孔纸相同，"
                 "但并未封死孔道；连通测量需细分判定。",
                 tris, _duct_grid(), _connectivity_cfg(), fixed_res=True)


def scene_duct_paper():
    hexagon = _slot_hexagon(DUCT_Z)
    # 扇形三角化六边形纸，精确封死缝隙
    tris = _wall_tris()
    for k in range(1, 5):
        tris.append((hexagon[0], hexagon[k], hexagon[k + 1]))
    return Scene("duct_paper", "封孔纸",
                 "一张纸裁成对角缝隙的形状，精确封死孔道；"
                 "粗层候选格与细斜片相同，连通测量细分后应判定为隔断。",
                 tris, _duct_grid(), _connectivity_cfg(), fixed_res=True)


def scene_duct_open():
    return Scene("duct_open", "空孔道（对照）",
                 "只有带对角缝隙的墙，无遮挡物。",
                 _wall_tris(), _duct_grid(), _connectivity_cfg(),
                 fixed_res=True)


def scene_tiny_corner():
    # 贴着格角 (4,4,4) 的细三角，投影不含任何像素中心
    tri = [((4.02, 4.03, 4.01), (4.09, 4.02, 4.03), (4.03, 4.10, 4.02))]
    return Scene("tiny_corner", "贴格角细三角",
                 "细小三角形不含任何像素中心，保守覆盖也不能遗漏；"
                 "可能交与必交分开记录，可对照解析交集。",
                 tri, Grid((0.0, 0.0, 0.0), 1.0, 8, 8, 8), None)


def scene_eps_graze():
    # 薄三角悬在格平面 z=7 之下 eps 内：保守外扩会把上一层标成
    # 可能交（伪占用），解析测试不确认 —— 演示 must/may_only 分离
    z = 7.0 - 4e-10
    tri = [((2.2, 2.2, z), (5.8, 2.2, z), (2.2, 5.8, z))]
    return Scene("eps_graze", "贴格界薄片（伪占用演示）",
                 "薄三角贴着格平面下缘 eps 内：保守覆盖把上一层标为可能交"
                 "（伪占用），必交/可能交分开记录并可对照解析交集。",
                 tri, Grid((0.0, 0.0, 0.0), 1.0, 12, 12, 12), None)


def scene_grid_point_tri():
    tri = [((2.0, 2.0, 3.0), (6.0, 2.0, 3.0), (4.0, 6.0, 3.0))]
    return Scene("grid_point_tri", "穿过格点的三角形",
                 "顶点恰好落在格点上、三角形躺在格平面上，"
                 "用于核对统一的体素边界归属规则（闭集，两侧归属）。",
                 tri, Grid((0.0, 0.0, 0.0), 1.0, 8, 8, 8), None)


def scene_tetra(scale=1.0):
    s = scale
    v = [(2, 2, 2), (8, 2, 2), (5, 8, 3), (5, 3, 9)]
    v = [tuple(x * s for x in p) for p in v]
    tris = [(v[0], v[2], v[1]), (v[0], v[1], v[3]),
            (v[1], v[2], v[3]), (v[2], v[0], v[3])]
    return Scene("tetra", "四面体",
                 "不同尺度模型之一：整体缩放下核对漏标/多标。",
                 tris, Grid((0.0, 0.0, 0.0), 1.0 * s, 12, 12, 12), None,
                 scalable=True)


def scene_cube(scale=1.0):
    s = scale
    lo = 3.0 * s
    hi = 9.0 * s
    c = [(lo, lo, lo), (hi, lo, lo), (hi, hi, lo), (lo, hi, lo),
         (lo, lo, hi), (hi, lo, hi), (hi, hi, hi), (lo, hi, hi)]
    tris = [
        (c[0], c[2], c[1]), (c[0], c[3], c[2]),  # 底
        (c[4], c[5], c[6]), (c[4], c[6], c[7]),  # 顶
        (c[0], c[1], c[5]), (c[0], c[5], c[4]),  # 前
        (c[2], c[7], c[6]), (c[2], c[3], c[7]),  # 后
        (c[1], c[2], c[6]), (c[1], c[6], c[5]),  # 右
        (c[0], c[4], c[7]), (c[0], c[7], c[3]),  # 左
    ]
    return Scene("cube", "立方体网格",
                 "12 个三角形组成的立方体表面，不同尺度下核对漏标/多标。",
                 tris, Grid((0.0, 0.0, 0.0), 1.0 * s, 12, 12, 12), None,
                 scalable=True)


_BUILDERS = {
    "duct_strip": scene_duct_strip,
    "duct_paper": scene_duct_paper,
    "duct_open": scene_duct_open,
    "tiny_corner": scene_tiny_corner,
    "eps_graze": scene_eps_graze,
    "grid_point_tri": scene_grid_point_tri,
    "tetra": scene_tetra,
    "cube": scene_cube,
}


def list_scenes():
    out = []
    for key, b in _BUILDERS.items():
        sc = b()
        out.append({"key": key, "name": sc.name, "description": sc.description,
                    "has_connectivity": sc.connectivity is not None,
                    "scalable": sc.scalable, "fixed_res": sc.fixed_res,
                    "res": sc.grid.nx})
    return out


def get_scene(key, res=None, scale=None, offset=(0.0, 0.0, 0.0)):
    if key not in _BUILDERS:
        raise ValueError(f"未知场景: {key}")
    if scale is not None and scale != 1.0:
        if not _BUILDERS[key]().scalable:
            raise ValueError(f"场景 {key} 不支持缩放")
        sc = scene_tetra(scale) if key == "tetra" else scene_cube(scale)
    else:
        sc = _BUILDERS[key]()
    if res is not None and res != sc.grid.nx:
        if sc.fixed_res:
            raise ValueError(f"场景 {key} 分辨率固定为 {sc.grid.nx}"
                             f"（连通细分由测量内部完成）")
        sc.grid = replace(sc.grid, nx=res, ny=res, nz=res)
    if offset != (0.0, 0.0, 0.0):
        dx, dy, dz = offset
        sc.triangles = [
            tuple((p[0] + dx, p[1] + dy, p[2] + dz) for p in tri)
            for tri in sc.triangles
        ]
    return sc
