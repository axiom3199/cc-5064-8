"""几何基础：向量运算与三角形-盒相交（Akenine-Möller SAT，闭集语义）。

闭集语义：三角形与盒仅共享边/顶点/面也算相交。体素化器、参考校验、
连通测量共用这一套判定，保证边界归属规则统一。
"""
import math


def vsub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vadd(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vdot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vcross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def vlen(a):
    return math.sqrt(vdot(a, a))


def tri_normal(tri):
    """未归一化法向量，模长 = 2 倍三角形面积。退化三角形返回零向量。"""
    e0 = vsub(tri[1], tri[0])
    e1 = vsub(tri[2], tri[1])
    return vcross(e0, e1)


def tri_box_overlap(center, half, tri, eps=1e-12):
    """三角形与轴对齐盒（闭集）是否相交。center/half 为盒中心与半长。

    SAT 13 轴：3 个盒轴、1 个三角形法向、9 个边叉积轴。
    接触（共享面/边/点）返回 True。退化三角形（共线/重合点）同样适用。
    eps 为相对容差，仅用于吸收浮点噪声，防止边界接触被误判为分离。
    """
    v0 = vsub(tri[0], center)
    v1 = vsub(tri[1], center)
    v2 = vsub(tri[2], center)
    e0 = vsub(v1, v0)
    e1 = vsub(v2, v1)
    e2 = vsub(v0, v2)
    hx, hy, hz = half

    for ex, ey, ez in (e0, e1, e2):
        for ax, ay, az in ((0.0, -ez, ey), (ez, 0.0, -ex), (-ey, ex, 0.0)):
            if ax == 0.0 and ay == 0.0 and az == 0.0:
                continue
            p0 = ax * v0[0] + ay * v0[1] + az * v0[2]
            p1 = ax * v1[0] + ay * v1[1] + az * v1[2]
            p2 = ax * v2[0] + ay * v2[1] + az * v2[2]
            r = hx * abs(ax) + hy * abs(ay) + hz * abs(az)
            tol = eps * max(1.0, r, abs(p0), abs(p1), abs(p2))
            if min(p0, p1, p2) > r + tol or max(p0, p1, p2) < -r - tol:
                return False

    for i in range(3):
        vals = (v0[i], v1[i], v2[i])
        h = half[i]
        tol = eps * max(1.0, h, abs(vals[0]), abs(vals[1]), abs(vals[2]))
        if min(vals) > h + tol or max(vals) < -h - tol:
            return False

    n = vcross(e0, e1)
    r = hx * abs(n[0]) + hy * abs(n[1]) + hz * abs(n[2])
    s = vdot(n, v0)
    tol = eps * max(1.0, r, abs(s))
    if s > r + tol or s < -r - tol:
        return False
    return True


def point_triangle_distance(p, tri):
    """点到三角形（闭集）的距离。用于核对保守多标体素与解析交集的偏差。"""
    # Real-Time Collision Detection, Christer Ericson, 5.1.5
    a, b, c = tri
    ab = vsub(b, a)
    ac = vsub(c, a)
    ap = vsub(p, a)
    d1 = vdot(ab, ap)
    d2 = vdot(ac, ap)
    if d1 <= 0.0 and d2 <= 0.0:
        return vlen(ap)
    bp = vsub(p, b)
    d3 = vdot(ab, bp)
    d4 = vdot(ac, bp)
    if d3 >= 0.0 and d4 <= d3:
        return vlen(bp)
    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        v = d1 / (d1 - d3)
        return vlen(vsub(p, vadd(a, tuple(v * x for x in ab))))
    cp = vsub(p, c)
    d5 = vdot(ab, cp)
    d6 = vdot(ac, cp)
    if d6 >= 0.0 and d5 <= d6:
        return vlen(cp)
    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        w = d2 / (d2 - d6)
        return vlen(vsub(p, vadd(a, tuple(w * x for x in ac))))
    va = d3 * d6 - d5 * d4
    if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return vlen(vsub(p, vadd(b, tuple(w * x for x in vsub(c, b)))))
    n = vcross(ab, ac)
    nl = vlen(n)
    if nl == 0.0:
        # 退化三角形：退化为点到三边的距离
        return min(_point_segment_distance(p, a, b),
                   _point_segment_distance(p, b, c),
                   _point_segment_distance(p, c, a))
    return abs(vdot(ap, n)) / nl


def _point_segment_distance(p, a, b):
    ab = vsub(b, a)
    denom = vdot(ab, ab)
    if denom == 0.0:
        return vlen(vsub(p, a))
    t = max(0.0, min(1.0, vdot(vsub(p, a), ab) / denom))
    return vlen(vsub(p, vadd(a, tuple(t * x for x in ab))))
