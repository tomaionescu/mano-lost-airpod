"""Geometry builder for the campus: everything is authored in GAME space (metres, Y up, X east, Z south,
same as the old three.js level) and converted with P(x, y, z) -> Blender (x, -z, y) when committed, so the
+Y-up glTF export lands exactly on game coordinates.

Parts are Blender mesh objects with several material slots. Faces get world-ish box-mapped UVs (in the
current frame, scaled by the material's tile size) and a vertex colour (macro variation, grime near the
ground) that Godot multiplies into the albedo (see assets/levels/campus_import.gd).
"""
import bpy, bmesh, math, random
from contextlib import contextmanager
from mathutils import Vector, Matrix
import mathutils.geometry as mgeo
import campus_mat as CM


def P(x, y, z):
    return (x, -z, y)


# ------------------------------------------------------------------ transforms (game space)
class Xf:
    __slots__ = ("m",)

    def __init__(self, m=None):
        self.m = m if m is not None else Matrix.Identity(4)

    @staticmethod
    def at(x=0.0, y=0.0, z=0.0, yaw=0.0, pitch=0.0, roll=0.0, s=1.0):
        """translate, then yaw about +Y (local +Z -> (sin yaw, 0, cos yaw)), pitch about local X, roll about local Z"""
        m = Matrix.Translation((x, y, z)) @ Matrix.Rotation(yaw, 4, "Y") @ Matrix.Rotation(pitch, 4, "X") @ Matrix.Rotation(roll, 4, "Z")
        if s != 1.0:
            m = m @ (Matrix.Scale(s, 4) if not isinstance(s, (tuple, list)) else Matrix.Diagonal((s[0], s[1], s[2], 1.0)))
        return Xf(m)

    def __matmul__(self, o):
        return Xf(self.m @ o.m)

    def pt(self, p):
        return self.m @ Vector(p)

    def dir(self, d):
        return (self.m.to_3x3() @ Vector(d))


def yaw_to(dx, dz):
    return math.atan2(dx, dz)


# ------------------------------------------------------------------ deterministic noise
def _h(ix, iy, iz):
    n = (ix * 374761393 + iy * 668265263 + iz * 2147483647) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFF) / 65535.0


def vnoise(x, y, z):
    ix, iy, iz = math.floor(x), math.floor(y), math.floor(z)
    fx, fy, fz = x - ix, y - iy, z - iz
    ux, uy, uz = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy), fz * fz * (3 - 2 * fz)
    def L(a, b, t):
        return a + (b - a) * t
    c00 = L(_h(ix, iy, iz), _h(ix + 1, iy, iz), ux)
    c10 = L(_h(ix, iy + 1, iz), _h(ix + 1, iy + 1, iz), ux)
    c01 = L(_h(ix, iy, iz + 1), _h(ix + 1, iy, iz + 1), ux)
    c11 = L(_h(ix, iy + 1, iz + 1), _h(ix + 1, iy + 1, iz + 1), ux)
    return L(L(c00, c10, uy), L(c01, c11, uy), uz)


def fbm(x, y, z):
    return 0.6 * vnoise(x * 0.11, y * 0.11, z * 0.11) + 0.3 * vnoise(x * 0.43, y * 0.43, z * 0.43) + 0.1 * vnoise(x * 1.7, y * 1.7, z * 1.7)


# ------------------------------------------------------------------ parts
class Part:
    def __init__(self, name, cast=True):
        self.name = name
        self.cast = cast
        self.V = []
        self.F = []
        self.FM = []
        self.FS = []
        self.UV = []
        self.C = []
        self.CN = None
        self.mats = {}

    def mi(self, mat):
        i = self.mats.get(mat)
        if i is None:
            i = self.mats[mat] = len(self.mats)
        return i

    def tri_count(self):
        return sum(len(f) - 2 for f in self.F)


class Collider:
    def __init__(self, name):
        self.name = name
        self.V = []
        self.F = []


