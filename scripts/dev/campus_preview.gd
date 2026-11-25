extends Node3D
## Dev check for the campus level: loads res://assets/levels/campus.glb, adds a TEMPORARY golden-hour rig
## (WorldEnvironment + DirectionalLight3D - the real lighting rig lives elsewhere), turns LIGHT_ markers into
## Omni/SpotLight3D, instances PROP_ markers, probes collision under gameplay markers and saves screenshots
## to res://shots/campus_<view>.png, then quits.
## Run windowed:  Godot --path <project> --position 40,40 res://scenes/dev/campus_preview.tscn
## Extra args after `--`:  --views=street,lobby   --no-quit   --frames=N

const LEVEL := "res://assets/levels/campus.glb"
const PROPS_DIR := "res://assets/props/"
const SUN_AZ_DEG := 235.0   # direction the sun comes FROM, measured from north (-Z) towards east (+X)
const SUN_EL_DEG := 17.0

# same viewpoints as tools/blender/campus_preview.py (game space == Godot space)
var VIEWS := {
	"street": [Vector3(-15.5, 1.7, 1.6), Vector3(6.0, 3.2, -1.2), 60.0],
	"street_east": [Vector3(24.0, 1.7, -2.2), Vector3(2.0, 2.6, 2.0), 62.0],
	"lobby": [Vector3(8.4, 1.65, -6.4), Vector3(-6.0, 1.2, -19.0), 70.0],
	"sm14": [Vector3(-4.8, 5.2, -16.8), Vector3(-14.0, 4.4, -23.5), 68.0],
	"courtyard": [Vector3(2.0, 1.7, 17.0), Vector3(15.0, 1.8, 31.0), 66.0],
	"amphi": [Vector3(16.2, 1.65, 17.6), Vector3(19.0, -1.6, 7.0), 72.0],
	"cafeteria": [Vector3(0, 0, 0), Vector3(0, 0, 0), 70.0],
	"under": [Vector3(25.4, -1.9, 41.2), Vector3(9.0, -2.7, 49.0), 72.0],
	"aerial": [Vector3(58.0, 62.0, 72.0), Vector3(2.0, 0.0, 8.0), 40.0],
	"title": [Vector3(25.0, 7.0, 37.0), Vector3(3.0, 3.0, 20.0), 55.0],
}

var level: Node3D
var cam: Camera3D
var stats := {}
var warnings: PackedStringArray = []


func _ready() -> void:
	var args := OS.get_cmdline_user_args()
	var only: PackedStringArray = []
	var frames := 45
	var quit_after := true
	for a in args:
		if a.begins_with("--views="):
			only = a.substr(8).split(",")
		elif a.begins_with("--frames="):
			frames = int(a.substr(9))
		elif a == "--no-quit":
			quit_after = false
	get_window().mode = Window.MODE_WINDOWED
	get_window().size = Vector2i(1600, 900)
	get_viewport().scaling_3d_scale = 1.0
	_build_environment()
	var ps: PackedScene = load(LEVEL)
	if ps == null:
		push_error("cannot load " + LEVEL)
		get_tree().quit(1)
		return
	level = ps.instantiate()
	add_child(level)
	_process_markers(level)
	cam = Camera3D.new()
	cam.near = 0.05
	cam.far = 600.0
	add_child(cam)
	cam.make_current()
	# let physics register the static bodies, then probe
	await get_tree().physics_frame
	await get_tree().physics_frame
	_probe_markers()
	_report()
	for view in VIEWS.keys():
		if only.size() > 0 and not only.has(view):
			continue
		_set_view(view)
		for i in frames:
			await get_tree().process_frame
		var img := get_viewport().get_texture().get_image()
		var path := ProjectSettings.globalize_path("res://shots/campus_%s.png" % view)
		img.save_png(path)
		print("[campus_preview] saved ", path)
	if quit_after:
		get_tree().quit()


func _set_view(view: String) -> void:
	var v: Array = VIEWS[view]
	var from: Vector3 = v[0]
	var look: Vector3 = v[1]
	if view == "cafeteria":
		from = _cafe_pt(8.0, 1.2, 1.65)
		look = _cafe_pt(13.0, 7.0, 1.0)
	cam.fov = v[2] * 0.62   # VIEWS store horizontal fov; Camera3D.fov is vertical (16:9)
	cam.global_position = from
	cam.look_at(look, Vector3.UP)


