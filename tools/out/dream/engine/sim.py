"""A small deterministic rigid-body simulation of the round-2 earbud on the Amphi 4 aisle steps (earbud.py), compiled
with numba: impulse-based contacts (sequential impulses with accumulated clamping, Coulomb friction, restitution
above a speed threshold), the body's real inertia (angular momentum is integrated, so it precesses in flight),
point contacts from the lathe's vertices against the steps' treads, risers and nosings and the aisle's side panels.
The dream's draw down the aisle is an extra horizontal acceleration, a piecewise-linear table over time.
Fixed step, no randomness: the same parameters give the same tumble to the last bit.
"""
import math
import numpy as np
import numba as nb
from earbud import Earbud, SECTIONS, AISLE_X

Z_LO = np.array([s[0] for s in SECTIONS])
Z_HI = np.array([s[1] for s in SECTIONS])
HS = np.array([s[2] for s in SECTIONS])


@nb.njit(cache=True)
def _contact(px, py, pz, z_lo, z_hi, hs, ax0, ax1):
    """Penetration depth (<= 0: none) and normal of one point."""
    ns = z_lo.shape[0]
    i = 0
    while i < ns - 1 and not (z_lo[i] < pz):
        i += 1
    h = hs[i]
    depth = -1.0
    nx = 0.0
    ny = 0.0
    nz = 0.0
    if py < h:
        d_up = h - py
        d_front = 1e9
        if i + 1 < ns and hs[i + 1] <= py:
            d_front = pz - z_lo[i]
        d_back = 1e9
        if i > 0 and hs[i - 1] <= py:
            d_back = z_hi[i] - pz
        if d_up <= d_front and d_up <= d_back:
            depth = d_up
            ny = 1.0
        elif d_front <= d_back:
            depth = d_front
            nz = -1.0
        else:
            depth = d_back
            nz = 1.0
    dw = ax0 - px
    if dw > 0.0 and dw > depth:
        depth = dw
        nx, ny, nz = 1.0, 0.0, 0.0
    dw = px - ax1
    if dw > 0.0 and dw > depth:
        depth = dw
        nx, ny, nz = -1.0, 0.0, 0.0
    return depth, nx, ny, nz


@nb.njit(cache=True)
def _rotm(wx, wy, wz, dt):
    a = math.sqrt(wx * wx + wy * wy + wz * wz)
    M = np.eye(3)
    if a * dt < 1e-14:
        return M
    x, y, z = wx / a, wy / a, wz / a
    c = math.cos(a * dt)
    s = math.sin(a * dt)
    C = 1.0 - c
    M[0, 0] = c + x * x * C
    M[0, 1] = x * y * C - z * s
    M[0, 2] = x * z * C + y * s
    M[1, 0] = y * x * C + z * s
    M[1, 1] = c + y * y * C
    M[1, 2] = y * z * C - x * s
    M[2, 0] = z * x * C - y * s
    M[2, 1] = z * y * C + x * s
    M[2, 2] = c + z * z * C
    return M


@nb.njit(cache=True)
def _cross(a, b):
    return np.array([a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]])


@nb.njit(cache=True)
def _ortho(R):
    # Gram-Schmidt on the columns
    c0 = R[:, 0] / math.sqrt(R[0, 0] ** 2 + R[1, 0] ** 2 + R[2, 0] ** 2)
    c1 = R[:, 1] - (c0 @ R[:, 1]) * c0
    c1 = c1 / math.sqrt(c1 @ c1)
    c2 = _cross(c0, c1)
    out = np.empty((3, 3))
    out[:, 0] = c0
    out[:, 1] = c1
    out[:, 2] = c2
    return out


