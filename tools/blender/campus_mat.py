"""Material library for the campus (Principled BSDF node trees the glTF exporter understands).

Each material = optional CC0 texture set (diff / nor_gl / arm) x colour factor x vertex colour (grime,
macro variation, tile variation baked by the geometry builder). `tile` is the size in metres covered by
one texture repeat; the builder box-maps UVs with it so texel density stays constant everywhere.
Every glass material has `glass` in its name (Godot swaps it for a tuned glass shader).
"""
import os, bpy
import campus_tex as T


def srgb(h):
    """'#rrggbb' -> linear (r, g, b)"""
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple((x / 12.92) if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def K(kelvin):
    """approximate black-body colour as '#rrggbb' (Tanner Helland fit), for lights and emissive panels"""
    import math
    t = kelvin / 100.0
    r = 255 if t <= 66 else 329.698727446 * ((t - 60) ** -0.1332047592)
    g = (99.4708025861 * math.log(t) - 161.1195681661) if t <= 66 else 288.1221695283 * ((t - 60) ** -0.0755148492)
    b = 255 if t >= 66 else (0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307)
    cl = lambda v: max(0, min(255, int(round(v))))
    return "#%02x%02x%02x" % (cl(r), cl(g), cl(b))


# tex: (source, id, res)  source: ph | acg | gen (generated image path relative to assets/textures)
# grime: ext (outdoor walls, dirt near the ground) | int (indoor, light) | floor | none
M = {}


def mat(name, tex=None, tile=2.0, color="#ffffff", rough=None, metal=0.0, normal=1.0, emit=None, alpha=None,
        double=False, grime="none", macro=0.06, maps=("diff", "nor_gl", "arm"), rough_tex=True, alpha_cut=0.5):
    M[name] = dict(name=name, tex=tex, tile=tile, color=color, rough=rough, metal=metal, normal=normal, emit=emit,
                   alpha=alpha, double=double, grime=grime, macro=macro, maps=maps, rough_tex=rough_tex, alpha_cut=alpha_cut)


PH, ACG = "ph", "acg"
# ------------------------------------------------------------------ exterior ground
mat("M_asphalt", (PH, "asphalt_02", "2k"), tile=4.0, color="#e4e4e4", grime="floor", macro=0.10)
mat("M_asphalt_patch", (PH, "asphalt_02", "2k"), tile=4.0, color="#9c9c9c", grime="floor", macro=0.06)
mat("M_road_paint", (PH, "asphalt_02", "2k"), tile=4.0, color="#d8d6cf", maps=("nor_gl", "arm"), rough=0.75, grime="floor", macro=0.10)
mat("M_road_paint_yellow", (PH, "asphalt_02", "2k"), tile=4.0, color="#d9a521", maps=("nor_gl", "arm"), rough=0.7, grime="floor", macro=0.08)
mat("M_sidewalk", (PH, "pavement_03", "2k"), tile=2.0, color="#d6d6d4", grime="floor", macro=0.10)
mat("M_curb", (PH, "concrete_wall_008", "2k"), tile=1.6, color="#9d9fa3", grime="ext", macro=0.06)
mat("M_gutter", (PH, "concrete_pavers_02", "2k"), tile=1.0, color="#a8a8a8", grime="floor", macro=0.08)
mat("M_court_slabs", (PH, "concrete_tiles_02", "2k"), tile=3.6, color="#e6e3dc", grime="floor", macro=0.10)
mat("M_pavers_passage", (PH, "concrete_pavers_02", "2k"), tile=2.0, color="#c8c6c2", grime="floor", macro=0.08)
mat("M_soil", (PH, "brown_mud_leaves_01", "1k"), tile=1.3, grime="none", macro=0.08)
mat("M_gravel", (PH, "gravel_concrete", "1k"), tile=2.0, color="#bdbab3", grime="none", macro=0.08)

# ------------------------------------------------------------------ facades
mat("M_concrete", (PH, "concrete_wall_008", "2k"), tile=2.7, color="#ece8e1", grime="ext", macro=0.08)
mat("M_concrete_x", (PH, "concrete_wall_008", "2k"), tile=2.7, color="#f2e9da", grime="ext", macro=0.08)
mat("M_concrete_dark", (PH, "concrete_wall_008", "2k"), tile=2.7, color="#8d8b88", grime="ext", macro=0.08)
mat("M_concrete_panels", (PH, "concrete_wall_004", "2k"), tile=4.0, color="#b9bcbf", grime="ext", macro=0.08, maps=("diffg", "nor_gl", "arm"))
mat("M_render_white", (PH, "white_stucco", "2k"), tile=2.0, color="#f3f1ec", grime="ext", macro=0.07)
mat("M_render_beige", (PH, "beige_wall_001", "2k"), tile=3.0, color="#f1e6d2", grime="ext", macro=0.08)
mat("M_render_sand", (PH, "beige_wall_001", "2k"), tile=3.0, color="#e5cfae", grime="ext", macro=0.08)
mat("M_render_grey", (PH, "plastered_wall_02", "2k"), tile=2.2, color="#cfcdc9", grime="ext", macro=0.08)
mat("M_render_rose", (PH, "plastered_wall_02", "2k"), tile=2.2, color="#e8cfc0", grime="ext", macro=0.08)
mat("M_brick", (PH, "brick_wall_001", "2k"), tile=3.0, grime="ext", macro=0.06)
mat("M_brick_yellow", (PH, "yellow_brick", "2k"), tile=2.0, grime="ext", macro=0.06)
mat("M_trespa", (PH, "oak_veneer_01", "2k"), tile=1.8, color="#9c7650", rough=0.5, grime="ext", macro=0.04, maps=("diffg", "nor_gl", "arm"))
mat("M_roof", (PH, "bitumen", "1k"), tile=6.0, color="#9a9a9a", grime="none", macro=0.10)
mat("M_roof_gravel", (PH, "gravel_concrete", "1k"), tile=2.0, color="#9e9b95", grime="none", macro=0.10)
mat("M_metal_blue", (ACG, "Metal009", "1K"), tile=1.5, color="#2f6497", rough=0.42, metal=0.55, grime="ext", macro=0.05)
mat("M_metal_blue_light", (ACG, "Metal009", "1K"), tile=1.5, color="#4b86bf", rough=0.42, metal=0.55, grime="ext", macro=0.05)
mat("M_spandrel_dark", None, color="#20262e", rough=0.35, metal=0.4, grime="ext", macro=0.04)
mat("M_spandrel_grey", None, color="#7b8189", rough=0.45, metal=0.3, grime="ext", macro=0.04)

# ------------------------------------------------------------------ metals & frames
mat("M_alu_anthracite", None, color="#2e3236", rough=0.42, metal=0.65, grime="ext", macro=0.03)
mat("M_alu_silver", None, color="#a9adb1", rough=0.32, metal=0.9, grime="ext", macro=0.03)
mat("M_pvc_white", None, color="#e9e9e4", rough=0.45, grime="ext", macro=0.03)
mat("M_steel", (ACG, "Metal009", "1K"), tile=1.0, color="#b9bdc1", grime="none", macro=0.03)
mat("M_steel_dark", (ACG, "Metal009", "1K"), tile=1.0, color="#4a4f55", rough=0.45, grime="none", macro=0.03)
mat("M_paint_metal_dark", None, color="#25292e", rough=0.5, metal=0.3, grime="ext", macro=0.04)
mat("M_paint_metal_green", None, color="#2c4b38", rough=0.5, metal=0.3, grime="ext", macro=0.04)
mat("M_paint_metal_red", None, color="#b8302b", rough=0.45, metal=0.2, grime="ext", macro=0.04)
mat("M_paint_metal_white", None, color="#e6e6e2", rough=0.45, metal=0.2, grime="ext", macro=0.03)
mat("M_paint_metal_teal", None, color="#138a8a", rough=0.45, metal=0.2, grime="ext", macro=0.03)
mat("M_paint_metal_yellow", None, color="#e2b51d", rough=0.45, metal=0.2, grime="ext", macro=0.03)
mat("M_chrome", None, color="#d7d9dc", rough=0.12, metal=1.0, grime="none", macro=0.0)
mat("M_zinc", None, color="#8e9399", rough=0.45, metal=0.8, grime="ext", macro=0.05)
mat("M_cast_iron", (ACG, "Metal009", "1K"), tile=0.8, color="#3a3836", rough=0.6, metal=0.6, grime="none", macro=0.06)

# ------------------------------------------------------------------ interior surfaces
mat("M_terrazzo", (ACG, "Terrazzo005", "2K"), tile=1.15, color="#ecebe8", rough=0.5, grime="floor", macro=0.05)
mat("M_paint_white", (PH, "painted_plaster_wall", "1k"), tile=2.0, color="#f2f0ec", grime="int", macro=0.04, maps=("nor_gl", "arm"))
mat("M_paint_grey", (PH, "painted_plaster_wall", "1k"), tile=2.0, color="#c4c7ca", grime="int", macro=0.04, maps=("nor_gl", "arm"))
mat("M_paint_warm", (PH, "painted_plaster_wall", "1k"), tile=2.0, color="#e9e1d4", grime="int", macro=0.04, maps=("nor_gl", "arm"))
mat("M_paint_navy", (PH, "painted_plaster_wall", "1k"), tile=2.0, color="#2a3a8c", grime="int", macro=0.04, maps=("nor_gl", "arm"))
mat("M_paint_epita", (PH, "painted_plaster_wall", "1k"), tile=2.0, color="#1f2a52", grime="int", macro=0.03, maps=("nor_gl", "arm"))
mat("M_paint_lime", (PH, "painted_plaster_wall", "1k"), tile=2.0, color="#b9f20f", grime="int", macro=0.03, maps=("nor_gl", "arm"))
mat("M_paint_amphi", (PH, "painted_plaster_wall", "1k"), tile=2.0, color="#d9d8d3", grime="int", macro=0.04, maps=("nor_gl", "arm"))
mat("M_paint_under", (PH, "painted_plaster_wall", "1k"), tile=2.0, color="#3c4048", grime="int", macro=0.06, maps=("nor_gl", "arm"))
mat("M_paint_under_teal", (PH, "painted_plaster_wall", "1k"), tile=2.0, color="#1b6f72", grime="int", macro=0.05, maps=("nor_gl", "arm"))
mat("M_paint_cafe", (PH, "painted_plaster_wall", "1k"), tile=2.0, color="#f4efe4", grime="int", macro=0.04, maps=("nor_gl", "arm"))
mat("M_ceiling_tiles", (ACG, "OfficeCeiling001", "1K"), tile=3.6, color="#f4f4f1", grime="none", macro=0.03)
mat("M_ceiling_plain", (PH, "painted_plaster_wall", "1k"), tile=2.0, color="#f4f3f0", grime="none", macro=0.03, maps=("nor_gl", "arm"))
mat("M_carpet", (ACG, "Carpet012", "1K"), tile=0.5, color="#59606c", grime="none", macro=0.05, maps=("diffg", "nor_gl", "arm"))
mat("M_carpet_amphi", (ACG, "Carpet012", "1K"), tile=0.8, color="#2a3360", grime="none", macro=0.05, maps=("diffg", "nor_gl", "arm"))
mat("M_vinyl", (PH, "floor_tiles_06", "2k"), tile=1.2, color="#d9d8d5", rough=0.6, grime="floor", macro=0.04)
mat("M_tiles_cafe", (ACG, "Tiles110", "1K"), tile=1.2, color="#f2f0ea", rough=0.45, grime="floor", macro=0.04)
mat("M_rubber_floor", (ACG, "Rubber004", "1K"), tile=1.5, color="#9a9ea6", grime="floor", macro=0.06)
mat("M_concrete_floor", (PH, "concrete_floor_02", "2k"), tile=2.0, color="#a9a8a5", grime="floor", macro=0.08)
mat("M_wood_oak", (PH, "oak_veneer_01", "1k"), tile=1.2, color="#c4ad90", rough=0.5, grime="none", macro=0.03, maps=("diffg", "nor_gl", "arm"))
mat("M_wood_floor", (PH, "wood_floor", "2k"), tile=1.7, color="#a99278", grime="floor", macro=0.04, maps=("diffg", "nor_gl", "arm"))
mat("M_wood_crate", (PH, "raw_plank_wall", "1k"), tile=1.0, color="#b89b78", grime="ext", macro=0.06, maps=("diffg", "nor_gl", "arm"))
mat("M_wood_dark", (PH, "oak_veneer_01", "1k"), tile=1.2, color="#5a3d2a", rough=0.45, grime="none", macro=0.03, maps=("diffg", "nor_gl", "arm"))
mat("M_laminate_white", None, color="#e7e4dd", rough=0.4, grime="none", macro=0.02)
mat("M_laminate_grey", None, color="#b8b6b0", rough=0.45, grime="none", macro=0.02)
mat("M_whiteboard", None, color="#f6f6f4", rough=0.12, grime="none", macro=0.0)
mat("M_cork", None, color="#b98e5c", rough=0.9, grime="none", macro=0.05)

# ------------------------------------------------------------------ soft furnishing / plastics
mat("M_fabric_navy", (ACG, "Fabric061", "1K"), tile=0.4, color="#28365f", grime="none", macro=0.03)
mat("M_fabric_mustard", (ACG, "Fabric061", "1K"), tile=0.4, color="#d09a23", grime="none", macro=0.03)
mat("M_fabric_grey", (ACG, "Fabric061", "1K"), tile=0.4, color="#5c6068", grime="none", macro=0.03)
mat("M_fabric_black", (ACG, "Fabric061", "1K"), tile=0.4, color="#2a2b2f", grime="none", macro=0.03)
mat("M_fabric_red", (ACG, "Fabric061", "1K"), tile=0.4, color="#b63a2e", grime="none", macro=0.03)
mat("M_fabric_blue", (ACG, "Fabric061", "1K"), tile=0.4, color="#2b55a8", grime="none", macro=0.03)
mat("M_fabric_lime", (ACG, "Fabric061", "1K"), tile=0.4, color="#a6d61a", grime="none", macro=0.03)
mat("M_fabric_orange", (ACG, "Fabric061", "1K"), tile=0.4, color="#e0602f", grime="none", macro=0.03)
mat("M_plastic_black", None, color="#141518", rough=0.45, grime="none", macro=0.0)
mat("M_plastic_dark", None, color="#2a2d33", rough=0.5, grime="none", macro=0.0)
mat("M_plastic_grey", None, color="#8d9198", rough=0.5, grime="none", macro=0.0)
mat("M_plastic_white", None, color="#e8e8e5", rough=0.4, grime="none", macro=0.0)
mat("M_plastic_red", None, color="#c0392b", rough=0.4, grime="none", macro=0.0)
mat("M_plastic_blue", None, color="#1d6fb8", rough=0.4, grime="none", macro=0.0)
mat("M_plastic_epita", None, color="#2e3c9f", rough=0.4, grime="none", macro=0.0)
mat("M_plastic_orange", None, color="#e85a3a", rough=0.45, grime="none", macro=0.0)
mat("M_plastic_green", None, color="#2e7d4f", rough=0.45, grime="none", macro=0.0)
mat("M_plastic_yellow", None, color="#f2c230", rough=0.45, grime="none", macro=0.0)
mat("M_rubber_black", None, color="#111214", rough=0.85, grime="none", macro=0.0)
mat("M_paper", None, color="#f1efe9", rough=0.85, grime="none", macro=0.0)

# ------------------------------------------------------------------ vehicles
mat("M_car_blue", None, color="#3d556d", rough=0.25, metal=0.6)
mat("M_car_red", None, color="#7d1f22", rough=0.25, metal=0.6)
mat("M_car_white", None, color="#d9dad6", rough=0.25, metal=0.3)
mat("M_car_green", None, color="#283a2c", rough=0.25, metal=0.6)
mat("M_car_trim", None, color="#16181b", rough=0.55)
mat("M_glass_car", None, color="#1a2230", rough=0.05, alpha=0.55)

# ------------------------------------------------------------------ glass (Godot swaps these)
mat("M_glass_clear", None, color="#cfe3ee", rough=0.04, alpha=0.18)
mat("M_glass_facade", None, color="#5d7486", rough=0.05, metal=0.2, alpha=0.55)
mat("M_glass_partition", None, color="#dbeaf2", rough=0.04, alpha=0.14)
mat("M_glass_railing", None, color="#d2e6ee", rough=0.05, alpha=0.2)
mat("M_glass_frosted", None, color="#e7eef2", rough=0.35, alpha=0.6)

# ------------------------------------------------------------------ emissive fixtures
mat("M_light_panel", None, color="#ffffff", emit=(K(4200), 5.0))
mat("M_light_warm", None, color="#ffffff", emit=(K(3000), 5.0))
mat("M_light_street", None, color="#ffffff", emit=(K(2900), 9.0))
mat("M_light_string", None, color="#ffffff", emit=(K(2400), 7.0))
mat("M_neon_pink", None, color="#ffffff", emit=("#ff4fb0", 6.0))
mat("M_neon_lime", None, color="#ffffff", emit=("#b8ff2a", 6.0))
mat("M_neon_blue", None, color="#ffffff", emit=("#3f8cff", 6.0))
mat("M_exit_green", None, color="#ffffff", emit=("#1fd36b", 3.0))
mat("M_led_red", None, color="#ffffff", emit=("#ff2a1a", 4.0))
mat("M_led_amber", None, color="#ffffff", emit=("#ffa21a", 4.0))
mat("M_led_green", None, color="#ffffff", emit=("#4cff7a", 4.0))
mat("M_tail_light", None, color="#5a0a08", emit=("#ff2a1a", 1.5))
mat("M_head_light", None, color="#d8dde2", emit=("#fff4e0", 1.2))

# ------------------------------------------------------------------ vegetation (alpha cut-outs)
mat("M_bark_plane", (PH, "bark_platanus", "1k"), tile=1.2, grime="none", macro=0.05)
mat("M_bark_birch", ("gen", "birch_bark", "1k"), tile=0.8, grime="none", macro=0.03)
mat("M_leaf_plane", (ACG, "LeafSet029", "2K"), tile=1.0, color="#c9d79a", alpha="MASK", double=True, maps=("diffa", "nor_gl", "arm"), macro=0.0)
mat("M_leaf_birch", (ACG, "LeafSet024", "2K"), tile=1.0, color="#d9e6a0", alpha="MASK", double=True, maps=("diffa", "nor_gl", "arm"), macro=0.0)
mat("M_grass", (ACG, "Foliage001", "1K"), tile=1.0, color="#c3cf8a", alpha="MASK", double=True, maps=("diffa", "nor_gl", "arm"), macro=0.0)
mat("M_leaf_palm", (ACG, "LeafSet022", "1K"), tile=1.0, color="#a9c08a", alpha="MASK", double=True, maps=("diffa", "nor_gl", "arm"), macro=0.0)
mat("M_moss", None, color="#55693a", rough=0.95)

mat("M_room_sleeve", None, color="#17191d", rough=0.9)
mat("M_room_card", None, color="#2a2f38", rough=0.6, emit=("#ffd9a0", 0.0))
# interior-mapped windows: Godot swaps these for scripts/fx/interior.gdshader (Interiors.material_for); in Blender
# they are only a dark glass stand-in. Panes come from campus_arch.interior_quad().
for _k in ("office", "flat", "flat_tall", "flat_lean", "hotel"):
    mat("M_window_" + _k, None, color="#1c2127", rough=0.08)
mat("M_signal_blue", None, color="#1f3b73", rough=0.5)
mat("M_signal_white", None, color="#f2f2ef", rough=0.5)
mat("M_epita_blue", None, color="#2e3c9f", rough=0.45)
mat("M_epita_navy", None, color="#1a2340", rough=0.5)
mat("M_epita_lime", None, color="#bcfb0b", rough=0.45)
mat("M_logo_1", None, color="#003048", rough=0.4)
mat("M_logo_2", None, color="#005070", rough=0.4)
mat("M_logo_3", None, color="#0070a0", rough=0.4)
mat("M_logo_4", None, color="#0088c0", rough=0.4)

# generated-image materials are registered at runtime by campus_gen (signs, posters, screens...)


# ------------------------------------------------------------------ Blender node trees
_gltf_group = None


def gltf_output_group():
    global _gltf_group
    g = bpy.data.node_groups.get("glTF Material Output")
    if g is None:
        g = bpy.data.node_groups.new("glTF Material Output", "ShaderNodeTree")
        s = g.interface.new_socket("Occlusion", in_out="INPUT", socket_type="NodeSocketFloat")
        s.default_value = 1.0
        g.interface.new_socket("Thickness", in_out="INPUT", socket_type="NodeSocketFloat")
        g.nodes.new("NodeGroupInput")
    return g


def tex_paths(spec):
    src, tid, res = spec["tex"]
    if src == PH:
        return T.polyhaven(tid, res, maps=tuple(m for m in spec["maps"] if m != "diffa"))
    if src == ACG:
        return T.ambientcg(tid, res, alpha="diffa" in spec["maps"], gray="diffg" in spec["maps"])
    if src == "gen":
        folder = os.path.join(T.TEX_DIR, "campus_gen")
        return {m: os.path.join(folder, f"{tid}_{m}_{res}.{'png' if m == 'diffa' else 'jpg'}") for m in spec["maps"]}
    raise ValueError(src)


_img_cache = {}


def load_image(path, noncolor):
    key = (path, noncolor)
    if key in _img_cache:
        return _img_cache[key]
    im = bpy.data.images.load(path, check_existing=True)
    im.colorspace_settings.name = "Non-Color" if noncolor else "sRGB"
    if path.lower().endswith(".png"):
        im.alpha_mode = "STRAIGHT"
    _img_cache[key] = im
    return im


def get(name):
    """Blender material for a registered spec (created on first use)."""
    m = bpy.data.materials.get(name)
    if m is not None:
        return m
    spec = M[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.use_backface_culling = not spec["double"]
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    b = N["Principled BSDF"]
    out = N["Material Output"]
    b.location, out.location = (300, 0), (600, 0)
    col_lin = srgb(spec["color"]) + (1.0,)
    paths = tex_paths(spec) if spec["tex"] else {}
    vc = N.new("ShaderNodeVertexColor")
    vc.layer_name = "Col"
    vc.location = (-300, -150)
    base = None
    if "diffg" in spec["maps"]:
        paths = dict(paths)
        paths.pop("diff", None)
    if "diff" in paths or "diffa" in paths or "diffg" in paths:
        p = paths.get("diffa") or paths.get("diffg") or paths.get("diff")
        t = N.new("ShaderNodeTexImage")
        t.image = load_image(p, False)
        t.location = (-700, 200)
        base = t.outputs["Color"]
        if spec["alpha"] == "MASK":
            g = N.new("ShaderNodeMath")
            g.operation = "GREATER_THAN"
            g.inputs[1].default_value = spec["alpha_cut"]
            L.new(t.outputs["Alpha"], g.inputs[0])
            L.new(g.outputs[0], b.inputs["Alpha"])
        if spec["color"].lower() != "#ffffff":
            mx = N.new("ShaderNodeMix")
            mx.data_type, mx.blend_type = "RGBA", "MULTIPLY"
            mx.inputs[0].default_value = 1.0
            L.new(base, mx.inputs[6])
            mx.inputs[7].default_value = col_lin
            mx.location = (-350, 200)
            base = mx.outputs[2]
    mx = N.new("ShaderNodeMix")
    mx.data_type, mx.blend_type = "RGBA", "MULTIPLY"
    mx.inputs[0].default_value = 1.0
    mx.location = (-100, 100)
    if base is not None:
        L.new(base, mx.inputs[6])
    else:
        mx.inputs[6].default_value = col_lin
    L.new(vc.outputs["Color"], mx.inputs[7])
    L.new(mx.outputs[2], b.inputs["Base Color"])
    if "nor_gl" in paths:
        t = N.new("ShaderNodeTexImage")
        t.image = load_image(paths["nor_gl"], True)
        t.location = (-700, -350)
        nm = N.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = spec["normal"]
        nm.location = (-350, -350)
        L.new(t.outputs["Color"], nm.inputs["Color"])
        L.new(nm.outputs["Normal"], b.inputs["Normal"])
    if "arm" in paths and spec["rough_tex"]:
        t = N.new("ShaderNodeTexImage")
        t.image = load_image(paths["arm"], True)
        t.location = (-900, -100)
        sp = N.new("ShaderNodeSeparateColor")
        sp.location = (-600, -100)
        L.new(t.outputs["Color"], sp.inputs[0])
        r = sp.outputs["Green"]
        if spec["rough"] is not None:
            mu = N.new("ShaderNodeMath")
            mu.operation = "MULTIPLY"
            mu.inputs[1].default_value = spec["rough"] / 0.7
            L.new(r, mu.inputs[0])
            r = mu.outputs[0]
        L.new(r, b.inputs["Roughness"])
        if spec["metal"] > 0:
            mu = N.new("ShaderNodeMath")
            mu.operation = "MULTIPLY"
            mu.inputs[1].default_value = 1.0
            mu.inputs[0].default_value = spec["metal"]
            b.inputs["Metallic"].default_value = spec["metal"]
        go = N.new("ShaderNodeGroup")
        go.node_tree = gltf_output_group()
        go.location = (300, -400)
        L.new(sp.outputs["Red"], go.inputs["Occlusion"])
    else:
        b.inputs["Roughness"].default_value = spec["rough"] if spec["rough"] is not None else 0.6
        b.inputs["Metallic"].default_value = spec["metal"]
    if spec["metal"] and "arm" in paths:
        b.inputs["Metallic"].default_value = spec["metal"]
    if spec["emit"]:
        ec, es = spec["emit"]
        b.inputs["Emission Color"].default_value = srgb(ec) + (1.0,)
        b.inputs["Emission Strength"].default_value = es
        if spec["color"].lower() == "#ffffff" and not paths:
            mx.inputs[6].default_value = (0.8, 0.8, 0.8, 1.0)
    a = spec["alpha"]
    if isinstance(a, float):
        b.inputs["Alpha"].default_value = a
        m.surface_render_method = "BLENDED"
        try:
            m.use_transparency_overlap = False
        except Exception:
            pass
    elif a == "MASK":
        m.surface_render_method = "DITHERED"
    return m


def tile_of(name):
    return M[name]["tile"]


def register_image_material(name, img_path, emit=0.0, rough=0.6, alpha=None, double=False, color="#ffffff", grime="none"):
    """material for a generated texture (sign, poster, screen...): UVs are set explicitly by the caller"""
    M[name] = dict(name=name, tex=("img", img_path, ""), tile=1.0, color=color, rough=rough, metal=0.0, normal=1.0,
                   emit=None, alpha=alpha, double=double, grime=grime, macro=0.0, maps=("diff",), rough_tex=False,
                   alpha_cut=0.5, img=img_path, img_emit=emit)


def get_image_material(name):
    m = bpy.data.materials.get(name)
    if m is not None:
        return m
    spec = M[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.use_backface_culling = not spec["double"]
    N, L = m.node_tree.nodes, m.node_tree.links
    b = N["Principled BSDF"]
    t = N.new("ShaderNodeTexImage")
    t.image = load_image(spec["img"], False)
    vc = N.new("ShaderNodeVertexColor")
    vc.layer_name = "Col"
    mx = N.new("ShaderNodeMix")
    mx.data_type, mx.blend_type = "RGBA", "MULTIPLY"
    mx.inputs[0].default_value = 1.0
    L.new(t.outputs["Color"], mx.inputs[6])
    L.new(vc.outputs["Color"], mx.inputs[7])
    L.new(mx.outputs[2], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = spec["rough"]
    if spec["img_emit"] > 0:
        L.new(t.outputs["Color"], b.inputs["Emission Color"])
        b.inputs["Emission Strength"].default_value = spec["img_emit"]
    if spec["alpha"] == "MASK":
        g = N.new("ShaderNodeMath")
        g.operation = "GREATER_THAN"
        g.inputs[1].default_value = 0.5
        L.new(t.outputs["Alpha"], g.inputs[0])
        L.new(g.outputs[0], b.inputs["Alpha"])
        m.surface_render_method = "DITHERED"
    return m


def material(name):
    spec = M[name]
    if spec["tex"] and spec["tex"][0] == "img":
        return get_image_material(name)
    return get(name)
