"""Footprint polygons in the XZ plane (game metres, [(x, z), ...]): orientation, clipping, triangulation,
grid pieces and points along edges. Pure Python (no bpy) so the footprint checks can import it too.

Facades follow campus_arch.wall_frame: walking a->b the outside is on the right, so a footprint walked in
its clockwise (x, z) order (negative shoelace area) puts every wall face outwards."""
import math

EPS = 1e-6


def area(poly):
    """signed shoelace area in (x, z); negative = clockwise = outward-right walls"""
    n = len(poly)
    return 0.5 * sum(poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1] for i in range(n))


def cw(poly):
    poly = [tuple(map(float, p)) for p in poly]
    return poly if area(poly) < 0 else poly[::-1]


def edges(poly):
    n = len(poly)
    return [(poly[i], poly[(i + 1) % n]) for i in range(n)]


def length(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def outward(a, b):
    """unit outward normal of edge a->b of a clockwise footprint (same as wall_frame's local +Z)"""
    L = length(a, b)
    return (-(b[1] - a[1]) / L, (b[0] - a[0]) / L)


def along(a, b, t, off=0.0):
    """point at fraction t of a->b, pushed `off` metres outwards"""
    n = outward(a, b)
    return (a[0] + (b[0] - a[0]) * t + n[0] * off, a[1] + (b[1] - a[1]) * t + n[1] * off)


def yaw_out(a, b):
    """yaw of something facing out of edge a->b (yaw 0 faces +Z)"""
    n = outward(a, b)
    return math.atan2(n[0], n[1])


def _clean(poly):
    out = []
    for p in poly:
        if not out or abs(p[0] - out[-1][0]) > EPS or abs(p[1] - out[-1][1]) > EPS:
            out.append(p)
    while len(out) > 1 and abs(out[0][0] - out[-1][0]) <= EPS and abs(out[0][1] - out[-1][1]) <= EPS:
        out.pop()
    return out


def clip_half(poly, p0, n):
    """part of poly where (p - p0) . n <= 0 (Sutherland-Hodgman against one half-plane, keeps the winding)"""
    out = []
    m = len(poly)
    for i in range(m):
        a, b = poly[i], poly[(i + 1) % m]
        da = (a[0] - p0[0]) * n[0] + (a[1] - p0[1]) * n[1]
        db = (b[0] - p0[0]) * n[0] + (b[1] - p0[1]) * n[1]
        if da <= EPS:
            out.append(a)
        if (da < -EPS and db > EPS) or (da > EPS and db < -EPS):
            t = da / (da - db)
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return _clean(out)


def clip_box(poly, x0, z0, x1, z1):
    for p0, n in (((x0, 0.0), (-1.0, 0.0)), ((x1, 0.0), (1.0, 0.0)), ((0.0, z0), (0.0, -1.0)), ((0.0, z1), (0.0, 1.0))):
        poly = clip_half(poly, p0, n)
        if len(poly) < 3:
            return []
    return poly


def on_line(p, p0, n, tol=1e-4):
    return abs((p[0] - p0[0]) * n[0] + (p[1] - p0[1]) * n[1]) < tol


def triangulate(poly):
    """ear clipping of a simple polygon; triangles keep the polygon's winding"""
    pts = cw(poly)
    idx = list(range(len(pts)))
    tris = []

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def inside(p, a, b, c):
        return cross(a, b, p) <= EPS and cross(b, c, p) <= EPS and cross(c, a, p) <= EPS

    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            a, b, c = pts[i0], pts[i1], pts[i2]
            if cross(a, b, c) >= -EPS:      # reflex or flat for a clockwise polygon
                continue
            if any(inside(pts[j], a, b, c) for j in idx if j not in (i0, i1, i2)):
                continue
            tris.append((a, b, c))
            idx.pop(k)
            break
        else:
            break
    if len(idx) == 3:
        tris.append(tuple(pts[i] for i in idx))
    return tris


def grid_pieces(poly, cell=4.0):
    """convex pieces covering poly, cut on a `cell` metre grid (clockwise like cw(poly)): large floors get
    enough vertices for the builder's vertex-colour grime and macro variation"""
    out = []
    for tri in triangulate(poly):
        xs, zs = [p[0] for p in tri], [p[1] for p in tri]
        i0, i1 = math.floor(min(xs) / cell), math.floor(max(xs) / cell)
        j0, j1 = math.floor(min(zs) / cell), math.floor(max(zs) / cell)
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                pc = clip_box(list(tri), i * cell, j * cell, (i + 1) * cell, (j + 1) * cell)
                if len(pc) >= 3 and abs(area(pc)) > 1e-4:
                    out.append(pc)
    return out


def inside_poly(p, poly):
    x, z = p
    c = False
    n = len(poly)
    for i in range(n):
        (ax, az), (bx, bz) = poly[i], poly[(i + 1) % n]
        if (az > z) != (bz > z) and x < ax + (z - az) * (bx - ax) / (bz - az):
            c = not c
    return c


def seg_dist(p, a, b):
    dx, dz = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dz * dz
    t = 0.0 if L2 < EPS else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dz) / L2))
    return math.hypot(p[0] - a[0] - dx * t, p[1] - a[1] - dz * t)


def poly_dist(p, poly):
    return min(seg_dist(p, a, b) for a, b in edges(poly))