func _cafe_pt(lx: float, lz: float, y: float) -> Vector3:
	var yaw := atan2(-(42.5 - 30.0), -1.5 + 11.5)
	var c := cos(yaw)
	var s := sin(yaw)
	return Vector3(-11.5 + lx * c + lz * s, y, 30.0 - lx * s + lz * c)


# ------------------------------------------------------------------ temporary lighting rig
func _build_environment() -> void:
	var env := Environment.new()
	var sky := Sky.new()
	var sm := ProceduralSkyMaterial.new()
	sm.sky_top_color = Color(0.22, 0.36, 0.62)
	sm.sky_horizon_color = Color(0.95, 0.72, 0.52)
	sm.ground_horizon_color = Color(0.55, 0.45, 0.38)
	sm.ground_bottom_color = Color(0.18, 0.16, 0.15)
	sm.sun_angle_max = 12.0
	sm.sun_curve = 0.08
	sky.sky_material = sm
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_sky_contribution = 1.0
	env.ambient_light_energy = 0.55
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	env.tonemap_mode = Environment.TONE_MAPPER_AGX
	env.tonemap_exposure = 1.0
	env.ssao_enabled = true
	env.ssao_radius = 1.2
	env.ssao_intensity = 1.6
	env.ssil_enabled = true
	env.sdfgi_enabled = true
	env.sdfgi_use_occlusion = true
	env.sdfgi_cascades = 4
	env.sdfgi_min_cell_size = 0.2
	env.glow_enabled = true
	env.glow_intensity = 0.6
	env.glow_bloom = 0.05
	env.glow_hdr_threshold = 1.2
	env.fog_enabled = true
	env.fog_light_color = Color(0.86, 0.72, 0.6)
	env.fog_density = 0.0016
	env.fog_sky_affect = 0.2
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)
	var sun := DirectionalLight3D.new()
	sun.name = "TempSun"
	sun.light_color = Color(1.0, 0.8, 0.6)
	sun.light_energy = 2.4
	sun.shadow_enabled = true
	sun.directional_shadow_max_distance = 140.0
	sun.light_angular_distance = 1.0
	var az := deg_to_rad(SUN_AZ_DEG)
	var el := deg_to_rad(SUN_EL_DEG)
	var to_sun := Vector3(sin(az) * cos(el), sin(el), -cos(az) * cos(el))
	add_child(sun)
	sun.look_at_from_position(Vector3.ZERO, -to_sun, Vector3.UP)


# ------------------------------------------------------------------ markers -> lights / props
func _extras(n: Node) -> Dictionary:
	if n.has_meta("extras"):
		var e = n.get_meta("extras")
		if e is Dictionary:
			return e
	return {}


func _process_markers(root: Node) -> void:
	var lights := 0
	var shadows := 0
	var props := 0
	var missing := {}
	var prop_cache := {}
	var nodes: Array[Node] = []
	_collect(root, nodes)
	for n in nodes:
		var nm := String(n.name)
		if n is MeshInstance3D:
			var mi := n as MeshInstance3D
			stats["meshes"] = stats.get("meshes", 0) + 1
			stats["level_tris"] = stats.get("level_tris", 0) + _tris(mi.mesh)
		if nm.begins_with("LIGHT_"):
			var ex := _extras(n)
			var l: Light3D
			if String(ex.get("type", "omni")) == "spot":
				var s := SpotLight3D.new()
				s.spot_range = float(ex.get("range", 8.0))
				s.spot_angle = float(ex.get("angle", 45.0))
				l = s
			else:
				var o := OmniLight3D.new()
				o.omni_range = float(ex.get("range", 8.0))
				l = o
			l.light_color = Color(String(ex.get("color", "#ffffff")))
			l.light_energy = float(ex.get("energy", 1.0))
			l.shadow_enabled = bool(ex.get("shadow", false))
			if l.shadow_enabled:
				shadows += 1
			n.add_child(l)
			lights += 1
		elif nm.begins_with("PROP_"):
			var asset := nm.substr(5).split("__")[0]
			if not prop_cache.has(asset):
				var p := PROPS_DIR + asset + ".glb"
				prop_cache[asset] = load(p) if ResourceLoader.exists(p) else null
			var scn = prop_cache[asset]
			if scn == null:
				missing[asset] = missing.get(asset, 0) + 1
				continue
			var inst: Node3D = scn.instantiate()
			n.add_child(inst)
			props += 1
			for c in _all(inst):
				if c is MeshInstance3D:
					stats["prop_tris"] = stats.get("prop_tris", 0) + _tris((c as MeshInstance3D).mesh)
	stats["lights"] = lights
	stats["shadow_lights"] = shadows
	stats["props"] = props
	if missing.size() > 0:
		warnings.append("missing prop glbs: " + str(missing))


