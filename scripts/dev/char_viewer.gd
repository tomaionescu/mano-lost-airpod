extends Node3D
## Dev tool: renders a character glb under game lighting and saves close-up + full-body shots.
## Godot --path . res://scenes/dev/char_viewer.tscn -- <glb stem> [<glb stem> ...] [anim=<clip>]

var stems: PackedStringArray = []
var anim := ""
var _frame := 0
var _idx := 0
var _rig: CharacterRig
var _cam: Camera3D
var _shots := [
	["face", Vector3(0.12, 1.56, 0.55), Vector3(0, 1.56, 0), 30.0],
	["face34", Vector3(0.42, 1.58, 0.42), Vector3(0, 1.56, 0), 30.0],
	# the slide below puts 1.56 at the head bone (mouth height); the mouth is just under it
	["face_mouth", Vector3(0.05, 1.54, 0.75), Vector3(0, 1.545, 0), 7.0],
	["full", Vector3(0.9, 1.1, 3.3), Vector3(0, 0.88, 0), 38.0],
	["back", Vector3(-0.6, 1.5, -2.2), Vector3(0, 1.2, 0), 40.0],
	# the whole head, crown included (the face shots crop it), from a little above the front three-quarter
	["head", Vector3(0.45, 1.68, 0.62), Vector3(0, 1.6, 0), 30.0],
	# from above and behind: the crown, the back of the hair, the nape
	["crown", Vector3(-0.32, 2.0, -0.55), Vector3(0, 1.6, -0.02), 32.0],
]
var _shot := 0
var _no_shadow := false   # "noshadow": lights without shadows (to tell shadow artifacts from model ones)


func _ready() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("anim="):
			anim = a.substr(5)
		elif a == "debugface":
			pass
		elif a == "noshadow":
			_no_shadow = true
		elif a == "nossao":
			pass
		elif a == "nolod":
			# full-detail meshes at any distance (to tell LOD artifacts from model ones)
			get_viewport().mesh_lod_threshold = 0.0
		elif "=" in a:
			# other key=value flags (shots=, hairshell=, hairdebug=, ...) are read where they apply
			pass
		else:
			stems.append(a)
	if stems.is_empty():
		stems = ["mano_street"]
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.11, 0.12, 0.14)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.42, 0.45, 0.52)
	env.ambient_light_energy = 0.55
	env.tonemap_mode = Environment.TONE_MAPPER_AGX
	env.tonemap_exposure = 1.0
	# "nossao": no screen-space AO (to tell its darkening from shadows and the model)
	env.ssao_enabled = not "nossao" in OS.get_cmdline_user_args()
	env.ssao_radius = 0.6
	env.glow_enabled = true
	env.glow_intensity = 0.4
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)
	_light(DirectionalLight3D.new(), Vector3(-35, 35, 0), Color(1.0, 0.86, 0.72), 2.2, true)
	_light(DirectionalLight3D.new(), Vector3(-15, -60, 0), Color(0.55, 0.65, 0.9), 0.7, false)
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


func _light(l: DirectionalLight3D, rot: Vector3, c: Color, e: float, shadow: bool) -> void:
	l.rotation_degrees = rot
	l.light_color = c
	l.light_energy = e
	l.shadow_enabled = shadow and not _no_shadow
	l.directional_shadow_max_distance = 10.0
	add_child(l)


func _load_next() -> void:
	if _rig:
		_rig.queue_free()
	_rig = CharacterRig.new()
	add_child(_rig)
	_rig.load_model("res://assets/characters/%s.glb" % stems[_idx])
	CharacterMaterials.apply(_rig)
	_rig.rotation.y = 0.0
	if anim != "" and _rig.anim_player and _rig.has_clip(anim):
		_rig.tree.active = false
		_rig.anim_player.play(_rig._clips[anim])
	_shot = 0
	_frame = 0
	_set_shot()


func _set_shot() -> void:
	var s = _shots[_shot]
	# shots are authored for a 1.56 m eye line; slide them to this character's head
	var head := _rig.head_position() if _rig else Vector3(0, 1.64, 0)
	var dy := head.y - 0.08 - 1.56 if String(s[0]) in ["face", "face34", "face_mouth", "head", "crown"] else 0.0
	_cam.fov = s[3]
	_cam.position = s[1] + Vector3(0, dy, 0)
	_cam.look_at(s[2] + Vector3(0, dy, 0))


func _process(_dt: float) -> void:
	_frame += 1
	if _frame < 25:
		return
	if "debugface" in OS.get_cmdline_user_args() and _shot == 0 and _rig:
		# what deforms the face right now: blend shapes off zero, and head-area bones away from their rest
		for mi in _rig.face_meshes:
			for i in mi.mesh.get_blend_shape_count():
				var v := mi.get_blend_shape_value(i)
				if absf(v) > 0.01:
					print("debugface shape ", mi.name, " ", mi.mesh.get_blend_shape_name(i), " = ", snappedf(v, 0.001))
		if _rig.skeleton:
			var sk := _rig.skeleton
			for b in sk.get_bone_count():
				var n := sk.get_bone_name(b)
				if n.contains("jaw") or n.contains("head") or n.contains("neck") or n.contains("eye") or n.contains("lip"):
					var d := sk.get_bone_pose(b).basis.get_rotation_quaternion().angle_to(sk.get_bone_rest(b).basis.get_rotation_quaternion())
					print("debugface bone ", n, " off rest ", snappedf(rad_to_deg(d), 0.1), " deg")
	# take the frame that was just drawn (a window macOS stops redrawing gave the same image for every later shot)
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