@nb.njit(cache=True)
def _run(pts, com, Ib, Ib_inv, mass, x0, R0, v0, w0, prm, pull_t, pull_a, z_lo, z_hi, hs, ax0, ax1, n_steps, log_every):
    g, dt, e, v_bounce, mu, roll_damp, lin_damp = prm[0], prm[1], prm[2], prm[3], prm[4], prm[5], prm[6]
    iters = int(prm[7])
    max_c = int(prm[8])
    c_rr = prm[9]            # rolling resistance of the carpet's pile: lever arm (m) of the normal force
    zf0, zf1 = prm[10], prm[11]   # the pull fades out as the centre of mass goes from z zf1 down to zf0
    R = R0.copy()
    x = x0 + R @ com
    v = v0.copy()
    L = (R @ Ib @ R.T) @ w0
    npts = pts.shape[0]
    nlog = n_steps // log_every + 1
    out_x = np.zeros((nlog, 3))
    out_R = np.zeros((nlog, 3, 3))
    out_nc = np.zeros(nlog, np.int64)
    out_v = np.zeros((nlog, 3))
    out_w = np.zeros((nlog, 3))
    rw = np.zeros((npts, 3))
    depth = np.zeros(npts)
    nrm = np.zeros((npts, 3))
    li = 0
    for step in range(n_steps + 1):
        t = step * dt
        Iw_inv = R @ Ib_inv @ R.T
        w = Iw_inv @ L
        # the pull, interpolated in its table
        ax = 0.0
        az = 0.0
        ay = 0.0
        k = 0
        while k < pull_t.shape[0] - 1 and pull_t[k + 1] <= t:
            k += 1
        if k >= pull_t.shape[0] - 1:
            ax, ay, az = pull_a[-1, 0], pull_a[-1, 1], pull_a[-1, 2]
        else:
            f = (t - pull_t[k]) / (pull_t[k + 1] - pull_t[k])
            f = min(max(f, 0.0), 1.0)
            ax = pull_a[k, 0] + (pull_a[k + 1, 0] - pull_a[k, 0]) * f
            ay = pull_a[k, 1] + (pull_a[k + 1, 1] - pull_a[k, 1]) * f
            az = pull_a[k, 2] + (pull_a[k + 1, 2] - pull_a[k, 2]) * f
        fz = 1.0
        if zf1 > zf0:
            fz = min(max((x[2] - zf0) / (zf1 - zf0), 0.0), 1.0)
        v[0] += ax * fz * dt
        v[1] += (ay * fz - g) * dt
        v[2] += az * fz * dt
        # contacts: the deepest points, at least 6 mm apart
        nhit = 0
        for i in range(npts):
            r = R @ pts[i]
            rw[i] = r
            d, nx, ny, nz = _contact(x[0] + r[0], x[1] + r[1], x[2] + r[2], z_lo, z_hi, hs, ax0, ax1)
            depth[i] = d
            nrm[i, 0] = nx
            nrm[i, 1] = ny
            nrm[i, 2] = nz
            if d > 0.0:
                nhit += 1
        nc = 0
        if nhit > 0:
            order = np.argsort(-depth)
            chosen = np.zeros(max_c, np.int64)
            for oi in range(npts):
                i = order[oi]
                if depth[i] <= 0.0:
                    break
                ok = True
                for c in range(nc):
                    j = chosen[c]
                    dd = rw[i] - rw[j]
                    if dd @ dd < 0.006 * 0.006:
                        ok = False
                        break
                if ok:
                    chosen[nc] = i
                    nc += 1
                    if nc >= max_c:
                        break
            target = np.zeros(nc)
            kn = np.zeros(nc)
            Pn = np.zeros(nc)
            Pt = np.zeros((nc, 3))
            for c in range(nc):
                i = chosen[c]
                r = rw[i]
                n = nrm[i]
                vn0 = (v + _cross(w, r)) @ n
                if vn0 < -v_bounce:
                    target[c] = -e * vn0
                else:
                    target[c] = min(max(depth[i] - 0.0005, 0.0) * 8.0, 0.2)
                kn[c] = 1.0 / mass + n @ _cross(Iw_inv @ _cross(r, n), r)
            for it in range(iters):
                for c in range(nc):
                    i = chosen[c]
                    r = rw[i]
                    n = nrm[i]
                    vr = v + _cross(w, r)
                    vn = vr @ n
                    jn = (target[c] - vn) / kn[c]
                    new = max(Pn[c] + jn, 0.0)
                    d = new - Pn[c]
                    Pn[c] = new
                    if d != 0.0:
                        v = v + d * n / mass
                        L = L + _cross(r, d * n)
                        w = Iw_inv @ L
                    vr = v + _cross(w, r)
                    vt = vr - (vr @ n) * n
                    s = math.sqrt(vt @ vt)
                    if s > 1e-9:
                        td = vt / s
                        kt = 1.0 / mass + td @ _cross(Iw_inv @ _cross(r, td), r)
                        newT = Pt[c] - (s / kt) * td
                        lim = mu * Pn[c]
                        nT = math.sqrt(newT @ newT)
                        if nT > lim:
                            newT = newT * (lim / nT)
                        dT = newT - Pt[c]
                        Pt[c] = newT
                        v = v + dT / mass
                        L = L + _cross(r, dT)
                        w = Iw_inv @ L
            L = L * math.exp(-roll_damp * dt)
            v = v * math.exp(-lin_damp * dt)
            # rolling resistance: up to c_rr times the normal impulse of angular impulse against the spin
            pn = 0.0
            for c in range(nc):
                pn += Pn[c]
            lim = c_rr * pn
            nL = math.sqrt(L @ L)
            if nL <= lim:
                L = L * 0.0
            elif nL > 0.0:
                L = L * (1.0 - lim / nL)
            w = Iw_inv @ L
        if step % log_every == 0:
            out_x[li] = x
            out_R[li] = R
            out_nc[li] = nc
            out_v[li] = v
            out_w[li] = w
            li += 1
        x = x + v * dt
        R = _ortho(np.ascontiguousarray(_rotm(w[0], w[1], w[2], dt)) @ np.ascontiguousarray(R))
    return out_x, out_R, out_nc, out_v, out_w


