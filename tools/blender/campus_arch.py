"""Architectural generators: walls with openings, windows, doors, curtain walls, stairs, railings, parapets.

Walls are authored in a local frame: u along the wall (local +X), y up, and the wall body between local
z = -thick (inside face, normal -Z) and z = 0 (outside face, normal +Z). Use B.at(...) / wall_frame() to
place that frame in the world.
"""
import math
from mathutils import Vector
from campus_geo import Xf


def wall_frame(ax, az, bx, bz):
    """frame for a wall running from a to b whose OUTSIDE face is on the right-hand side when walking a->b
    seen from above with north up... concretely: local +X = a->b, local +Z = outward normal."""
    yaw = math.atan2(bx - ax, bz - az) - math.pi / 2
    return Xf.at(ax, 0, az, yaw), math.hypot(bx - ax, bz - az)


class Opening:
    __slots__ = ("u0", "u1", "y0", "y1", "kind", "opt")

    def __init__(self, u0, u1, y0, y1, kind="window", **opt):
        self.u0, self.u1, self.y0, self.y1, self.kind, self.opt = u0, u1, y0, y1, kind, opt


def wall(B, length, y0, y1, thick, mat_out, mat_in=None, openings=(), col=True, ends=True, top=True, bottom=False,
         ground_out=None, ground_in=None, col_group=None, mat_reveal=None, mat_top=None, u_start=0.0,
         base_in=None, base_out=None):
    """solid wall slab with rectangular openings. Openings are filled by fill_opening().
    base_in / base_out: (material, height) skirting board along the inner / outer face, interrupted at doors."""
    if mat_in is None:
        mat_in = mat_out
    mat_reveal = mat_reveal or mat_out
    ops = sorted(openings, key=lambda o: o.u0)
    us = {u_start, length}
    ys = {y0, y1}
    for o in ops:
        us.update((o.u0, o.u1))
        ys.update((o.y0, o.y1))
    us = sorted(u for u in us if u_start - 1e-6 <= u <= length + 1e-6)
    ys = sorted(y for y in ys if y0 - 1e-6 <= y <= y1 + 1e-6)

    def inside(u, y):
        for o in ops:
            if o.u0 - 1e-6 <= u <= o.u1 + 1e-6 and o.y0 - 1e-6 <= y <= o.y1 + 1e-6:
                return True
        return False
    t = thick
    for i in range(len(us) - 1):
        ua, ub = us[i], us[i + 1]
        for j in range(len(ys) - 1):
            ya, yb = ys[j], ys[j + 1]
            if inside((ua + ub) / 2, (ya + yb) / 2):
                continue
            if mat_out:
                B.rect((ua, ya, 0), (ub - ua, 0, 0), (0, yb - ya, 0), mat_out, ground=ground_out)
            if mat_in:
                B.rect((ub, ya, -t), (ua - ub, 0, 0), (0, yb - ya, 0), mat_in, ground=ground_in)
    for o in ops:
        if not mat_reveal:
            break
        # reveals (jambs, head soffit, sill)
        B.rect((o.u0, o.y0, 0), (0, 0, -t), (0, o.y1 - o.y0, 0), mat_reveal)            # left jamb faces +X
        B.rect((o.u1, o.y0, -t), (0, 0, t), (0, o.y1 - o.y0, 0), mat_reveal)            # right jamb faces -X
        B.rect((o.u0, o.y1, -t), (o.u1 - o.u0, 0, 0), (0, 0, t), mat_reveal)           # head faces -Y
        if o.y0 > y0 + 1e-6:
            B.rect((o.u0, o.y0, 0), (o.u1 - o.u0, 0, 0), (0, 0, -t), mat_reveal)        # sill faces +Y
    if ends and mat_reveal:
        B.rect((u_start, y0, -t), (0, 0, t), (0, y1 - y0, 0), mat_reveal)
        B.rect((length, y0, 0), (0, 0, -t), (0, y1 - y0, 0), mat_reveal)
    if top and (mat_top or mat_reveal):
        B.rect((u_start, y1, 0), (length - u_start, 0, 0), (0, 0, -t), mat_top or mat_reveal)
    if bottom and mat_reveal:
        B.rect((u_start, y0, -t), (length - u_start, 0, 0), (0, 0, t), mat_reveal)
    if col:
        # one collider per wall, with holes only for walk-through openings
        walk = [o for o in ops if o.kind in ("door_open", "void", "passage")]
        cu = sorted({u_start, length} | {o.u0 for o in walk} | {o.u1 for o in walk})
        for i in range(len(cu) - 1):
            ua, ub = cu[i], cu[i + 1]
            hole = [o for o in walk if o.u0 - 1e-6 <= (ua + ub) / 2 <= o.u1 + 1e-6]
            if not hole:
                B.cbox(ua, y0, -t, ub, y1, 0, col_group)
            else:
                o = hole[0]
                if o.y1 < y1:
                    B.cbox(ua, o.y1, -t, ub, y1, 0, col_group)
                if o.y0 > y0:
                    B.cbox(ua, y0, -t, ub, o.y0, 0, col_group)
    for side, spec in (("in", base_in), ("out", base_out)):
        if not spec:
            continue
        bm, bh = spec
        cuts = sorted((o.u0, o.u1) for o in ops if o.y0 <= y0 + 0.05)
        segs, cur = [], u_start
        for a, b in cuts:
            if a > cur:
                segs.append((cur, a))
            cur = max(cur, b)
        if cur < length:
            segs.append((cur, length))
        for a, b in segs:
            if b - a < 0.02:
                continue
            if side == "in":
                B.box(a, y0, -t - 0.014, b, y0 + bh, -t, bm, skip="sb")
            else:
                B.box(a, y0, 0.0, b, y0 + bh, 0.014, bm, skip="nb")
    for o in ops:
        fill_opening(B, o, t)