class Builder:
    def __init__(self):
        self.parts = {}
        self.part = None
        self.xf = Xf()
        self.ground = 0.0
        self.tint = (1.0, 1.0, 1.0)
        self.cols = {}
        self.col = None
        self.markers = []
        self.uv_off = (0.0, 0.0)
        self.auto_sub = True
        self.rng = random.Random(1234)

    # -------------------------------------------------------------- state
    def use(self, name, cast=True):
        if name not in self.parts:
            self.parts[name] = Part(name, cast)
        self.part = self.parts[name]
        return self.part

    def use_col(self, name):
        if name not in self.cols:
            self.cols[name] = Collider(name)
        self.col = self.cols[name]
        return self.col

    @contextmanager
    def frame(self, xf):
        prev = self.xf
        self.xf = prev @ xf
        try:
            yield self.xf
        finally:
            self.xf = prev

    @contextmanager
    def at(self, x=0.0, y=0.0, z=0.0, yaw=0.0, pitch=0.0, roll=0.0, s=1.0):
        with self.frame(Xf.at(x, y, z, yaw, pitch, roll, s)) as f:
            yield f

    @contextmanager
    def ground_at(self, y):
        prev = self.ground
        self.ground = y
        try:
            yield
        finally:
            self.ground = prev

    @contextmanager
    def tinted(self, rgb):
        prev = self.tint
        self.tint = (prev[0] * rgb[0], prev[1] * rgb[1], prev[2] * rgb[2])
        try:
            yield
        finally:
            self.tint = prev

    @contextmanager
    def in_part(self, name, cast=True):
        prev = self.part
        self.use(name, cast)
        try:
            yield self.part
        finally:
            self.part = prev

    # -------------------------------------------------------------- vertex colour
    def shade(self, pw, nw, spec, ground):
        v = 1.0
        mac = spec["macro"]
        if mac:
            n = fbm(pw.x, pw.y, pw.z)
            v *= 1.0 - mac * (1.0 - n) * 1.6
        g = spec["grime"]
        if g == "ext":
            if abs(nw.y) < 0.7 and ground is not None:
                h = max(0.0, pw.y - ground)
                v *= 1.0 - 0.30 * math.exp(-h / 0.5) * (0.7 + 0.3 * vnoise(pw.x * 0.9, 0.0, pw.z * 0.9))
            elif nw.y > 0.7:
                v *= 1.0 - 0.18 * vnoise(pw.x * 0.5, pw.y, pw.z * 0.5)
        elif g == "int":
            if abs(nw.y) < 0.7 and ground is not None:
                h = max(0.0, pw.y - ground)
                v *= 1.0 - 0.10 * math.exp(-h / 0.3)
        elif g == "floor":
            d = vnoise(pw.x * 0.35 + 7.0, 0.0, pw.z * 0.35 - 3.0)
            v *= 1.0 - 0.16 * max(0.0, d - 0.35) / 0.65
        t = self.tint
        return (min(1.0, v * t[0]), min(1.0, v * t[1]), min(1.0, v * t[2]), 1.0)

    # -------------------------------------------------------------- primitives (local coords of the current frame)
    def face(self, pts, mat, uvs=None, cols=None, smooth=False, normals=None, ground=None, flip=False):
        """add one planar polygon (local points, CCW seen from the front). UVs: box-mapped by default."""
        if flip:
            pts = list(reversed(pts))
            if uvs:
                uvs = list(reversed(uvs))
            if normals:
                normals = list(reversed(normals))
        part = self.part
        xf = self.xf
        lp = [Vector(p) for p in pts]
        ln = mgeo.normal(lp) if len(lp) >= 3 else Vector((0, 1, 0))
        if ln.length < 1e-9:
            return
        wp = [xf.pt(p) for p in lp]
        wn = xf.dir(ln).normalized()
        spec = CM.M[mat]
        if uvs is None:
            uvs = self.boxuv(lp, ln, spec["tile"])
        if cols is None:
            g = self.ground if ground is None else ground
            cols = [self.shade(w, wn, spec, g) for w in wp]
        base = len(part.V)
        part.V.extend(wp)
        part.F.append(tuple(range(base, base + len(wp))))
        part.FM.append(part.mi(mat))
        part.FS.append(smooth)
        part.UV.extend(uvs)
        part.C.extend(cols)
        if normals is not None:
            if part.CN is None:
                part.CN = [None] * (len(part.UV) - len(uvs))
            part.CN.extend(xf.dir(n).normalized() for n in normals)
        elif part.CN is not None:
            part.CN.extend([None] * len(uvs))

    def boxuv(self, lp, ln, tile):
        ax, ay, az = abs(ln.x), abs(ln.y), abs(ln.z)
        ou, ov = self.uv_off
        s = 1.0 / tile
        if ay >= ax and ay >= az:
            sg = 1.0 if ln.y >= 0 else -1.0
            return [(p.x * s + ou, -p.z * s * sg + ov) for p in lp]
        if ax >= az:
            sg = 1.0 if ln.x >= 0 else -1.0
            return [(-p.z * s * sg + ou, p.y * s + ov) for p in lp]
        sg = 1.0 if ln.z >= 0 else -1.0
        return [(p.x * s * sg + ou, p.y * s + ov) for p in lp]

    def quad(self, a, b, c, d, mat, **kw):
        self.face([a, b, c, d], mat, **kw)

    def grid(self, o, du, dv, us, vs, mat, ground=None, skip=None):
        """subdivided planar rectangle: o + u*du + v*dv for u in us, v in vs (sorted fractions 0..1)."""
        o, du, dv = Vector(o), Vector(du), Vector(dv)
        for i in range(len(us) - 1):
            for j in range(len(vs) - 1):
                if skip and skip(i, j):
                    continue
                u0, u1, v0, v1 = us[i], us[i + 1], vs[j], vs[j + 1]
                self.face([o + du * u0 + dv * v0, o + du * u1 + dv * v0, o + du * u1 + dv * v1, o + du * u0 + dv * v1], mat, ground=ground)

    def _splits(self, length, cell, extra=()):
        n = max(1, int(math.ceil(length / cell - 1e-6))) if cell else 1
        s = set(i / n for i in range(n + 1))
        for e in extra:
            if 0 < e < 1:
                s.add(e)
        return sorted(s)

    def rect(self, o, du, dv, mat, sub=None, ground=None):
        """rectangle with automatic subdivision (so vertex colours can vary over large faces)"""
        o, du, dv = Vector(o), Vector(du), Vector(dv)
        lu, lv = du.length, dv.length
        spec = CM.M[mat]
        cell = sub
        if cell is None and self.auto_sub and (spec["macro"] or spec["grime"] != "none"):
            cell = 2.5 if max(lu, lv) > 3.0 else None
        extra_v = ()
        n = du.cross(dv)
        g = self.ground if ground is None else ground
        if spec["grime"] in ("ext", "int") and n.length > 1e-9 and abs(n.normalized().y) < 0.3 and lv > 0.4:
            # rows near the ground give the grime gradient something to interpolate on
            wo = self.xf.pt(o)
            wt = self.xf.pt(o + dv)
            lo, hi = min(wo.y, wt.y), max(wo.y, wt.y)
            if lo < g + 1.5 and hi > g:
                extra_v = tuple(((g + h) - lo) / (hi - lo) for h in (0.12, 0.35, 0.7, 1.2))
                if wo.y > wt.y:
                    extra_v = tuple(1 - e for e in extra_v)
                if cell is None:
                    cell = 4.0
        us = self._splits(lu, cell)
        vs = self._splits(lv, cell, extra_v)
        self.grid(o, du, dv, us, vs, mat, ground=ground)

    def box(self, x0, y0, z0, x1, y1, z1, mat, skip="", sub=None, mats=None, ground=None):
        """axis-aligned box in the current frame. skip: letters of faces to omit (n s e w t b = -z +z +x -x +y -y).
        mats: optional per-face material override dict."""
        if x1 < x0:
            x0, x1 = x1, x0
        if y1 < y0:
            y0, y1 = y1, y0
        if z1 < z0:
            z0, z1 = z1, z0
        if x1 - x0 < 1e-6 or y1 - y0 < 1e-6 or z1 - z0 < 1e-6:
            return
        mm = lambda k: (mats or {}).get(k, mat)
        if "t" not in skip:
            self.rect((x0, y1, z1), (x1 - x0, 0, 0), (0, 0, z0 - z1), mm("t"), sub, ground)
        if "b" not in skip:
            self.rect((x0, y0, z0), (x1 - x0, 0, 0), (0, 0, z1 - z0), mm("b"), sub, ground)
        if "s" not in skip:
            self.rect((x0, y0, z1), (x1 - x0, 0, 0), (0, y1 - y0, 0), mm("s"), sub, ground)
        if "n" not in skip:
            self.rect((x1, y0, z0), (x0 - x1, 0, 0), (0, y1 - y0, 0), mm("n"), sub, ground)
        if "e" not in skip:
            self.rect((x1, y0, z1), (0, 0, z0 - z1), (0, y1 - y0, 0), mm("e"), sub, ground)
        if "w" not in skip:
            self.rect((x0, y0, z0), (0, 0, z1 - z0), (0, y1 - y0, 0), mm("w"), sub, ground)

    def boxc(self, cx, cy, cz, sx, sy, sz, mat, **kw):
        """box from centre (cy = bottom) and size"""
        self.box(cx - sx / 2, cy, cz - sz / 2, cx + sx / 2, cy + sy, cz + sz / 2, mat, **kw)

    def prism(self, pts, y0, y1, mat, top=True, bottom=False, sides=True, side_mat=None, top_mat=None, smooth=False):
        """vertical extrusion of a polygon given in the XZ plane [(x, z), ...] (any winding, may be concave)"""
        pts = [tuple(p) for p in pts]
        area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
        if area > 0:  # make it clockwise in (x, z) == CCW seen from +Y
            pts = pts[::-1]
        if top or bottom:
            tris = mgeo.tessellate_polygon([[Vector((x, z, 0)) for x, z in pts]])
            for t in tris:
                a, b, c = (pts[i] for i in t)
                if top:
                    tri = [(a[0], y1, a[1]), (b[0], y1, b[1]), (c[0], y1, c[1])]
                    if mgeo.normal([Vector(v) for v in tri]).y < 0:
                        tri.reverse()
                    self.face(tri, top_mat or mat)
                if bottom:
                    tri = [(a[0], y0, a[1]), (b[0], y0, b[1]), (c[0], y0, c[1])]
                    if mgeo.normal([Vector(v) for v in tri]).y > 0:
                        tri.reverse()
                    self.face(tri, mat)
        if sides:
            n = len(pts)
            for i in range(n):
                (ax, az), (bx, bz) = pts[i], pts[(i + 1) % n]
                self.rect((ax, y0, az), (bx - ax, 0, bz - az), (0, y1 - y0, 0), side_mat or mat)

    def slab(self, pts, y0, y1, mat, **kw):
        self.prism(pts, y0, y1, mat, top=True, bottom=True, **kw)

    def seg_box(self, ax, az, bx, bz, y0, y1, thick, mat, **kw):
        """box along the segment (ax,az)->(bx,bz), centred on it"""
        L = math.hypot(bx - ax, bz - az)
        yaw = math.atan2(bx - ax, bz - az) - math.pi / 2
        with self.at((ax + bx) / 2, 0, (az + bz) / 2, yaw):
            self.box(-L / 2, y0, -thick / 2, L / 2, y1, thick / 2, mat, **kw)

    def cyl(self, cx, y0, cz, r, h, mat, seg=16, caps=(True, True), r2=None, smooth=True, a0=0.0, a1=None, uv_scale=None):
        """vertical cylinder / cone frustum. r2 = top radius"""
        r2 = r if r2 is None else r2
        full = a1 is None
        a1 = (a0 + 2 * math.pi) if full else a1
        spec = CM.M[mat]
        tile = spec["tile"] if uv_scale is None else uv_scale
        ring0, ring1 = [], []
        n = seg
        for i in range(n + 1):
            a = a0 + (a1 - a0) * i / n
            ca, sa = math.cos(a), math.sin(a)
            ring0.append((cx + ca * r, y0, cz + sa * r, ca, sa, a))
            ring1.append((cx + ca * r2, y0 + h, cz + sa * r2, ca, sa, a))
        slope = (r - r2) / h if h else 0
        circ = 2 * math.pi * max(r, r2)
        for i in range(n):
            p = ring0[i], ring0[i + 1], ring1[i + 1], ring1[i]
            pts = [(q[0], q[1], q[2]) for q in p]
            uvs = [((q[5] - a0) / (2 * math.pi) * circ / tile, (q[1] - y0) / tile) for q in p]
            nr = [Vector((q[3], slope, q[4])).normalized() for q in p]
            # winding: outward normal
            self.face(pts[::-1], mat, uvs=uvs[::-1], smooth=smooth, normals=nr[::-1] if smooth else None)
        if full:
            if caps[0] and r > 0:
                self.face([(q[0], q[1], q[2]) for q in ring0[:-1]], mat)
            if caps[1] and r2 > 0:
                self.face([(q[0], q[1], q[2]) for q in ring1[:-1]][::-1], mat)

    def cyl_axis(self, a, b, r, mat, seg=12, caps=True, smooth=True, r2=None):
        """cylinder between two local points a, b (any direction)"""
        a, b = Vector(a), Vector(b)
        d = b - a
        L = d.length
        if L < 1e-6:
            return
        q = Vector((0, 1, 0)).rotation_difference(d.normalized())
        m = Matrix.Translation(a) @ q.to_matrix().to_4x4()
        with self.frame(Xf(m)):
            self.cyl(0, 0, 0, r, L, mat, seg=seg, caps=(caps, caps), r2=r2, smooth=smooth)

    def tube(self, path, r, mat, seg=8, closed=False, caps=True):
        """smooth tube along a polyline of local points"""
        path = [Vector(p) for p in path]
        if len(path) < 2:
            return
        rings = []
        for i, p in enumerate(path):
            if i == 0:
                t = (path[1] - path[0]).normalized()
            elif i == len(path) - 1:
                t = (path[-1] - path[-2]).normalized()
            else:
                t = ((path[i] - path[i - 1]).normalized() + (path[i + 1] - path[i]).normalized()).normalized()
            up = Vector((0, 1, 0)) if abs(t.y) < 0.95 else Vector((1, 0, 0))
            u = t.cross(up).normalized()
            v = u.cross(t).normalized()
            rings.append([(p + (u * math.cos(2 * math.pi * k / seg) + v * math.sin(2 * math.pi * k / seg)) * r,
                           (u * math.cos(2 * math.pi * k / seg) + v * math.sin(2 * math.pi * k / seg))) for k in range(seg)])
        dist = 0.0
        tile = CM.M[mat]["tile"]
        for i in range(len(rings) - 1):
            d = (path[i + 1] - path[i]).length
            for k in range(seg):
                k2 = (k + 1) % seg
                a0, a1, b1, b0 = rings[i][k], rings[i][k2], rings[i + 1][k2], rings[i + 1][k]
                uv = [(k / seg, dist / tile), ((k + 1) / seg, dist / tile), ((k + 1) / seg, (dist + d) / tile), (k / seg, (dist + d) / tile)]
                self.face([a0[0], a1[0], b1[0], b0[0]], mat, uvs=uv, smooth=True, normals=[a0[1], a1[1], b1[1], b0[1]])
            dist += d
        if caps:
            self.face([q[0] for q in rings[0]][::-1], mat)
            self.face([q[0] for q in rings[-1]], mat)

    def sphere(self, cx, cy, cz, r, mat, seg=12, rings=8, sy=1.0, hemi=False):
        top = []
        for j in range(rings + 1):
            th = math.pi * j / rings
            if hemi and th > math.pi / 2 + 1e-6:
                break
            row = []
            for i in range(seg + 1):
                ph = 2 * math.pi * i / seg
                n = Vector((math.sin(th) * math.cos(ph), math.cos(th), math.sin(th) * math.sin(ph)))
                row.append((Vector((cx + n.x * r, cy + n.y * r * sy, cz + n.z * r)), n, (i / seg, 1 - j / rings)))
            top.append(row)
        for j in range(len(top) - 1):
            for i in range(seg):
                a, b, c, d = top[j][i], top[j][i + 1], top[j + 1][i + 1], top[j + 1][i]
                pts = [a, b, c, d]
                if (a[0] - d[0]).length < 1e-9 or j == 0:
                    pts = [a, c, d]
                elif (b[0] - c[0]).length < 1e-9:
                    pts = [a, b, d]
                self.face([q[0] for q in pts], mat, uvs=[q[2] for q in pts], smooth=True, normals=[q[1] for q in pts])

    def card(self, c, right, up, mat, uv=(0, 0, 1, 1), normal=None, double=False):
        """textured quad centred at c spanning +-right, +-up (local vectors). uv=(u0,v0,u1,v1) atlas rect."""
        c, r, u = Vector(c), Vector(right), Vector(up)
        pts = [c - r - u, c + r - u, c + r + u, c - r + u]
        u0, v0, u1, v1 = uv
        uvs = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
        nrm = [normal] * 4 if normal is not None else None
        self.face(pts, mat, uvs=uvs, normals=nrm, smooth=normal is not None)
        if double:
            self.face(pts[::-1], mat, uvs=uvs[::-1], normals=[-Vector(normal)] * 4 if normal is not None else None, smooth=normal is not None)

    # -------------------------------------------------------------- collision (local coords -> world)
    def cbox(self, x0, y0, z0, x1, y1, z1, group=None):
        col = self.cols.setdefault(group, Collider(group)) if group else self.col
        xf = self.xf
        x0, x1 = min(x0, x1), max(x0, x1)
        y0, y1 = min(y0, y1), max(y0, y1)
        z0, z1 = min(z0, z1), max(z0, z1)
        c = [xf.pt(p) for p in ((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1),
                                 (x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1))]
        b = len(col.V)
        col.V.extend(c)
        for f in ((0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)):
            col.F.append(tuple(b + i for i in f))

    def cboxc(self, cx, cy, cz, sx, sy, sz, group=None):
        self.cbox(cx - sx / 2, cy, cz - sz / 2, cx + sx / 2, cy + sy, cz + sz / 2, group)

    def cprism(self, pts, y0, y1, group=None):
        """vertical prism collider from an XZ polygon (outward-facing triangles)"""
        col = self.cols.setdefault(group, Collider(group)) if group else self.col
        xf = self.xf
        pts = [tuple(p) for p in pts]
        area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
        if area > 0:
            pts = pts[::-1]
        n = len(pts)
        b = len(col.V)
        lo = [Vector((x, y0, z)) for x, z in pts]
        hi = [Vector((x, y1, z)) for x, z in pts]
        col.V.extend(xf.pt(p) for p in lo)
        col.V.extend(xf.pt(p) for p in hi)
        tris = mgeo.tessellate_polygon([[Vector((x, z, 0)) for x, z in pts]])
        for t in tris:
            t = list(t)
            if mgeo.normal([hi[i] for i in t]).y < 0:
                t.reverse()
            col.F.append(tuple(b + n + i for i in t))
            col.F.append(tuple(b + i for i in reversed(t)))
        for i in range(n):
            j = (i + 1) % n
            col.F.append((b + i, b + j, b + n + j, b + n + i))

    def cramp(self, x0, y0, z0, x1, y1, z1, width, thick=0.25, group=None):
        """sloped walkway collider whose TOP passes through both end points (like the old physics.ramp)"""
        a, b = Vector((x0, y0, z0)), Vector((x1, y1, z1))
        d = b - a
        L = d.length
        zax = d.normalized()
        xax = Vector((0, 1, 0)).cross(zax).normalized()
        yax = zax.cross(xax).normalized()
        m = Matrix.Identity(4)
        for r in range(3):
            m[r][0], m[r][1], m[r][2], m[r][3] = xax[r], yax[r], zax[r], a[r]
        with self.frame(Xf(m)):
            self.cbox(-width / 2, -thick, 0, width / 2, 0, L, group)

    # -------------------------------------------------------------- markers
    def marker(self, name, pos, yaw=0.0, extras=None, display="PLAIN_AXES", half=None, size=0.3, look=None, rot=None):
        self.markers.append(dict(name=name, pos=tuple(pos), yaw=yaw, extras=extras or {}, display=display,
                                 half=half, size=size, look=look, rot=rot))

    # -------------------------------------------------------------- text
    def text(self, s, font, size, mat, align="CENTER", valign="CENTER", depth=0.0, spacing=1.0, bevel=0.0, maxw=None):
        """3D text in the local XY plane (front faces +Z). Returns the (width, height) actually used."""
        cu = bpy.data.curves.new("txt", "FONT")
        cu.body = s
        cu.font = font
        cu.size = 1.0
        cu.align_x = {"CENTER": "CENTER", "LEFT": "LEFT", "RIGHT": "RIGHT"}[align]
        cu.align_y = {"CENTER": "CENTER", "TOP": "TOP", "BOTTOM": "BOTTOM", "BASE": "TOP_BASELINE"}.get(valign, "CENTER")
        cu.space_character = spacing
        cu.extrude = depth / 2 / size if depth else 0.0
        cu.bevel_depth = bevel / size if bevel else 0.0
        cu.resolution_u = 3
        ob = bpy.data.objects.new("txt", cu)
        bpy.context.scene.collection.objects.link(ob)
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
        xs = [v.co.x for v in bm.verts] or [0]
        ys = [v.co.y for v in bm.verts] or [0]
        w, h = (max(xs) - min(xs)) * size, (max(ys) - min(ys)) * size
        k = size
        if maxw and w > maxw:
            f = maxw / w
            k, w, h = k * f, w * f, h * f
        for f in bm.faces:
            pts = [(v.co.x * k, v.co.y * k, v.co.z * k + (depth / 2 if depth else 0.0)) for v in f.verts]
            self.face(pts, mat)
        bm.free()
        bpy.data.objects.remove(ob)
        bpy.data.curves.remove(cu)
        bpy.data.meshes.remove(me)
        return w, h


