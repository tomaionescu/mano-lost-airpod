class_name LevelBinder
extends RefCounted
## Reads the gameplay markers exported from Blender (see docs/PIPELINE.md) and builds the runtime
## pieces: lights, prop instances, decals, glass, reflection probes; returns positions for gameplay.
## Also sorts lamps and lit windows into the groups WorldEnv.apply_time() dims (WorldEnv.bind_level()), and adds
## the movement of docs/DESIGN.md §4.8: foliage swaying in the breeze, October leaves falling from the trees, and dust and
## a fog volume where the low sun comes into a room (none of it with the dev switch lens=v1).

var spawn := Transform3D(Basis(), Vector3(18.75, -0.75, 14.0))
var npcs: Dictionary = {}        # id -> {pos, yaw, extras}
var spots: Dictionary = {}       # id -> {pos, label, range}
var anchors: Dictionary = {}     # id -> {pos, yaw, extras}
var ducks: Array = []            # [{id, pos}]
var zones: Array = []            # [{id, aabb, label, sub, surface}]
var paths: Dictionary = {}       # name -> Array[Vector3]
var path_extras: Dictionary = {} # name -> extras of its first point (model, loop, speed)
var portals: Dictionary = {}     # "a|b" -> Array[Vector3]
var cams: Dictionary = {}        # name -> Transform3D
var props: Array = []            # [{asset, node}] instanced PROP_ markers
var light_count := 0
var lamps: Dictionary = {}       # lamp group -> Array[Light3D]; each light keeps meta "base_energy"
var lamp_materials: Dictionary = {}  # lamp group -> Array[BaseMaterial3D] whose glow follows the group
var window_materials: Array = [] # the room cards behind the windows: lit after sunset

## Physics layer that only camera queries look at: furniture volumes (monitors, chair backs)
## that have no player collision but must not end up between the lens and a face.
const CAMERA_OCCLUDERS := 16

## LIGHT_ name prefix -> lamp group that WorldEnv.apply_time() dims; a `group` extra on the marker wins.
## Lights in no group (signs, neon, entrances, amphi, cafeteria, the Under) stay as exported all evening.
const LAMP_GROUPS := {"street_": "street_lamps", "rue_voltaire_": "street_lamps", "court_": "string_lights",
	"sm_": "classroom", "f1_": "classroom", "lobby_0": "classroom", "lobby_1": "classroom", "stairwell": "classroom"}
## Group colours (docs/DESIGN.md §4.4): string lights about 2200 K, street lamps 3000 K, classroom panels 4500 K,
## so it is warm outside and cool inside at 17:42, and the other way round after sunset.
const LAMP_COLORS := {"street_lamps": Color(1.0, 0.80, 0.62), "string_lights": Color(1.0, 0.64, 0.36),
	"classroom": Color(0.94, 0.98, 0.92)}
## Emissive materials that glow with a lamp group: the street-lamp heads and the string-light bulbs.
const LAMP_MATERIALS := {"M_light_street": "street_lamps", "M_light_string": "string_lights"}
## Foliage that moves in the breeze (scripts/fx/foliage.gdshader), by imported material name: [anchor, metres of
## sway, cycles per second]. Anchor 0: leaf cards of a crown or a bush, moving more the higher they sit above the
## plant's foot; 1: grass cards bending from the root. Plants indoors (INTERIORS) keep their imported material.
const FOLIAGE := {"M_leaves_plane": [0, 0.03, 0.8], "M_leaves_birch": [0, 0.035, 1.1], "M_grass": [1, 0.025, 1.2]}
## Tree props that drop October leaves (FallingLeaves); true: the birch's small yellow ones.
const LEAF_TREES := {"tree_plane": false, "planter_birch": true}
## Zones that are indoors, as for WorldEnv.set_interior() in main.gd: no wind there.
const INTERIORS := ["amphi", "volt_gf", "volt_f1", "sm14", "sm15", "cafe", "under"]
## Rooms the low sun comes into at golden hour (Amphi 4 over its west wall, the lobby through the street doors):
## [FogVolume density (0: none), dust motes per m³]; see scripts/fx/sun_room.gd. docs/DESIGN.md §4.8 asks for about 0.03, but the
## sun fills half of the amphi at once (no narrow window to make a beam) and 0.03 turns it to fog; 0.01 reads as
## warm, dusty air. The room's lamps keep their fog light low, or the volume would glow round every lamp. Motes
## only show within a few metres of the lens and only in the sun, so the room needs about one per m³ to keep a few
## in a shot.
const SUN_ROOMS := {"amphi": [0.01, 1.2], "volt_gf": [0.0, 0.3]}
const SUN_ROOM := preload("res://scripts/fx/sun_room.gd")

