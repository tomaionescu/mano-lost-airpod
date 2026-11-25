extends Node3D
## Dev tool (glasses/eyes debugging): char_viewer's lighting and shots, plus per-kind material overrides.
## Godot --path . res://scenes/dev/glass_probe.tscn -- <stem> [...] shots=<dir> [only=face,face34]
##   p:<kind>:<param>=<value>   set a shader parameter (ShaderMaterial) or property (StandardMaterial3D) on every
##                              surface of that kind (kinds as in CharacterMaterials: eye, cornea, lash, glasses...);
##                              a colour as c:r,g,b (0-1, sRGB for a source_color uniform) or c:#rrggbb
##   sh:<kind>=<res path>       swap that kind's shader (ShaderMaterial), keeping its parameters
##   hide=<kind>,<kind>         hide those meshes
##   lights=key,fill,back       which of char_viewer's three lights are on (default all)
##   noshadow, nossao, anim=<clip>

var stems: PackedStringArray = []
var anim := ""
var _frame := 0
var _idx := 0
var _rig: CharacterRig
var _cam: Camera3D
var _shots := [
	["face", Vector3(0.12, 1.56, 0.55), Vector3(0, 1.56, 0), 30.0],
	["face34", Vector3(0.42, 1.58, 0.42), Vector3(0, 1.56, 0), 30.0],
	["face_mouth", Vector3(0.05, 1.54, 0.75), Vector3(0, 1.545, 0), 7.0],
	["full", Vector3(0.9, 1.1, 3.3), Vector3(0, 0.88, 0), 38.0],
	["back", Vector3(-0.6, 1.5, -2.2), Vector3(0, 1.2, 0), 40.0],
	["head", Vector3(0.45, 1.68, 0.62), Vector3(0, 1.6, 0), 30.0],
	["crown", Vector3(-0.32, 2.0, -0.55), Vector3(0, 1.6, -0.02), 32.0],
]
var _shot := 0
var _no_shadow := false
var _overrides := []   # [kind, param, value]
var _swaps := {}       # kind -> Shader
var _hide := PackedStringArray()
var _lights := PackedStringArray(["key", "fill", "back"])
var _ncam := 0
var _rest := false
var _pose := ""   # "rest": the bind pose, no idle, no blinks or look-at


func _ready() -> void:
	var only := PackedStringArray()
	for a in OS.get_cmdline_user_args():
		if a.begins_with("anim="):
			anim = a.substr(5)
		elif a == "noshadow":
			_no_shadow = true
		elif a.begins_with("cam="):
			# a custom shot "cam": position, target (authored for a 1.56 m eye line, like the others), fov
			var v := a.substr(4).split_floats(",")
			_shots.append(["cam%d" % _ncam, Vector3(v[0], v[1], v[2]), Vector3(v[3], v[4], v[5]), v[6]])
			_ncam += 1
		elif a == "rest":
			_rest = true
		elif a.begins_with("pose="):
			# a fixed frame of a clip, the same in every run: pose=idle@0.4
			_pose = a.substr(5)
		elif a.begins_with("only="):
			only = a.substr(5).split(",")
		elif a.begins_with("hide="):
			_hide = a.substr(5).split(",")
		elif a.begins_with("lights="):
			_lights = a.substr(7).split(",")
		elif a.begins_with("p:"):
			var kv := a.substr(2).split("=", true, 1)
			var kp := kv[0].split(":")
			_overrides.append([kp[0], kp[1], _val(kv[1])])
		elif a.begins_with("sh:"):
			var kv := a.substr(3).split("=", true, 1)
			_swaps[kv[0]] = load(kv[1])
		elif "=" in a or a == "nossao":
			pass
		else:
			stems.append(a)
	if not only.is_empty():
		_shots = _shots.filter(func(s) -> bool: return String(s[0]) in only or String(s[0]).begins_with("cam"))
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.11, 0.12, 0.14)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.42, 0.45, 0.52)
	env.ambient_light_energy = 0.55
	env.tonemap_mode = Environment.TONE_MAPPER_AGX
	env.tonemap_exposure = 1.0
	env.ssao_enabled = not "nossao" in OS.get_cmdline_user_args()
	env.ssao_radius = 0.6
	env.glow_enabled = true
	env.glow_intensity = 0.4
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)
	if "key" in _lights:
		_light(DirectionalLight3D.new(), Vector3(-35, 35, 0), Color(1.0, 0.86, 0.72), 2.2, true)
	if "fill" in _lights:
		_light(DirectionalLight3D.new(), Vector3(-15, -60, 0), Color(0.55, 0.65, 0.9), 0.7, false)
	if "back" in _lights:
		_light(DirectionalLight3D.new(), Vector3(-20, 160, 0), Color(1.0, 0.8, 0.6), 1.6, false)
	var floor := MeshInstance3D.new()
	floor.mesh = PlaneMesh.new()
	(floor.mesh as PlaneMesh).size = Vector2(8, 8)
	var fm := StandardMaterial3D.new()
	fm.albedo_color = Color(0.2, 0.21, 0.23)
	fm.roughness = 0.8
	floor.material_override = fm
	add_child(floor)
	_cam = Camera3D.new()
	add_child(_cam)
	_load_next()


