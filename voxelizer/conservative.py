"""保守光栅化：三角形投影到主轴平面，保守计算被覆盖像素及深度区间。

与"像素中心命中"不同：只要三角形与像素方块（闭集）相交即覆盖，
因此不含任何中心点的细小三角形也不会遗漏；同时候选像素严格限制在
三角形投影包围盒内，额外覆盖有界，不会把整个包围盒标成实体。
"""
from dataclasses import dataclass

from .geometry import tri_normal


@dataclass
class PixelCoverage:
    i: int          # 像素在 u 轴的层号
    j: int          # 像素在 v 轴的层号
    dmin: float     # 三角形在 三角形∩像素 区域内的最小深度（沿投影轴）
    dmax: float     # 最大深度
    center_hit: bool  # 像素中心是否落在三角形内（调试用，保守覆盖不依赖它）


def dominant_axis(normal):
    """投影轴：法向量绝对值最大的分量，使投影面积最大化。"""
    a = (abs(normal[0]), abs(normal[1]), abs(normal[2]))
    return a.index(max(a))


def tri_square_overlap_2d(tri2d, sq_min, size, eps):
    """三角形与像素方块（均为闭集）的 SAT 相交。间隙 <= eps 视为相交。"""
    sx, sy = sq_min
    sq = ((sx, sy), (sx + size, sy), (sx + size, sy + size), (sx, sy + size))
    axes = [(1.0, 0.0), (0.0, 1.0)]
    for k in range(3):
        p = tri2d[k]
        q = tri2d[(k + 1) % 3]
        nx = -(q[1] - p[1])
        ny = q[0] - p[0]
        if nx != 0.0 or ny != 0.0:
            axes.append((nx, ny))
    for ax, ay in axes:
        tmin = min(ax * p[0] + ay * p[1] for p in tri2d)
        tmax = max(ax * p[0] + ay * p[1] for p in tri2d)
        smin = min(ax * p[0] + ay * p[1] for p in sq)
        smax = max(ax * p[0] + ay * p[1] for p in sq)
        if tmin > smax + eps or smin > tmax + eps:
            return False
    return True


def _clip_axis(poly, axis, bound, keep_ge):
    """用半平面（axis 坐标 >=/<= bound）裁剪凸多边形。"""
    if not poly:
        return []
    out = []
    other = 1 - axis
    n = len(poly)
    for i in range(n):
        cur = poly[i]
        prv = poly[(i - 1) % n]
        vc = cur[axis]
        vp = prv[axis]
        cin = vc >= bound if keep_ge else vc <= bound
        pin = vp >= bound if keep_ge else vp <= bound
        if cin != pin:
            t = (bound - vp) / (vc - vp)
            q = [0.0, 0.0]
            q[axis] = bound
            q[other] = prv[other] + t * (cur[other] - prv[other])
            out.append((q[0], q[1]))
        if cin:
            out.append(cur)
    return out


def clip_triangle_to_square(tri2d, sq_min, size):
    """Sutherland–Hodgman：返回 三角形∩像素 的凸多边形顶点（闭集，可为点/边）。"""
    x0, y0 = sq_min
    x1 = x0 + size
    y1 = y0 + size
    poly = list(tri2d)
    poly = _clip_axis(poly, 0, x0, True)
    poly = _clip_axis(poly, 0, x1, False)
    poly = _clip_axis(poly, 1, y0, True)
    poly = _clip_axis(poly, 1, y1, False)
    return poly


def point_in_tri_2d(p, tri2d, eps=1e-12):
    """点是否在三角形内（闭集）。仅用于 center_hit 调试标记。"""
    signs = []
    for k in range(3):
        a = tri2d[k]
        b = tri2d[(k + 1) % 3]
        signs.append((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]))
    return all(s >= -eps for s in signs) or all(s <= eps for s in signs)


def project_triangle_coverage(grid, tri, axis):
    """把三角形投影到垂直于 axis 的平面，返回 (coverages, tri2d, (u, v))。

    候选像素取自投影包围盒（有界）；每个被覆盖像素用 三角形∩像素
    的凸多边形顶点求深度区间（深度在三角形上是线性的，顶点处取极值）。
    """
    n = tri_normal(tri)
    u = (axis + 1) % 3
    v = (axis + 2) % 3
    tri2d = [(p[u], p[v]) for p in tri]
    us = [p[0] for p in tri2d]
    vs = [p[1] for p in tri2d]
    i0, i1 = grid.cell_range_closed(min(us), max(us), u)
    j0, j1 = grid.cell_range_closed(min(vs), max(vs), v)
    i0, i1 = grid.clamp(u, i0, i1)
    j0, j1 = grid.clamp(v, j0, j1)
    nw = n[axis]
    p0 = tri[0]

    def depth(uu, vv):
        return p0[axis] - (n[u] * (uu - p0[u]) + n[v] * (vv - p0[v])) / nw

    h = grid.cell
    out = []
    for i in range(i0, i1 + 1):
        for j in range(j0, j1 + 1):
            sq_min = (grid.axis_lo(u, i), grid.axis_lo(v, j))
            if not tri_square_overlap_2d(tri2d, sq_min, h, grid.eps):
                continue
            poly = clip_triangle_to_square(tri2d, sq_min, h)
            if not poly:
                continue
            ds = [depth(p[0], p[1]) for p in poly]
            c = (sq_min[0] + 0.5 * h, sq_min[1] + 0.5 * h)
            out.append(PixelCoverage(i, j, min(ds), max(ds),
                                     point_in_tri_2d(c, tri2d)))
    return out, tri2d, (u, v)