var foliage_count := 0               # surfaces swapped to the swaying material
var falling_leaves: FallingLeaves    # null without tree props or with lens=v1
var sun_fx: Array = []               # fog volumes and dust that WorldEnv shows only while the sun is up

var _glass: StandardMaterial3D
var _shadow_lights := 0
var _foliage: Dictionary = {}        # "<material id>|<sway base>" -> swaying ShaderMaterial
var _crowns: Dictionary = {}         # tree mesh -> AABB of its leaves (mesh space)


func bind(root: Node3D, max_shadow_lights := 14) -> void:
	_glass = StandardMaterial3D.new()
	_glass.albedo_color = Color(0.62, 0.72, 0.78, 0.14)
	_glass.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	_glass.roughness = 0.04
	_glass.metallic_specular = 1.0
	_glass.cull_mode = BaseMaterial3D.CULL_DISABLED
	var path_pts := {}
	var portal_pts := {}
	var markers: Array = []
	_collect(root, markers)
	for n in markers:
		var nm := String(n.name)
		var xf: Transform3D = n.global_transform
		var ex: Dictionary = n.get_meta("extras", {}) if n.has_meta("extras") else {}
		var yaw := _yaw_of(xf)
		if nm == "SPAWN_player":
			spawn = Transform3D(Basis(Vector3.UP, yaw), xf.origin)
		elif nm.begins_with("NPC_"):
			npcs[nm.substr(4)] = {"pos": xf.origin, "yaw": yaw, "extras": ex}
		elif nm.begins_with("SPOT_"):
			spots[nm.substr(5)] = {"pos": xf.origin, "label": ex.get("label", nm.substr(5).capitalize()), "range": float(ex.get("range", 1.8))}
		elif nm.begins_with("ANCHOR_"):
			anchors[nm.substr(7)] = {"pos": xf.origin, "yaw": yaw, "extras": ex, "xform": xf}
		elif nm.begins_with("DUCK_"):
			ducks.append({"id": nm.substr(5), "pos": xf.origin})
		elif nm.begins_with("ZONE_"):
			var half := xf.basis.get_scale().abs()
			# rotated boxes are fine: points are tested in the zone's own (unit-cube) space
			zones.append({"id": nm.substr(5).get_slice(".", 0), "xform_inv": xf.affine_inverse(), "volume": half.x * half.y * half.z * 8.0,
				"priority": int(ex.get("priority", 0)), "center": xf.origin,
				"label": ex.get("label", ""), "sub": ex.get("sub", ""), "surface": ex.get("surface", "concrete")})
		elif nm.begins_with("PATH_"):
			var parts := nm.substr(5).rsplit("_", true, 1)
			var key := parts[0]
			if not path_pts.has(key):
				path_pts[key] = []
			path_pts[key].append([int(parts[1]) if parts.size() > 1 else 0, xf.origin])
			if not path_extras.has(key) and not ex.is_empty():
				path_extras[key] = ex
		elif nm.begins_with("PORTAL_"):
			var body := nm.substr(7)
			var key := body.rsplit("_", true, 1)[0].replace("__", "|")
			if not portal_pts.has(key):
				portal_pts[key] = []
			portal_pts[key].append([int(body.rsplit("_", true, 1)[1]) if "_" in body else 0, xf.origin])
		elif nm.begins_with("LIGHT_"):
			_make_light(n, xf, ex, max_shadow_lights)
		elif nm.begins_with("PROP_"):
			_make_prop(n, nm.substr(5).get_slice("__", 0), xf)
		elif nm.begins_with("DECAL_"):
			_make_decal(n, nm.substr(6).get_slice("__", 0), xf)
		elif nm.begins_with("CAM_"):
			cams[nm.substr(4)] = xf
	for k in path_pts:
		var arr: Array = path_pts[k]
		arr.sort_custom(func(a, b): return a[0] < b[0])
		paths[k] = arr.map(func(e): return e[1])
	for k in portal_pts:
		var arr: Array = portal_pts[k]
		arr.sort_custom(func(a, b): return a[0] < b[0])
		portals[k] = arr.map(func(e): return e[1])
	_fix_materials(root)
	if not WorldEnv.lens_v1():
		_make_leaves(root)
		_make_sun_rooms(root)