# ------------------------------------------------------------------ commit to Blender
def link(ob, coll):
    coll.objects.link(ob)
    return ob


def make_mesh(part, name=None):
    me = bpy.data.meshes.new(name or part.name)
    verts = [P(v.x, v.y, v.z) for v in part.V]
    me.from_pydata(verts, [], part.F)
    me.update(calc_edges=True)
    nloops = len(me.loops)
    mats = sorted(part.mats.items(), key=lambda kv: kv[1])
    for mname, _ in mats:
        me.materials.append(CM.material(mname))
    if part.FM:
        me.polygons.foreach_set("material_index", part.FM)
        me.polygons.foreach_set("use_smooth", [bool(s) for s in part.FS])
    uvl = me.uv_layers.new(name="UVMap")
    flat = [c for uv in part.UV for c in uv]
    uvl.data.foreach_set("uv", flat)
    ca = me.color_attributes.new("Col", "BYTE_COLOR", "CORNER")
    ca.data.foreach_set("color", [c for col in part.C for c in col])
    me.color_attributes.active_color = ca
    if part.CN is not None:
        # custom normals where given, face normal elsewhere
        cn = []
        li = 0
        for pi, poly in enumerate(me.polygons):
            fn = poly.normal
            for _ in range(poly.loop_total):
                n = part.CN[li] if li < len(part.CN) else None
                cn.append(P(n.x, n.y, n.z) if n is not None else tuple(fn))
                li += 1
        try:
            me.normals_split_custom_set(cn)
        except Exception as e:
            print("custom normals failed", part.name, e)
    me.validate(clean_customdata=False)
    return me