def fill_opening(B, o, t):
    k = o.kind
    op = o.opt
    if k in ("window", "window_int"):
        window(B, o.u0, o.u1, o.y0, o.y1, t, **op)
    elif k in ("door", "door_open"):
        door(B, o.u0, o.u1, o.y0, o.y1, t, **op)
    elif k == "glassdoor":
        glass_door(B, o.u0, o.u1, o.y0, o.y1, t, **op)
    elif k in ("void", "passage", "blank"):
        pass


def frame_rect(B, u0, u1, y0, y1, z0, z1, fw, mat, bottom=True):
    """rectangular frame ring (jambs, head, bottom rail) between z0..z1"""
    B.box(u0, y0, z0, u0 + fw, y1, z1, mat)
    B.box(u1 - fw, y0, z0, u1, y1, z1, mat)
    B.box(u0 + fw, y1 - fw, z0, u1 - fw, y1, z1, mat)
    if bottom:
        B.box(u0 + fw, y0, z0, u1 - fw, y0 + fw, z1, mat)


def interior_quad(B, u0, u1, y0, y1, z, interior):
    """an interior-mapped window pane (scripts/fx/interior.gdshader): interior = (material, seed, lit). The UVs
    carry the room's seed (u = seed + 0..1) and its chance of being lit at night out of 8 (v = lit + 0..1)."""
    mat, seed, lit = interior
    s, k = float(int(seed) % 4096), float(max(0, min(8, int(round(lit * 8)))))
    B.quad((u0, y0, z), (u1, y0, z), (u1, y1, z), (u0, y1, z), mat,
           uvs=[(s + 0.002, k + 0.002), (s + 0.998, k + 0.002), (s + 0.998, k + 0.998), (s + 0.002, k + 0.998)])