func _collect(n: Node, out: Array) -> void:
	var nm := String(n.name)
	for p in ["SPAWN_", "NPC_", "SPOT_", "ANCHOR_", "DUCK_", "ZONE_", "PATH_", "PORTAL_", "LIGHT_", "PROP_", "DECAL_", "CAM_"]:
		if nm.begins_with(p) and n is Node3D:
			out.append(n)
			break
	for c in n.get_children():
		_collect(c, out)


static func _yaw_of(xf: Transform3D) -> float:
	var f := xf.basis.z
	return atan2(f.x, f.z)


func _make_light(n: Node3D, xf: Transform3D, ex: Dictionary, max_shadow: int) -> void:
	var type: String = ex.get("type", "omni")
	var l: Light3D
	if type == "spot":
		var s := SpotLight3D.new()
		s.spot_range = float(ex.get("range", 8.0))
		s.spot_angle = float(ex.get("angle", 50.0))
		s.spot_angle_attenuation = 0.8
		l = s
	else:
		var o := OmniLight3D.new()
		o.omni_range = float(ex.get("range", 8.0))
		o.omni_attenuation = 1.4
		l = o
	l.light_bake_mode = Light3D.BAKE_STATIC   # fixtures never move
	l.light_color = Color(ex.get("color", "#ffe6c8"))
	l.light_energy = float(ex.get("energy", 1.5))
	var group: String = ex.get("group", lamp_group(String(n.name).substr(6)))
	if group != "":
		l.light_color = LAMP_COLORS.get(group, l.light_color)
		l.set_meta("base_energy", l.light_energy)
		if not lamps.has(group):
			lamps[group] = []
		lamps[group].append(l)
	l.light_volumetric_fog_energy = 0.6
	l.light_specular = 0.6
	var shadow: bool = bool(ex.get("shadow", false)) and _shadow_lights < max_shadow
	l.shadow_enabled = shadow
	if shadow:
		_shadow_lights += 1
		l.shadow_blur = 1.5
	# fade out far lights so dozens of fixtures stay cheap
	l.distance_fade_enabled = true
	l.distance_fade_begin = 28.0
	l.distance_fade_length = 10.0
	l.distance_fade_shadow = 18.0
	n.add_child(l)
	light_count += 1


## Lamp group of a LIGHT_ marker from its name (without "LIGHT_"), or "" if it is not dimmed.
static func lamp_group(light_name: String) -> String:
	for p in LAMP_GROUPS:
		if light_name.begins_with(p):
			return LAMP_GROUPS[p]
	return ""


func _make_prop(n: Node3D, asset: String, _xf: Transform3D) -> void:
	var path := "res://assets/props/%s.glb" % asset
	if not ResourceLoader.exists(path):
		return
	var inst: Node3D = (load(path) as PackedScene).instantiate()
	n.add_child(inst)
	var ex: Dictionary = n.get_meta("extras", {}) if n.has_meta("extras") else {}
	if not bool(ex.get("shadow", true)):
		# backdrop props beyond the playable streets (campus_backdrop): kept out of the shadow passes
		for mi in inst.find_children("*", "MeshInstance3D", true, false):
			(mi as MeshInstance3D).cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	props.append({"asset": asset, "node": n})
	_add_camera_occluder(inst)


func _add_camera_occluder(inst: Node3D) -> void:
	var box := AABB()
	var first := true
	for mi in inst.find_children("*", "MeshInstance3D", true, false):
		var xf := Transform3D()
		var p: Node = mi
		while p != inst and p != null:
			if p is Node3D:
				xf = (p as Node3D).transform * xf
			p = p.get_parent()
		var a: AABB = xf * (mi as MeshInstance3D).get_aabb()
		box = a if first else box.merge(a)
		first = false
	# furniture-sized only: trees, lamps and cars would swallow whole conversation spaces
	if first or box.size.y > 2.5 or maxf(box.size.x, box.size.z) > 3.0:
		return
	var body := StaticBody3D.new()
	body.collision_layer = CAMERA_OCCLUDERS
	body.collision_mask = 0
	var cs := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = box.size + Vector3(0, 0.12, 0)   # a little headroom: a lens grazing a monitor top still loses the face
	cs.shape = shape
	cs.position = box.get_center() + Vector3(0, 0.06, 0)
	body.add_child(cs)
	inst.add_child(body)