def commit_parts(B, coll):
    obs = []
    for name, part in B.parts.items():
        if not part.F:
            continue
        me = make_mesh(part)
        ob = bpy.data.objects.new(name, me)
        link(ob, coll)
        obs.append(ob)
    return obs


def commit_colliders(B, coll):
    obs = []
    for name, c in B.cols.items():
        if not c.F:
            continue
        me = bpy.data.meshes.new(name + "_col")
        me.from_pydata([P(v.x, v.y, v.z) for v in c.V], [], c.F)
        me.update(calc_edges=True)
        ob = bpy.data.objects.new(name + "-colonly", me)
        ob.display_type = "WIRE"
        ob.hide_render = True
        link(ob, coll)
        obs.append(ob)
    return obs


def commit_markers(B, coll):
    obs = []
    for m in B.markers:
        ob = bpy.data.objects.new(m["name"], None)
        ob.empty_display_type = m["display"]
        ob.empty_display_size = m["size"]
        x, y, z = m["pos"]
        ob.location = P(x, y, z)
        if m["look"] is not None:
            d = Vector(P(*m["look"]))
            if d.length > 1e-9:
                # glTF/Godot local -Z == Blender local +Y: aim +Y along d
                up = "Z" if abs(d.normalized().z) < 0.99 else "X"
                ob.rotation_euler = d.to_track_quat("Y", up).to_euler()
        elif m["rot"] is not None:
            ob.rotation_euler = m["rot"]
        else:
            ob.rotation_euler = (0.0, 0.0, m["yaw"])
        if m["half"] is not None:
            hx, hy, hz = m["half"]
            ob.scale = (hx, hz, hy)
        for k, v in m["extras"].items():
            ob[k] = v
        link(ob, coll)
        obs.append(ob)
    return obs
