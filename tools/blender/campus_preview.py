"""Eevee check renders of the built campus (tools/out/campus_<view>.png).
Adds a golden-hour sun + sky, Blender lights for every LIGHT_ marker and prop instances at PROP_ markers,
then renders a fixed set of viewpoints. Nothing here is exported."""
import bpy, os, math
from mathutils import Vector
from campus_geo import P
from campus_layout import *

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ROOT, "tools", "out")

SUN_AZ = math.radians(235.0)    # direction the sun shines FROM, measured from north (-Z game) towards east
SUN_EL = math.radians(17.0)

VIEWS = {
    "street": ((-15.5, 1.7, 1.6), (6.0, 3.2, -1.2), 60),
    "street_east": ((24.0, 1.7, -2.2), (2.0, 2.6, 2.0), 62),
    "lobby": ((8.4, 1.65, -6.4), (-6.0, 1.2, -19.0), 70),
    "sm14": ((-4.8, F1 + 1.6, -16.8), (-14.0, F1 + 0.8, -23.5), 68),
    "courtyard": ((2.0, 1.7, 17.0), (15.0, 1.8, 31.0), 66),
    "amphi": ((16.2, 1.65, 17.6), (19.0, -1.6, 7.0), 72),
    "cafeteria": (None, None, 70),
    "under": ((25.4, UY + 1.7, 41.2), (9.0, UY + 0.9, 49.0), 72),
    "aerial": ((58.0, 62.0, 72.0), (2.0, 0.0, 8.0), 40),
    "title": ((25.0, 7.0, 37.0), (3.0, 3.0, 20.0), 55),
}


def _cafe_view():
    a = cafe_pt(8.0, 1.2)
    b = cafe_pt(13.0, 7.0)
    return (a[0], 1.65, a[1]), (b[0], 1.0, b[1])


def setup_world(scene):
    w = bpy.data.worlds.new("preview_world")
    scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes["Background"]
    sky = nt.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    sky.sun_elevation = SUN_EL
    sky.sun_rotation = SUN_AZ
    sky.altitude = 50.0
    sky.air_density = 1.4
    sky.dust_density = 2.5
    sky.sun_intensity = 0.4
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 0.22
    sun = bpy.data.lights.new("preview_sun", "SUN")
    sun.energy = 3.2
    sun.color = (1.0, 0.78, 0.55)
    sun.angle = math.radians(1.2)
    so = bpy.data.objects.new("preview_sun", sun)
    scene.collection.objects.link(so)
    # sun direction: from azimuth (0 = north = -Z game = +Y blender) rotated towards east (+X)
    d_from = Vector((math.sin(SUN_AZ) * math.cos(SUN_EL), math.cos(SUN_AZ) * math.cos(SUN_EL), math.sin(SUN_EL)))
    so.rotation_euler = (-d_from).to_track_quat("-Z", "Y").to_euler()


def hexcol(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple((x / 12.92) if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def add_marker_lights(scene):
    n = 0
    for ob in list(scene.objects):
        if not ob.name.startswith("LIGHT_"):
            continue
        kind = ob.get("type", "omni")
        energy = float(ob.get("energy", 1.0))
        rng = float(ob.get("range", 8.0))
        if kind == "spot":
            L = bpy.data.lights.new(ob.name + "_bl", "SPOT")
            L.spot_size = math.radians(float(ob.get("angle", 45.0)) * 2)
            L.energy = energy * 260
        else:
            L = bpy.data.lights.new(ob.name + "_bl", "POINT")
            L.energy = energy * 28 * rng
            L.shadow_soft_size = 0.15
        L.color = hexcol(ob.get("color", "#ffffff"))
        L.use_shadow = bool(ob.get("shadow", False))
        L.use_custom_distance = True
        L.cutoff_distance = rng * 1.3
        lo = bpy.data.objects.new(ob.name + "_bl", L)
        scene.collection.objects.link(lo)
        lo.matrix_world = ob.matrix_world.copy()
        if kind == "spot":
            # marker local +Y (blender) == glTF -Z == light direction; blender spot shines along local -Z
            lo.rotation_euler = (ob.matrix_world.to_3x3() @ Vector((0, 1, 0))).to_track_quat("-Z", "Y").to_euler()
        n += 1
    return n


def add_prop_instances(scene):
    """collection-instance every PROP_ marker with the prop library collection of the same asset"""
    lib = {c.name[5:]: c for c in bpy.data.collections if c.name.startswith("PROP_")}
    n = 0
    for ob in list(scene.objects):
        if not ob.name.startswith("PROP_") or ob.type != "EMPTY":
            continue
        asset = ob.name[5:].split("__")[0]
        c = lib.get(asset)
        if c is None:
            continue
        inst = bpy.data.objects.new(ob.name + "_inst", None)
        inst.instance_type = "COLLECTION"
        inst.instance_collection = c
        inst.matrix_world = ob.matrix_world.copy()
        scene.collection.objects.link(inst)
        n += 1
    return n


def camera(scene, frm, look, fov):
    cam = bpy.data.cameras.new("preview_cam")
    cam.sensor_fit = "HORIZONTAL"
    cam.angle = math.radians(fov)
    cam.clip_start = 0.05
    cam.clip_end = 500
    ob = bpy.data.objects.new("preview_cam", cam)
    scene.collection.objects.link(ob)
    ob.location = P(*frm)
    d = Vector(P(*look)) - Vector(P(*frm))
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    scene.camera = ob
    return ob


def render_all(fast=False, log=print, views=None):
    scene = bpy.data.scenes["campus"]
    bpy.context.window_manager  # noqa
    setup_world(scene)
    nl = add_marker_lights(scene)
    npr = add_prop_instances(scene)
    log(f"preview: {nl} lights, {npr} prop instances")
    r = scene.render
    r.engine = "BLENDER_EEVEE_NEXT"
    r.resolution_x, r.resolution_y = (1280, 720)
    r.resolution_percentage = 100
    scene.eevee.taa_render_samples = 16 if fast else 48
    try:
        scene.eevee.shadow_pool_size = "1024"
    except Exception:
        pass
    try:
        scene.eevee.use_shadows = True
        scene.eevee.use_raytracing = True
        scene.eevee.ray_tracing_options.resolution_scale = "2"
        scene.eevee.use_fast_gi = True
    except Exception:
        pass
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = 0.0
    # hide colliders / markers in renders
    for ob in scene.objects:
        if ob.name.endswith("-colonly") or ob.type == "EMPTY" and not ob.instance_collection:
            ob.hide_render = True
    for name, (frm, look, fov) in VIEWS.items():
        if views and name not in views:
            continue
        if name == "cafeteria":
            frm, look = _cafe_view()
        cam = camera(scene, frm, look, fov)
        r.filepath = os.path.join(OUT, f"campus_{name}.png")
        bpy.ops.render.render(write_still=True, scene=scene.name)
        log("rendered", name)
        bpy.data.objects.remove(cam)