func _make_decal(n: Node3D, tex: String, _xf: Transform3D) -> void:
	var path := "res://assets/decals/%s.png" % tex
	if not ResourceLoader.exists(path):
		return
	var d := Decal.new()
	d.texture_albedo = load(path)
	d.size = Vector3(2, 2, 2)   # the marker's scale carries the real size
	d.upper_fade = 0.2
	d.lower_fade = 0.2
	d.cull_mask = 1
	n.add_child(d)


func _fix_materials(n: Node) -> void:
	if n is MeshInstance3D:
		var mi := n as MeshInstance3D
		if mi.mesh:
			for s in mi.mesh.get_surface_count():
				var m := mi.mesh.surface_get_material(s)
				if m and "glass" in String(m.resource_name).to_lower():
					mi.set_surface_override_material(s, _glass)
					mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
				elif m and String(m.resource_name).begins_with("M_window_"):
					# interior-mapped windows: one ShaderMaterial per kind, lit after sunset with the room cards
					var im := Interiors.material_for(String(m.resource_name))
					mi.set_surface_override_material(s, im)
					if not window_materials.has(im):
						window_materials.append(im)
				elif m is BaseMaterial3D and FOLIAGE.has(String(m.resource_name)) and not WorldEnv.lens_v1():
					var sway := _foliage_material(mi, s, m as BaseMaterial3D)
					if sway:
						mi.set_surface_override_material(s, sway)
						foliage_count += 1
				elif m is BaseMaterial3D:
					_sort_glow(m as BaseMaterial3D)
	for c in n.get_children():
		_fix_materials(c)


## The swaying copy of an imported foliage material for one surface, or null indoors. A plant prop sways from its
## origin (its foot); a level mesh holding many bushes from the bottom of the surface.
func _foliage_material(mi: MeshInstance3D, s: int, m: BaseMaterial3D) -> ShaderMaterial:
	var spec: Array = FOLIAGE[String(m.resource_name)]
	var verts: PackedVector3Array = mi.mesh.surface_get_arrays(s)[Mesh.ARRAY_VERTEX]
	if verts.is_empty():
		return null
	var lo := Vector3(INF, INF, INF)
	var hi := -lo
	for v in verts:
		lo = lo.min(v)
		hi = hi.max(v)
	if INTERIORS.has(zone_at(mi.global_transform * ((lo + hi) * 0.5)).get("id", "")):
		return null
	var in_prop := false
	var p := mi.get_parent()
	while p != null and not in_prop:
		in_prop = String(p.name).begins_with("PROP_")
		p = p.get_parent()
	var base := 0.0 if in_prop else snappedf(lo.y, 0.1)
	var key := "%d|%.1f" % [m.get_instance_id(), base]
	if _foliage.has(key):
		return _foliage[key]
	var sm := ShaderMaterial.new()
	sm.shader = preload("res://scripts/fx/foliage.gdshader")
	sm.resource_name = String(m.resource_name) + "_sway"
	sm.set_shader_parameter("albedo", m.albedo_color)
	sm.set_shader_parameter("albedo_tex", m.albedo_texture)
	sm.set_shader_parameter("vertex_color", m.vertex_color_use_as_albedo)
	sm.set_shader_parameter("use_normal_map", m.normal_enabled and m.normal_texture != null)
	sm.set_shader_parameter("normal_tex", m.normal_texture)
	sm.set_shader_parameter("normal_scale", m.normal_scale)
	# the Poly Haven / ambientCG ARM map: occlusion, roughness and metal in r, g, b
	sm.set_shader_parameter("use_arm_map", m.roughness_texture != null)
	sm.set_shader_parameter("arm_tex", m.roughness_texture)
	sm.set_shader_parameter("roughness", m.roughness)
	sm.set_shader_parameter("metallic", m.metallic)
	sm.set_shader_parameter("specular", m.metallic_specular)
	sm.set_shader_parameter("alpha_scissor", m.alpha_scissor_threshold)
	sm.set_shader_parameter("uv1_scale", m.uv1_scale)
	sm.set_shader_parameter("uv1_offset", m.uv1_offset)
	sm.set_shader_parameter("anchor", spec[0])
	sm.set_shader_parameter("sway_amp", spec[1])
	sm.set_shader_parameter("sway_hz", spec[2])
	sm.set_shader_parameter("sway_base", base)
	_foliage[key] = sm
	return sm


