"""空腔连通测量：在体素表上做 6-连通洪泛。

预览可以保守占格（may），但连通测量遇到会决定孔道通断的格子时：
  1. 精测——每个候选体素都已做三角形-盒相交解析测试（must/may 分类）；
  2. 细分——预算允许时把空间格边长减半重新体素化，收缩保守带宽；
  3. 未决——预算耗尽仍无法判定时返回 undecided 并给出未决区域。

结论语义：
- connected：找到一条完全由"确定自由"（不在保守覆盖 may 中）体素
  组成的 6-连通通路，此结论与分辨率无关，是物理可信的。
- blocked：细分到预算上限后，精确占用（must，全部经解析确认、无
  未决格）仍隔断两侧。这是当前分辨率下的体素级结论，应用方可用
  fine_verdict 的细网格通路复验。
- undecided：细分预算耗尽，决定通断的格子未全部判定。
"""
from collections import deque
from dataclasses import dataclass, field

from .voxelizer import Voxelizer

_NEIGHBOR_DELTAS = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0),
                    (0, 0, 1), (0, 0, -1))


@dataclass
class ConnectivityResult:
    status: str                 # "connected" | "blocked" | "undecided"
    levels: int                 # 实际使用的细分层数
    budget: int                 # 细分预算（允许的细分层数）
    grid: object                # 得出该结论时的空间格（可能已细分）
    path: list = field(default_factory=list)          # connected 时的通路
    frontier: list = field(default_factory=list)      # 决定通断的候选格
    undecided_cells: list = field(default_factory=list)  # 未决区域
    message: str = ""


def _layer_cells(grid, axis, layer):
    a0, a1 = [a for a in range(3) if a != axis]
    for u in range(grid.axis_n(a0)):
        for v in range(grid.axis_n(a1)):
            c = [0, 0, 0]
            c[a0] = u
            c[a1] = v
            c[axis] = layer
            yield tuple(c)


def flood_reach(grid, blocked, axis, start_layer):
    """从 start_layer 的所有非阻塞体素出发的 6-连通可达集。"""
    dq = deque()
    reach = set()
    for c in _layer_cells(grid, axis, start_layer):
        if c not in blocked:
            dq.append(c)
            reach.add(c)
    while dq:
        c = dq.popleft()
        for d in _NEIGHBOR_DELTAS:
            nb = (c[0] + d[0], c[1] + d[1], c[2] + d[2])
            if nb in reach or nb in blocked or not grid.in_bounds(nb):
                continue
            reach.add(nb)
            dq.append(nb)
    return reach


def flood_path(grid, blocked, axis, start_layer, goal_layer):
    """6-连通 BFS，返回 (path 或 None, 起点侧可达集)。"""
    dq = deque()
    parent = {}
    for c in _layer_cells(grid, axis, start_layer):
        if c not in blocked:
            dq.append(c)
            parent[c] = None
    goal = None
    while dq:
        c = dq.popleft()
        if c[axis] == goal_layer:
            goal = c
            break
        for d in _NEIGHBOR_DELTAS:
            nb = (c[0] + d[0], c[1] + d[1], c[2] + d[2])
            if nb in parent or nb in blocked or not grid.in_bounds(nb):
                continue
            parent[nb] = c
            dq.append(nb)
    path = None
    if goal is not None:
        path = []
        c = goal
        while c is not None:
            path.append(c)
            c = parent[c]
        path.reverse()
    return path, set(parent)


def _frontier(grid, table, axis, start_layer, goal_layer):
    """决定通断的候选格：may 中同时与两侧（非 may）可达区相邻的体素。"""
    reach_s = flood_reach(grid, table.may, axis, start_layer)
    reach_g = flood_reach(grid, table.may, axis, goal_layer)
    out = []
    for c in table.may:
        touch_s = touch_g = False
        for d in _NEIGHBOR_DELTAS:
            nb = (c[0] + d[0], c[1] + d[1], c[2] + d[2])
            if nb in reach_s:
                touch_s = True
            if nb in reach_g:
                touch_g = True
        if touch_s and touch_g:
            out.append(c)
    return sorted(out)


def measure_connectivity(triangles, grid, budget, axis=2,
                         start_layer=0, goal_layer=None):
    """连通测量：逐层细分直到可判定或预算耗尽。"""
    if goal_layer is None:
        goal_layer = grid.axis_n(axis) - 1
    g = grid
    level = 0
    while True:
        scale = 1 << level
        s_l = start_layer * scale
        g_l = (goal_layer + 1) * scale - 1
        table = Voxelizer(g).voxelize(triangles)

        path, _ = flood_path(g, table.may, axis, s_l, g_l)
        if path is not None:
            return ConnectivityResult(
                "connected", level, budget, g, path=path,
                message=f"细分 {level} 层：找到完全由确定自由体素组成的通路")

        frontier = _frontier(g, table, axis, s_l, g_l)
        if level >= budget:
            path2, _ = flood_path(g, table.must, axis, s_l, g_l)
            if path2 is None and table.may == table.must and level > 0:
                return ConnectivityResult(
                    "blocked", level, budget, g, frontier=frontier,
                    message=f"细分 {level} 层：精确占用仍隔断，"
                            f"全部候选格均经解析确认")
            return ConnectivityResult(
                "undecided", level, budget, g, frontier=frontier,
                undecided_cells=frontier,
                message="细分预算耗尽：决定通断的格子未全部判定，返回未决")

        g = g.refined()
        level += 1


def fine_verdict(triangles, grid, axis=2, start_layer=0, goal_layer=None,
                 levels=2):
    """细网格复验：细分 levels 层后用精确占用（must）求通路。"""
    if goal_layer is None:
        goal_layer = grid.axis_n(axis) - 1
    g = grid
    for _ in range(levels):
        g = g.refined()
    scale = 1 << levels
    table = Voxelizer(g).voxelize(triangles)
    path, _ = flood_path(g, table.must, axis,
                         start_layer * scale, (goal_layer + 1) * scale - 1)
    return "connected" if path is not None else "blocked"