DEFAULTS = dict(g=9.81, dt=1.0 / 2000.0, e=0.35, v_bounce=0.12, mu=0.45, roll_damp=2.5, lin_damp=0.3, iters=10,
                max_contacts=6, t_end=2.5, c_rr=0.0, zf0=0.0, zf1=0.0)


def simulate(bud: Earbud, pod_pos, pod_basis, pull_t, pull_a, v0=(0, 0, 0), w0=(0, 0, 0), log_dt=1.0 / 1000.0, **kw):
    """Simulates from the pod pose and returns samples every log_dt: t, pod origin, basis, contacts, COM, v, w."""
    p = dict(DEFAULTS)
    p.update(kw)
    prm = np.array([p["g"], p["dt"], p["e"], p["v_bounce"], p["mu"], p["roll_damp"], p["lin_damp"], p["iters"],
                    p["max_contacts"], p["c_rr"], p["zf0"], p["zf1"]], float)
    n_steps = int(round(p["t_end"] / p["dt"]))
    every = max(int(round(log_dt / p["dt"])), 1)
    x, R, nc, v, w = _run(bud.points, bud.com, bud.inertia, bud.inv_inertia, bud.mass,
                          np.asarray(pod_pos, float), np.asarray(pod_basis, float), np.asarray(v0, float),
                          np.asarray(w0, float), prm, np.asarray(pull_t, float), np.asarray(pull_a, float),
                          Z_LO, Z_HI, HS, AISLE_X[0], AISLE_X[1], n_steps, every)
    o = x - np.einsum("nij,j->ni", R, bud.com)
    t = np.arange(len(x)) * every * p["dt"]
    return {"t": t, "o": o, "b": R, "nc": nc, "air": nc == 0, "x": x, "v": v, "w": w}