func _val(s: String) -> Variant:
	if s.begins_with("c:"):
		# a colour, "c:r,g,b" (0-1, as a source_color uniform takes it: sRGB) or "c:#rrggbb"
		var cs := s.substr(2)
		if cs.begins_with("#"):
			return Color.html(cs)
		var f := cs.split_floats(",")
		return Color(f[0], f[1], f[2])
	if s.is_valid_float():
		return float(s)
	if s == "true" or s == "false":
		return s == "true"
	return s


func _light(l: DirectionalLight3D, rot: Vector3, c: Color, e: float, shadow: bool) -> void:
	l.rotation_degrees = rot
	l.light_color = c
	l.light_energy = e
	l.shadow_enabled = shadow and not _no_shadow
	l.directional_shadow_max_distance = 10.0
	add_child(l)


func _meshes(n: Node, out: Array = []) -> Array:
	if n is MeshInstance3D:
		out.append(n)
	for c in n.get_children():
		_meshes(c, out)
	return out


func _kind(mi: MeshInstance3D) -> String:
	for t in String(mi.name).split("_"):
		if t in CharacterMaterials.KINDS:
			return t
	return ""


func _apply_overrides() -> void:
	for node in _meshes(_rig):
		var mi := node as MeshInstance3D
		var k := _kind(mi)
		if k in _hide:
			mi.visible = false
		for s in mi.get_surface_override_material_count():
			var m: Material = mi.get_surface_override_material(s)
			if m == null:
				continue
			if _swaps.has(k) and m is ShaderMaterial:
				(m as ShaderMaterial).shader = _swaps[k]
			for o in _overrides:
				if o[0] != k:
					continue
				if m is ShaderMaterial:
					(m as ShaderMaterial).set_shader_parameter(o[1], o[2])
					# and the same uniform on a next pass that has it (glasses_over_hair)
					var nx := m.next_pass as ShaderMaterial
					if nx and nx.shader and String(o[1]) in nx.shader.code:
						nx.set_shader_parameter(o[1], o[2])
				else:
					m.set(o[1], o[2])
				print("probe ", mi.name, " ", o[1], " = ", o[2])


func _load_next() -> void:
	if _rig:
		_rig.queue_free()
	_rig = CharacterRig.new()
	add_child(_rig)
	_rig.load_model("res://assets/characters/%s.glb" % stems[_idx])
	CharacterMaterials.apply(_rig)
	_apply_overrides()
	_rig.rotation.y = 0.0
	if _rest or _pose != "":
		if _rig.tree:
			_rig.tree.active = false
		_rig.set_process(false)
	if _pose != "" and _rig.anim_player:
		var clip := _pose.get_slice("@", 0)
		_rig.anim_player.play(_rig._clips[clip])
		_rig.anim_player.seek(float(_pose.get_slice("@", 1)), true)
		_rig.anim_player.pause()
	if anim != "" and _rig.anim_player and _rig.has_clip(anim):
		_rig.tree.active = false
		_rig.anim_player.play(_rig._clips[anim])
	_shot = 0
	_frame = 0
	_set_shot()


func _set_shot() -> void:
	var s = _shots[_shot]
	var head := _rig.head_position() if _rig else Vector3(0, 1.64, 0)
	var dy := head.y - 0.08 - 1.56 if String(s[0]) in ["face", "face34", "face_mouth", "head", "crown"] or String(s[0]).begins_with("cam") else 0.0
	_cam.fov = s[3]
	_cam.position = s[1] + Vector3(0, dy, 0)
	_cam.look_at(s[2] + Vector3(0, dy, 0))


func _process(_dt: float) -> void:
	_frame += 1
	if _frame < 25:
		return
	set_process(false)
	RenderingServer.force_draw()
	await RenderingServer.frame_post_draw
	set_process(true)
	var img := get_viewport().get_texture().get_image()
	print("shot ", _shots[_shot][0], " cam ", _cam.global_position)
	img.save_png("%s/char_%s_%s.png" % [preload("res://scripts/dev/autotest.gd").shots_dir(), stems[_idx], _shots[_shot][0]])
	_shot += 1
	_frame = 15
	if _shot >= _shots.size():
		_idx += 1
		if _idx >= stems.size():
			get_tree().quit()
			return
		_load_next()
	else:
		_set_shot()
