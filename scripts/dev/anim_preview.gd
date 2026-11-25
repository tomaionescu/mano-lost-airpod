extends Node3D
## Dev tool: plays every animation clip of a character glb and saves contact sheets to shots/anim_<clip>.png.
## Godot --path . --position 40,40 res://scenes/dev/anim_preview.tscn -- [test_anim] [clips=walk,idle] [frames=8]
##   [view=side|front|34] [blend=1.6]   (blend=<speed>: drive the real AnimationTree locomotion blend space)
## Locomotion clips are shown on a treadmill: the checker floor scrolls backwards at the clip's speed (from the
## clip's "speed" metadata if present, else LOCO_SPEED), so planted feet must stay on the same floor square.

const LOCO_SPEED := {"walk": 1.335, "jog": 3.08, "run": 4.10}
const CELL := Vector2i(360, 480)

var stem := "test_anim"
var clips: PackedStringArray = []
var frames := 8
var view := "34"
var blend_speed := -1.0
var _rig: CharacterRig
var _cam: Camera3D
var _view: SubViewport
var _floor: MeshInstance3D
var _floor_mat: StandardMaterial3D
var _chair: Node3D
var _desk: Node3D


func _ready() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("clips="):
			clips = a.substr(6).split(",")
		elif a.begins_with("frames="):
			frames = int(a.substr(7))
		elif a.begins_with("view="):
			view = a.substr(5)
		elif a.begins_with("blend="):
			blend_speed = float(a.substr(6))
		else:
			stem = a
	_setup_stage()
	_rig = CharacterRig.new()
	add_child(_rig)
	_rig.load_model("res://assets/characters/%s.glb" % stem)
	CharacterMaterials.apply(_rig)
	if clips.is_empty():
		for n in _rig._clips:
			clips.append(n)
	await _run()
	get_tree().quit()


func _setup_stage() -> void:
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.78, 0.8, 0.84)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.6, 0.62, 0.68)
	env.ambient_light_energy = 0.7
	env.tonemap_mode = Environment.TONE_MAPPER_AGX
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-50, 30, 0)
	sun.light_energy = 1.6
	sun.shadow_enabled = true
	sun.directional_shadow_max_distance = 12.0
	add_child(sun)
	# checker floor (0.25 m squares) that can scroll like a treadmill
	var img := Image.create_empty(64, 64, false, Image.FORMAT_RGB8)
	for y in 64:
		for x in 64:
			var c := 0.86 if ((x / 32) + (y / 32)) % 2 == 0 else 0.55
			img.set_pixel(x, y, Color(c, c, c * 1.02))
	var tex := ImageTexture.create_from_image(img)
	_floor_mat = StandardMaterial3D.new()
	_floor_mat.albedo_texture = tex
	_floor_mat.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	_floor_mat.roughness = 0.9
	_floor_mat.uv1_scale = Vector3(10, 10, 1)   # 5 m plane, one texture = 2 squares = 0.5 m
	_floor = MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(5, 5)
	_floor.mesh = pm
	_floor.material_override = _floor_mat
	add_child(_floor)
	# chair proxy (seat top 0.45 m, front edge at the root, seat behind the character who faces +Z) and desk
	_chair = Node3D.new()
	add_child(_chair)
	_box(_chair, Vector3(0.46, 0.04, 0.44), Vector3(0, 0.43, -0.22), Color(0.45, 0.32, 0.22))
	_box(_chair, Vector3(0.46, 0.45, 0.04), Vector3(0, 0.68, -0.46), Color(0.45, 0.32, 0.22))
	_box(_chair, Vector3(0.40, 0.41, 0.38), Vector3(0, 0.205, -0.22), Color(0.35, 0.25, 0.18))
	_desk = Node3D.new()
	add_child(_desk)
	_box(_desk, Vector3(1.2, 0.03, 0.6), Vector3(0, 0.725, 0.25), Color(0.55, 0.5, 0.44))
	_box(_desk, Vector3(0.42, 0.02, 0.14), Vector3(0, 0.75, 0.1), Color(0.2, 0.2, 0.22))
	# render through a fixed-size SubViewport sharing this world (independent of the window size)
	_view = SubViewport.new()
	_view.size = CELL
	_view.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	_view.msaa_3d = Viewport.MSAA_4X
	add_child(_view)
	_cam = Camera3D.new()
	_cam.fov = 40.0
	_view.add_child(_cam)
	_cam.current = true


func _box(parent: Node3D, size: Vector3, pos: Vector3, col: Color) -> void:
	var mi := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = size
	mi.mesh = bm
	var m := StandardMaterial3D.new()
	m.albedo_color = col
	m.roughness = 0.8
	mi.material_override = m
	mi.position = pos
	parent.add_child(mi)


func _place_camera(sitting: bool) -> void:
	var tgt := Vector3(0, 0.62 if sitting else 0.86, 0)
	match view:
		"feet":
			_cam.position = Vector3(1.5, 0.32, 0.0)
			tgt = Vector3(0, 0.18, 0)
		"side":
			_cam.position = Vector3(3.4, 0.95, 0.0)
		"front":
			_cam.position = Vector3(0.0, 1.1, 3.5)
		_:
			_cam.position = Vector3(1.9, 1.25, 2.9)
	_cam.look_at(tgt)


func _run() -> void:
	var ap := _rig.anim_player
	for clip in clips:
		if not _rig.has_clip(clip):
			push_warning("no clip " + clip)
			continue
		var anim := ap.get_animation(_rig._clips[clip])
		var length := anim.length
		var looping := clip in ["idle", "idle_2", "walk", "jog", "run", "sit_idle", "sit_talk", "typing", "talk_idle"]
		_place_camera(clip.begins_with("sit") or clip == "typing")
		_chair.visible = clip.begins_with("sit") or clip in ["typing", "stand_up"]
		_desk.visible = clip == "typing"
		var speed: float = LOCO_SPEED.get(clip, 0.0)
		var sheet := Image.create_empty(CELL.x * frames, CELL.y, false, Image.FORMAT_RGBA8)
		if blend_speed >= 0.0 and _rig.tree:
			_rig.tree.active = true
			_rig.speed = blend_speed
		else:
			_rig.tree.active = false
			ap.play(_rig._clips[clip])
			ap.pause()
		for k in frames:
			var t := length * float(k) / float(frames if looping else max(frames - 1, 1))
			if blend_speed < 0.0:
				ap.seek(t, true)
			# treadmill: the floor moves towards -Z (the character faces +Z) at the clip speed
			_floor.position.z = -fposmod(speed * t, 0.5)
			await get_tree().process_frame
			await RenderingServer.frame_post_draw
			var shot := _view.get_texture().get_image()
			shot.convert(Image.FORMAT_RGBA8)
			sheet.blit_rect(shot, Rect2i(Vector2i.ZERO, CELL), Vector2i(CELL.x * k, 0))
		var path := "res://shots/anim_%s%s.png" % [clip, "" if view == "34" else "_" + view]
		sheet.save_png(path)
		print("[anim_preview] ", clip, " length ", snappedf(length, 0.01), " -> ", path)