## One particle system for the leaves of every tree prop, each crown taken from its leaf cards.
func _make_leaves(root: Node3D) -> void:
	var crowns: Array = []
	for e in props:
		if not LEAF_TREES.has(e.asset):
			continue
		var marker: Node3D = e.node
		for mi: MeshInstance3D in marker.find_children("*", "MeshInstance3D", true, false):
			var box := _crown_of(mi.mesh)
			if box.size == Vector3.ZERO:
				continue
			var w: AABB = mi.global_transform * box
			crowns.append({"centre": w.get_center(), "radius": maxf(w.size.x, w.size.z) * 0.45,
				"ground": marker.global_position.y, "birch": LEAF_TREES[e.asset]})
	if crowns.is_empty():
		return
	# FallingLeaves takes the first MAX_CROWNS: keep the trees nearest the middle of the campus
	crowns.sort_custom(func(a, b): return (a.centre as Vector3).length_squared() < (b.centre as Vector3).length_squared())
	falling_leaves = FallingLeaves.new(crowns)
	falling_leaves.name = "FallingLeaves"
	root.add_child(falling_leaves)


## Mesh-space bounds of a tree's leaf cards (the M_leaves_* surfaces), zero if it has none.
func _crown_of(mesh: Mesh) -> AABB:
	if mesh == null:
		return AABB()
	if _crowns.has(mesh):
		return _crowns[mesh]
	var box := AABB()
	var first := true
	for s in mesh.get_surface_count():
		var m := mesh.surface_get_material(s)
		if m == null or not String(m.resource_name).begins_with("M_leaves"):
			continue
		for v in (mesh.surface_get_arrays(s)[Mesh.ARRAY_VERTEX] as PackedVector3Array):
			if first:
				box = AABB(v, Vector3.ZERO)
				first = false
			else:
				box = box.expand(v)
	_crowns[mesh] = box
	return box


func _make_sun_rooms(root: Node3D) -> void:
	for z in zones:
		if not SUN_ROOMS.has(z.id):
			continue
		var xf: Transform3D = (z.xform_inv as Transform3D).affine_inverse()
		var half := xf.basis.get_scale().abs()
		var spec: Array = SUN_ROOMS[z.id]
		var room: Node3D = SUN_ROOM.new(AABB(xf.origin - half, half * 2.0), spec[0], spec[1])
		room.name = "SunRoom_" + String(z.id)
		root.add_child(room)
		sun_fx.append(room)
		if spec[0] > 0.0:
			# the room's own lamps keep a little fog light, so the volume shows the sun and not a glow round every lamp
			for l: Light3D in root.find_children("*", "Light3D", true, false):
				var q: Vector3 = z.xform_inv * l.global_position
				if absf(q.x) <= 1.0 and absf(q.z) <= 1.0:
					l.light_volumetric_fog_energy = 0.15


## Lamp bulbs and room cards are shared imported materials (one per glb), so each is listed once and
## dimmed in place; "base_emission" keeps the exported strength.
func _sort_glow(m: BaseMaterial3D) -> void:
	var nm := String(m.resource_name)
	var list: Array
	if LAMP_MATERIALS.has(nm):
		if not lamp_materials.has(LAMP_MATERIALS[nm]):
			lamp_materials[LAMP_MATERIALS[nm]] = []
		list = lamp_materials[LAMP_MATERIALS[nm]]
	elif nm == "M_room_card" or nm.begins_with("M_window"):
		list = window_materials
	else:
		return
	if not list.has(m):
		m.set_meta("base_emission", m.emission_energy_multiplier)
		list.append(m)


# ------------------------------------------------------------------ queries
## The instanced prop of `asset` nearest to `p` (horizontally), within `radius`; null if none.
func nearest_prop(asset: String, p: Vector3, radius: float) -> Node3D:
	var best: Node3D = null
	var best_d := radius
	for e in props:
		if e.asset != asset:
			continue
		var q: Vector3 = (e.node as Node3D).global_position - p
		q.y = 0
		if q.length() < best_d:
			best_d = q.length()
			best = e.node
	return best


func zone_at(p: Vector3) -> Dictionary:
	var best := {}
	var best_key := [-INF, INF]   # higher priority first, then the smaller volume
	for z in zones:
		var l: Vector3 = z.xform_inv * p
		if absf(l.x) <= 1.02 and absf(l.y) <= 1.02 and absf(l.z) <= 1.02:
			if z.priority > best_key[0] or (z.priority == best_key[0] and z.volume < best_key[1]):
				best_key = [z.priority, z.volume]
				best = z
	return best