func _collect(n: Node, out: Array[Node]) -> void:
	out.append(n)
	for c in n.get_children():
		_collect(c, out)


func _all(n: Node) -> Array[Node]:
	var out: Array[Node] = []
	_collect(n, out)
	return out


func _tris(m: Mesh) -> int:
	if m == null:
		return 0
	var t := 0
	for i in m.get_surface_count():
		var arr := m.surface_get_arrays(i)
		var idx = arr[Mesh.ARRAY_INDEX]
		if idx != null and idx.size() > 0:
			t += idx.size() / 3
		else:
			t += arr[Mesh.ARRAY_VERTEX].size() / 3
	return t


# ------------------------------------------------------------------ collision probes
func _ray_floor(p: Vector3, up := 1.0, down := 3.0) -> Variant:
	var q := PhysicsRayQueryParameters3D.create(p + Vector3.UP * up, p - Vector3.UP * down)
	var hit := get_world_3d().direct_space_state.intersect_ray(q)
	if hit.is_empty():
		return null
	return hit["position"].y


func _probe_markers() -> void:
	var counts := {}
	var paths := {}
	for n in _all(level):
		var nm := String(n.name)
		var pre := nm.split("_")[0]
		counts[pre] = counts.get(pre, 0) + 1
		if not (n is Node3D):
			continue
		var p: Vector3 = (n as Node3D).global_position
		if pre in ["SPAWN", "NPC", "SPOT", "DUCK", "ANCHOR"]:
			var up := 0.4 if pre in ["DUCK", "ANCHOR"] else 0.9
			var y = _ray_floor(p, up, 2.0)
			if y == null:
				warnings.append("%s: no floor/support under %s" % [nm, str(p)])
			else:
				var d := p.y - float(y)
				var tol := 0.12 if pre != "DUCK" else 0.2
				if abs(d) > tol and not (pre == "NPC" and _extras(n).get("sit", false)):
					warnings.append("%s: support at y=%.2f, marker at %.2f (d=%.2f)" % [nm, y, p.y, d])
		elif pre == "PATH" or pre == "PORTAL":
			var key := nm.substr(0, nm.rfind("_"))
			if not paths.has(key):
				paths[key] = []
			paths[key].append([nm, p])
	for key in paths.keys():
		var pts: Array = paths[key]
		pts.sort_custom(func(a, b): return a[0] < b[0])
		for i in range(pts.size() - 1):
			var a: Vector3 = pts[i][1]
			var b: Vector3 = pts[i + 1][1]
			var n_s := int(ceil(a.distance_to(b) / 0.4))
			var prev = null
			for k in range(n_s + 1):
				var q := a.lerp(b, float(k) / n_s)
				var y = _ray_floor(q, 1.2, 2.5)
				if y == null:
					warnings.append("%s: hole between %s and %s near %s" % [key, pts[i][0], pts[i + 1][0], str(q)])
					break
				if prev != null and abs(float(y) - float(prev)) > 0.26:
					warnings.append("%s: lip %.2f m near %s" % [key, abs(float(y) - float(prev)), str(q)])
				prev = y
	stats["markers"] = counts


func _report() -> void:
	print("[campus_preview] stats ", JSON.stringify(stats))
	for w in warnings:
		print("[campus_preview] WARN ", w)
	print("[campus_preview] warnings: ", warnings.size())