def window(B, u0, u1, y0, y1, t, frame="M_alu_anthracite", glass="M_glass_clear", depth=0.12, fw=0.06, fd=0.07,
           cols=None, rows=None, mullion=0.05, sill="M_alu_anthracite", sill_out=0.06, inner_sill=None, card=None,
           card_depth=0.6, transom=None, blind=None, shutter=None, rail=None, interior=None):
    """frame + mullions + glass recessed by `depth` from the outer face; optional exterior sill, interior
    window board, fake interior card behind the glass (for exterior-only buildings), roller blind.
    interior=(material, seed, lit): an interior-mapped pane replaces the glass, the card and its sleeve."""
    zg = -depth
    z0, z1 = zg - fd / 2, zg + fd / 2
    frame_rect(B, u0, u1, y0, y1, z0, z1, fw, frame)
    w, h = u1 - u0, y1 - y0
    if cols is None:
        cols = max(1, int(round(w / 1.25)))
    if rows is None:
        rows = 1
    for i in range(1, cols):
        u = u0 + w * i / cols
        B.box(u - mullion / 2, y0 + fw, z0 + 0.005, u + mullion / 2, y1 - fw, z1 - 0.005, frame)
    ys = []
    if transom:
        ys.append(y0 + transom)
    for j in range(1, rows):
        ys.append(y0 + h * j / rows)
    for yy in ys:
        B.box(u0 + fw, yy - mullion / 2, z0 + 0.005, u1 - fw, yy + mullion / 2, z1 - 0.005, frame)
    if interior:
        interior_quad(B, u0 + fw, u1 - fw, y0 + fw, y1 - fw, zg, interior)
        card = None
    else:
        B.quad((u0 + fw, y0 + fw, zg), (u1 - fw, y0 + fw, zg), (u1 - fw, y1 - fw, zg), (u0 + fw, y1 - fw, zg), glass,
               uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
    if sill and y0 > 0.05:
        B.box(u0 - 0.04, y0 - 0.05, -0.02, u1 + 0.04, y0, sill_out, sill)
    if inner_sill:
        B.box(u0 - 0.03, y0 - 0.03, -t - 0.04, u1 + 0.03, y0, z0, inner_sill)
    if blind:
        # roller blind box + lowered fabric (fraction `blind` of the height), seen through the glass
        bh = h * blind
        B.box(u0 + fw, y1 - fw - 0.08, z0 - 0.09, u1 - fw, y1 - fw, z0 - 0.01, frame)
        B.quad((u1 - fw - 0.01, y1 - fw - bh, z0 - 0.05), (u0 + fw + 0.01, y1 - fw - bh, z0 - 0.05),
               (u0 + fw + 0.01, y1 - fw - 0.08, z0 - 0.05), (u1 - fw - 0.01, y1 - fw - 0.08, z0 - 0.05), "M_fabric_grey",
               flip=True)
    if shutter is not None:
        # exterior roller shutter (volet roulant), fraction closed
        sh = h * shutter
        B.box(u0, y1 - 0.02, -0.02, u1, y1 + 0.18, 0.06, "M_pvc_white")
        if sh > 0.02:
            for k in range(int(sh / 0.05)):
                yy = y1 - 0.02 - (k + 1) * 0.05
                B.box(u0 + 0.02, yy, -0.05, u1 - 0.02, yy + 0.048, -0.03, "M_pvc_white")
    if rail:
        # french-window guard rail
        for yy in (y0 + 0.95, y0 + 0.5):
            B.box(u0 + 0.02, yy - 0.02, -0.03, u1 - 0.02, yy + 0.02, 0.0, rail)
        nb = max(2, int((u1 - u0) / 0.12))
        for k in range(nb + 1):
            u = u0 + 0.03 + (u1 - u0 - 0.06) * k / nb
            B.box(u - 0.008, y0 + 0.02, -0.025, u + 0.008, y0 + 0.95, -0.009, rail)
    if card:
        mat, uvr = card
        zc = -t - card_depth
        B.quad((u0, y0, zc), (u1, y0, zc), (u1, y1, zc), (u0, y1, zc), mat,
               uvs=[(uvr[0], uvr[1]), (uvr[2], uvr[1]), (uvr[2], uvr[3]), (uvr[0], uvr[3])])
        # dark sleeve so the card reads as a room
        for (a, b, c, d) in (((u0, y0, -t), (u0, y0, zc), (u0, y1, zc), (u0, y1, -t)),
                             ((u1, y1, -t), (u1, y1, zc), (u1, y0, zc), (u1, y0, -t)),
                             ((u0, y1, -t), (u0, y1, zc), (u1, y1, zc), (u1, y1, -t)),
                             ((u1, y0, -t), (u1, y0, zc), (u0, y0, zc), (u0, y0, -t))):
            B.quad(a, b, c, d, "M_room_sleeve")


def door(B, u0, u1, y0, y1, t, leaf="M_paint_metal_white", frame="M_alu_anthracite", leaves=1, glazed=False,
         handle="M_alu_silver", open_frac=0.0, push=True, kick=None, center=True, fw=0.06):
    """door frame + leaf/leaves set mid-wall. door_open kind leaves a passable gap (leaf swung open)."""
    zc = -t / 2 if center else -0.08
    fd = min(t, 0.14)
    B.box(u0, y0, zc - fd / 2, u0 + fw, y1, zc + fd / 2, frame)
    B.box(u1 - fw, y0, zc - fd / 2, u1, y1, zc + fd / 2, frame)
    B.box(u0, y1 - fw, zc - fd / 2, u1, y1, zc + fd / 2, frame)
    w = (u1 - u0 - 2 * fw) / leaves
    lt = 0.045
    for k in range(leaves):
        a = u0 + fw + k * w
        hinge_left = (k == 0)
        if open_frac > 0:
            # swung leaf, rotated about its hinge, pointing inwards (-z)
            ang = open_frac * math.pi / 2 * (1 if hinge_left else -1)
            hx = a if hinge_left else a + w
            with B.at(hx, 0, zc, ang):
                x0, x1 = (0, w - 0.01) if hinge_left else (-(w - 0.01), 0)
                B.box(x0, y0 + 0.01, -lt / 2, x1, y1 - fw - 0.005, lt / 2, leaf)
            continue
        B.box(a + 0.005, y0 + 0.01, zc - lt / 2, a + w - 0.005, y1 - fw - 0.005, zc + lt / 2, leaf)
        if glazed:
            gy0, gy1 = y0 + 0.9, y1 - fw - 0.25
            for zz, nrm in ((zc + lt / 2 + 0.001, 1), (zc - lt / 2 - 0.001, -1)):
                pts = [(a + 0.15, gy0, zz), (a + w - 0.15, gy0, zz), (a + w - 0.15, gy1, zz), (a + 0.15, gy1, zz)]
                B.quad(*(pts if nrm > 0 else pts[::-1]), "M_glass_clear", uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
        hx = a + w - 0.09 if hinge_left else a + 0.09
        for s in (1, -1):
            zz = zc + s * (lt / 2 + 0.03)
            B.box(hx - 0.012, y0 + 0.98, min(zz, zc + s * lt / 2), hx + 0.012, y0 + 1.06, max(zz, zc + s * lt / 2), handle)
            hx2 = hx - 0.11 if hinge_left else hx + 0.11
            B.box(min(hx, hx2), y0 + 1.0, zz - s * 0.012, max(hx, hx2), y0 + 1.03, zz + s * 0.012, handle)
        if kick:
            for s in (1, -1):
                zz = zc + s * (lt / 2 + 0.002)
                B.box(a + 0.02, y0 + 0.02, min(zz, zz + s * 0.003), a + w - 0.02, y0 + 0.25, max(zz, zz + s * 0.003), kick)


def glass_door(B, u0, u1, y0, y1, t, frame="M_alu_anthracite", leaves=2, bar="M_alu_silver", center=False, transom=None):
    """aluminium-framed glass entrance doors (closed)"""
    zc = -t / 2 if center else -0.1
    fd = 0.1
    fw = 0.07
    yt = y1 if transom is None else y1 - transom
    frame_rect(B, u0, u1, y0, y1, zc - fd / 2, zc + fd / 2, fw, frame, bottom=False)
    if transom:
        B.box(u0 + fw, yt - fw, zc - fd / 2, u1 - fw, yt, zc + fd / 2, frame)
        B.quad((u0 + fw, yt, zc), (u1 - fw, yt, zc), (u1 - fw, y1 - fw, zc), (u0 + fw, y1 - fw, zc), "M_glass_clear",
               uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
    w = (u1 - u0 - 2 * fw) / leaves
    for k in range(leaves):
        a = u0 + fw + k * w
        b = a + w
        lf = 0.05
        frame_rect(B, a + 0.005, b - 0.005, y0 + 0.005, yt - fw - 0.005, zc - 0.025, zc + 0.025, lf, frame)
        B.box(a + lf, y0 + 0.005, zc - 0.025, b - lf, y0 + 0.16, zc + 0.025, frame)
        B.quad((a + lf, y0 + 0.16, zc), (b - lf, y0 + 0.16, zc), (b - lf, yt - fw - lf, zc), (a + lf, yt - fw - lf, zc),
               "M_glass_clear", uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
        # push bars both sides
        hx0, hx1 = (b - 0.12, b - 0.08) if k == 0 else (a + 0.08, a + 0.12)
        for s in (1, -1):
            zz = zc + s * 0.07
            B.box(hx0, y0 + 0.7, min(zz, zz - s * 0.015), hx1, y0 + 1.5, max(zz, zz - s * 0.015), bar)
            B.box(hx0, y0 + 0.75, min(zc + s * 0.025, zz), hx1, y0 + 0.78, max(zc + s * 0.025, zz), bar)
            B.box(hx0, y0 + 1.42, min(zc + s * 0.025, zz), hx1, y0 + 1.45, max(zc + s * 0.025, zz), bar)


def curtain_wall(B, u0, u1, y0, y1, z, mull_u, mull_y, frame="M_alu_anthracite", glass="M_glass_facade", depth=0.12,
                 mw=0.06, spandrels=None, card=None, card_depth=0.8):
    """stick curtain wall in the plane z (outer face of mullion caps at z + depth/2)."""
    us = [u0]
    u = u0
    while u + mull_u < u1 - 0.2:
        u += mull_u
        us.append(u)
    us.append(u1)
    ys = [y0]
    y = y0
    while y + mull_y < y1 - 0.2:
        y += mull_y
        ys.append(y)
    ys.append(y1)
    for uu in us:
        B.box(uu - mw / 2, y0, z - depth / 2, uu + mw / 2, y1, z + depth / 2, frame)
    for yy in ys:
        B.box(u0, yy - mw / 2, z - depth / 2, u1, yy + mw / 2, z + depth / 2 - 0.01, frame)
    for i in range(len(us) - 1):
        for j in range(len(ys) - 1):
            a, b, c, d = us[i] + mw / 2, us[i + 1] - mw / 2, ys[j] + mw / 2, ys[j + 1] - mw / 2
            sp = spandrels(i, j) if spandrels else None
            if sp:
                B.quad((a, c, z), (b, c, z), (b, d, z), (a, d, z), sp)
            else:
                B.quad((a, c, z), (b, c, z), (b, d, z), (a, d, z), glass, uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
                if card:
                    mat, pick = card
                    uvr = pick(i, j)
                    if uvr:
                        zc = z - card_depth
                        B.quad((a, c, zc), (b, c, zc), (b, d, zc), (a, d, zc), mat,
                               uvs=[(uvr[0], uvr[1]), (uvr[2], uvr[1]), (uvr[2], uvr[3]), (uvr[0], uvr[3])])
    return us, ys


def stairs(B, x_c, width, z_start, z_end, y0, y1, mat_tread, mat_riser=None, mat_side=None, n=None, nosing="M_alu_silver",
           col_group=None, solid_below=True):
    """straight flight along -z or +z (z_start at y0 -> z_end at y1) centred on x_c; visual steps only, ramp collider"""
    mat_riser = mat_riser or mat_tread
    mat_side = mat_side or mat_riser
    rise_total = y1 - y0
    if n is None:
        n = max(1, int(round(abs(rise_total) / 0.18)))
    rise = rise_total / n
    run = (z_end - z_start) / n
    x0, x1 = x_c - width / 2, x_c + width / 2
    for i in range(n):
        za = z_start + run * i
        zb = za + run
        yb = y0 + rise * (i + 1)
        lo, hi = min(za, zb), max(za, zb)
        base = y0 - 0.2 if solid_below else yb - 0.2
        # tread top + riser front + sides
        B.rect((x0, yb, hi), (x1 - x0, 0, 0), (0, 0, lo - hi), mat_tread)
        rz = za
        if run < 0:
            B.rect((x0, yb - rise, rz), (x1 - x0, 0, 0), (0, rise, 0), mat_riser)
        else:
            B.rect((x1, yb - rise, rz), (x0 - x1, 0, 0), (0, rise, 0), mat_riser)
        B.rect((x1, base, hi), (0, 0, lo - hi), (0, yb - base, 0), mat_side)
        B.rect((x0, base, lo), (0, 0, hi - lo), (0, yb - base, 0), mat_side)
        if nosing:
            if run < 0:
                B.box(x0 + 0.02, yb - 0.025, rz - 0.035 + (0 if run < 0 else 0), x1 - 0.02, yb + 0.002, rz + 0.0, nosing)
            else:
                B.box(x0 + 0.02, yb - 0.025, rz, x1 - 0.02, yb + 0.002, rz + 0.035, nosing)
    B.cramp(x_c, y0, z_start, x_c, y1, z_end, width, 0.3, col_group)


def handrail(B, pts, h=0.9, r=0.025, mat="M_alu_silver", post_every=1.2, post_mat=None, posts=True):
    """tube handrail at height h above a polyline of floor points, with posts"""
    post_mat = post_mat or mat
    top = [(x, y + h, z) for (x, y, z) in pts]
    B.tube(top, r, mat, seg=8)
    if posts:
        for i in range(len(pts) - 1):
            a, b = Vector(pts[i]), Vector(pts[i + 1])
            L = (b - a).length
            n = max(1, int(round(L / post_every)))
            for k in range(n + (1 if i == len(pts) - 2 else 0)):
                p = a + (b - a) * (k / n)
                B.cyl(p.x, p.y, p.z, 0.02, h, post_mat, seg=8)


def glass_railing(B, u0, u1, y0, h=1.05, z=0.0, mat_glass="M_glass_railing", cap="M_alu_silver", posts="M_alu_silver",
                  post_every=1.5, col_group=None, col_h=2.4):
    """frameless glass balustrade along local x with a cap rail; collider goes up to col_h (no falling over)"""
    B.quad((u0, y0 + 0.05, z), (u1, y0 + 0.05, z), (u1, y0 + h - 0.04, z), (u0, y0 + h - 0.04, z), mat_glass,
           uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
    B.quad((u1, y0 + 0.05, z), (u0, y0 + 0.05, z), (u0, y0 + h - 0.04, z), (u1, y0 + h - 0.04, z), mat_glass,
           uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
    B.box(u0, y0 + h - 0.04, z - 0.03, u1, y0 + h + 0.01, z + 0.03, cap)
    B.box(u0, y0, z - 0.04, u1, y0 + 0.06, z + 0.04, posts)
    n = max(1, int(round((u1 - u0) / post_every)))
    for k in range(n + 1):
        u = u0 + (u1 - u0) * k / n
        B.box(u - 0.02, y0 + 0.06, z - 0.035, u + 0.02, y0 + h - 0.04, z + 0.035, posts)
    if col_group is not False:
        B.cbox(u0, y0, z - 0.05, u1, y0 + col_h, z + 0.05, col_group)


def parapet(B, length, y0, h, thick, mat, coping="M_zinc", inner_mat=None):
    """roof parapet wall along local x at the outer face z=0, with a metal coping"""
    B.box(0, y0, -thick, length, y0 + h, 0, mat, skip="t", mats={"n": inner_mat or mat})
    B.box(-0.03, y0 + h, -thick - 0.03, length + 0.03, y0 + h + 0.05, 0.04, coping)


def downpipe(B, u, y0, y1, z=0.075, r=0.05, mat="M_zinc", brackets=2.0):
    B.cyl(u, y0 + 0.25, z, r, y1 - y0 - 0.25, mat, seg=10, caps=(False, True))
    B.cyl(u, y0 + 0.02, z, r * 1.25, 0.25, mat, seg=10)  # boot
    y = y0 + 1.2
    while y < y1 - 0.3:
        B.box(u - r - 0.02, y, -0.01, u + r + 0.02, y + 0.04, z + r + 0.015, mat)
        y += brackets
    # hopper head
    B.box(u - 0.11, y1 - 0.3, -0.01, u + 0.11, y1, z + 0.12, mat)
