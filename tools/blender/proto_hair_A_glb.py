"""Prototype A (hair cards shaped by the scan): a small numpy-only reader for the character .glb files.

Reads the skinned meshes of a built character (positions in Blender's Z-up world frame, normals, UVs, triangles
with their material, skin weights), the joints' rest positions and the PNG textures, so the strand growing in
proto_hair_A_grow.py can run in plain python3.11 (numpy + scipy) without Blender or the Godot lock.
"""
import json, struct
import numpy as np

_COMP = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
_NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def _yup_to_zup(P):
    """glTF (Y up, -Z forward) -> Blender (Z up): (x, y, z) -> (x, -z, y)."""
    return np.stack([P[:, 0], -P[:, 2], P[:, 1]], 1)


class GLB:
    def __init__(self, path):
        b = open(path, "rb").read()
        jl = struct.unpack("<I", b[12:16])[0]
        self.J = json.loads(b[20:20 + jl])
        off = 20 + jl
        bl = struct.unpack("<I", b[off:off + 4])[0]
        self.bin = b[off + 8:off + 8 + bl]

    def accessor(self, i):
        a = self.J["accessors"][i]
        bv = self.J["bufferViews"][a["bufferView"]]
        dt = np.dtype(_COMP[a["componentType"]])
        n = _NCOMP[a["type"]]
        start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = bv.get("byteStride", 0)
        if stride and stride != dt.itemsize * n:
            raw = np.frombuffer(self.bin, np.uint8, count=stride * (a["count"] - 1) + dt.itemsize * n, offset=start)
            out = np.lib.stride_tricks.as_strided(raw, (a["count"], dt.itemsize * n), (stride, 1)).copy()
            arr = out.view(dt).reshape(a["count"], n)
        else:
            arr = np.frombuffer(self.bin, dt, count=a["count"] * n, offset=start).reshape(a["count"], n)
        if a.get("normalized"):
            arr = arr.astype(np.float32) / np.iinfo(dt).max
        return arr

    def image_bytes(self, i):
        im = self.J["images"][i]
        bv = self.J["bufferViews"][im["bufferView"]]
        s = bv.get("byteOffset", 0)
        return self.bin[s:s + bv["byteLength"]]

    def texture_image(self, tex_index):
        return self.J["textures"][tex_index]["source"]

    def material(self, name_part):
        for i, m in enumerate(self.J.get("materials", [])):
            if name_part in m["name"]:
                return i, m
        return None, None

    def joints(self):
        """{bone name: rest head position (Blender frame)} from the skin's inverse bind matrices."""
        sk = self.J["skins"][0]
        ibm = self.accessor(sk["inverseBindMatrices"]).reshape(-1, 4, 4).transpose(0, 2, 1)   # column-major
        out = {}
        for k, j in enumerate(sk["joints"]):
            M = np.linalg.inv(ibm[k].astype(np.float64))
            out[self.J["nodes"][j]["name"]] = _yup_to_zup(M[None, :3, 3])[0]
        return out, [self.J["nodes"][j]["name"] for j in sk["joints"]]

    def mesh(self, node_name_part):
        """Merged primitives of the first mesh node whose name contains node_name_part."""
        for n in self.J["nodes"]:
            if "mesh" in n and node_name_part in n["name"]:
                break
        else:
            return None
        m = self.J["meshes"][n["mesh"]]
        P, N, UV, T, MAT, JI, JW = [], [], [], [], [], [], []
        base = 0
        for p in m["primitives"]:
            at = p["attributes"]
            pos = self.accessor(at["POSITION"]).astype(np.float64)
            P.append(_yup_to_zup(pos))
            N.append(_yup_to_zup(self.accessor(at["NORMAL"]).astype(np.float64)))
            UV.append(self.accessor(at["TEXCOORD_0"]).astype(np.float64) if "TEXCOORD_0" in at else np.zeros((len(pos), 2)))
            if "JOINTS_0" in at:
                JI.append(self.accessor(at["JOINTS_0"]).astype(np.int64))
                JW.append(self.accessor(at["WEIGHTS_0"]).astype(np.float64))
            idx = self.accessor(p["indices"]).astype(np.int64).reshape(-1, 3) + base
            T.append(idx)
            MAT.append(np.full(len(idx), p.get("material", -1)))
            base += len(pos)
        out = {"name": n["name"], "P": np.concatenate(P), "N": np.concatenate(N), "UV": np.concatenate(UV),
               "T": np.concatenate(T), "mat": np.concatenate(MAT), "extras": n.get("extras", {})}
        if JI:
            out["JI"] = np.concatenate(JI)
            out["JW"] = np.concatenate(JW)
        return out

    def joint_weight(self, mesh, names, joint_names):
        """Per-vertex summed skin weight of the given bones."""
        ids = [joint_names.index(b) for b in names if b in joint_names]
        w = np.zeros(len(mesh["P"]))
        for c in range(mesh["JI"].shape[1]):
            w += np.where(np.isin(mesh["JI"][:, c], ids), mesh["JW"][:, c], 0.0)
        return w


def decode_png(data):
    import cv2
    im = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
    if im.ndim == 2:
        im = im[..., None].repeat(3, 2)
    return im[..., :3][..., ::-1].astype(np.float32) / 255.0     # RGB, sRGB-encoded 0..1


def sample(img, uv):
    """Bilinear lookup of an image (H, W, C) at glTF UVs (v down from the top: glTF convention)."""
    H, W = img.shape[:2]
    x = np.clip((uv[:, 0] % 1.0) * W - 0.5, 0, W - 1.001)
    y = np.clip((uv[:, 1] % 1.0) * H - 0.5, 0, H - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    a = img[y0, x0] * (1 - fx) + img[y0, x0 + 1] * fx
    b = img[y0 + 1, x0] * (1 - fx) + img[y0 + 1, x0 + 1] * fx
    return a * (1 - fy) + b * fy
