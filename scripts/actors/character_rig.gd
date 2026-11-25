class_name CharacterRig
extends Node3D
## Wraps an imported character (.glb from tools/blender/build_human.py): locomotion blend space,
## sit / talk states, one-shot gestures, head look-at, blinking, procedural lip flap and facial expressions.

signal footstep(foot: String)

const LOCO_POINTS := {"idle": 0.0, "walk": 1.33, "jog": 3.07, "run": 4.5}

var skeleton: Skeleton3D
var anim_player: AnimationPlayer
var tree: AnimationTree
var face_meshes: Array[MeshInstance3D] = []
var look_mod: LookAtModifier3D
var neck_mod: LookAtModifier3D
var look_target: Node3D

var speed := 0.0
var sitting := false
var talking := false        # lip flap: only while this character is saying a line
var conversing := false     # body: in a conversation (talking idle / seated talking)
var _sit_clip_default := "sit_idle"
var talk_level := 0.0
var look_weight := 0.0
var look_at_point = null # Vector3 or null
var expression := {} # blend shape -> target weight
var eyes_closed := 0.0   # 0..1, overrides blinking (sleeping, waking up)
var lid_rest := 0.0      # the lids' resting drop (CharacterMaterials.FINISH "rig"; 0 for anyone not listed)
var _expr_now := {}
var _blink_t := 2.0
var _blink := 0.0
var _talk_phase := 0.0
var _syllable := 0.0
var _syllable_target := 0.0
var _lip_env := PackedFloat32Array()   # a recorded line's jaw opening at VoiceLines.ENV_RATE (lip_sync)
var _lip_player: AudioStreamPlayer
var _lip_stream: AudioStream
var _shape_index := {} # mesh -> {name: idx}
var _mouth_mats: Array[StandardMaterial3D] = []   # teeth + tongue (CharacterMaterials), lit by how open the mouth is
var _mouth_light := -1.0
var _mouth_tries := 0
var _clips := {}
var _state := ""   # empty so the first set_state() really sends a request (a Transition starts with no state)
var loco_points := LOCO_POINTS.duplicate()
var idle_clip := "idle"


## Lip sync to the recorded line `player` is playing: `env` is its jaw opening (0..1) at VoiceLines.ENV_RATE.
## It lasts while that clip is the player's stream (Dialogue clears it when the card goes); an empty `env`
## goes back to the random flap.
func lip_sync(env: PackedFloat32Array, player: AudioStreamPlayer) -> void:
	_lip_env = env
	_lip_player = player if not env.is_empty() else null
	_lip_stream = player.stream if _lip_player else null


## Max speed this body can walk/jog without sliding (for movement code).
func stride_speed(kind: String) -> float:
	return float(loco_points.get(kind, LOCO_POINTS.get(kind, 1.33)))


func load_model(path: String) -> void:
	var packed: PackedScene = load(path)
	var model := packed.instantiate()
	add_child(model)
	skeleton = _find(model, "Skeleton3D") as Skeleton3D
	anim_player = _find(model, "AnimationPlayer") as AnimationPlayer
	for m in _find_all(model, "MeshInstance3D"):
		var mi := m as MeshInstance3D
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		if mi.mesh and mi.mesh.get_blend_shape_count() > 0:
			face_meshes.append(mi)
			var idx := {}
			for i in mi.mesh.get_blend_shape_count():
				idx[String(mi.mesh.get_blend_shape_name(i))] = i
			_shape_index[mi] = idx
	if not face_meshes.is_empty():
		var rf: Dictionary = CharacterMaterials.FINISH.get(String(face_meshes[0].name).get_slice("_", 0), {}).get("rig", {})
		lid_rest = float(rf.get("lid_rest", 0.0))
	# each body's own stride speeds (from tools/blender/retarget.py) keep the feet planted
	var ex := _find_extras(model, "anim_speeds")
	if not ex.is_empty():
		var sp: Dictionary = ex.anim_speeds
		for k in ["walk", "jog", "run"]:
			if sp.has(k):
				loco_points[k] = float(sp[k])
	if anim_player:
		for n in anim_player.get_animation_list():
			_clips[String(n).get_slice("/", 1) if "/" in String(n) else String(n)] = n
		_build_tree()
	if skeleton:
		_build_look_at()
	_blink_t = randf_range(1.0, 4.0)


func has_clip(name: String) -> bool:
	return _clips.has(name)


func _clip(name: String) -> String:
	return _clips.get(name, _clips.get("idle", ""))


func _build_tree() -> void:
	for n in _clips:
		var a := anim_player.get_animation(_clips[n])
		if a and n in ["idle", "idle_2", "walk", "jog", "run", "sit_idle", "talk_idle", "sit_talk", "typing"]:
			a.loop_mode = Animation.LOOP_LINEAR
	tree = AnimationTree.new()
	tree.name = "AnimationTree"
	add_child(tree)
	tree.anim_player = tree.get_path_to(anim_player)
	var root := AnimationNodeBlendTree.new()

	var loco := AnimationNodeBlendSpace1D.new()
	loco.min_space = 0.0
	loco.max_space = 6.0
	for k in LOCO_POINTS:
		var clip_name: String = idle_clip if k == "idle" else k
		if has_clip(clip_name):
			var an := AnimationNodeAnimation.new()
			an.animation = _clips[clip_name]
			loco.add_blend_point(an, loco_points[k], -1, StringName(k))
	root.add_node("loco", loco, Vector2(0, 0))

	var trans := AnimationNodeTransition.new()
	trans.xfade_time = 0.45
	var inputs := ["loco", "sit", "talk"]
	for i in inputs.size():
		trans.add_input(inputs[i])
	root.add_node("state", trans, Vector2(400, 0))
	root.connect_node("state", 0, "loco")
	var sit := AnimationNodeAnimation.new()
	sit.animation = _clip("sit_idle")
	root.add_node("sit", sit, Vector2(200, 120))
	root.connect_node("state", 1, "sit")
	var talk := AnimationNodeAnimation.new()
	talk.animation = _clip("talk_idle")
	root.add_node("talk", talk, Vector2(200, 240))
	root.connect_node("state", 2, "talk")

	var shot := AnimationNodeOneShot.new()
	shot.fadein_time = 0.25
	shot.fadeout_time = 0.35
	shot.filter_enabled = false
	root.add_node("gesture", shot, Vector2(600, 0))
	root.connect_node("gesture", 0, "state")
	var gest := AnimationNodeAnimation.new()
	gest.animation = _clip("wave")
	root.add_node("gesture_anim", gest, Vector2(400, 200))
	root.connect_node("gesture", 1, "gesture_anim")
	root.connect_node("output", 0, "gesture")
	tree.tree_root = root
	tree.active = true
	set_state("loco")


func _build_look_at() -> void:
	look_target = Node3D.new()
	look_target.name = "LookTarget"
	add_child(look_target)
	look_target.top_level = true
	if skeleton.find_bone("neck_01") != -1:
		neck_mod = _make_look("neck_01", 35.0, 25.0)
	if skeleton.find_bone("head") != -1:
		look_mod = _make_look("head", 55.0, 30.0)


func _make_look(bone: String, yaw_limit: float, pitch_limit: float) -> LookAtModifier3D:
	var m := LookAtModifier3D.new()
	skeleton.add_child(m)
	m.bone_name = bone
	m.target_node = m.get_path_to(look_target)
	# which local bone axis is the face direction (model +Z) and which is "up" depends on the rig's bone rolls
	var b := skeleton.get_bone_global_rest(skeleton.find_bone(bone)).basis.orthonormalized()
	var cand := [[SkeletonModifier3D.BONE_AXIS_PLUS_X, b.x], [SkeletonModifier3D.BONE_AXIS_MINUS_X, -b.x],
		[SkeletonModifier3D.BONE_AXIS_PLUS_Y, b.y], [SkeletonModifier3D.BONE_AXIS_MINUS_Y, -b.y],
		[SkeletonModifier3D.BONE_AXIS_PLUS_Z, b.z], [SkeletonModifier3D.BONE_AXIS_MINUS_Z, -b.z]]
	var best_fwd = cand[0]
	for c in cand:
		if (c[1] as Vector3).dot(Vector3.BACK) > (best_fwd[1] as Vector3).dot(Vector3.BACK):
			best_fwd = c
	m.forward_axis = best_fwd[0]
	var ups := [absf(b.x.dot(Vector3.UP)), absf(b.y.dot(Vector3.UP)), absf(b.z.dot(Vector3.UP))]
	m.primary_rotation_axis = ups.find(ups.max()) as Vector3.Axis
	m.use_angle_limitation = true
	m.symmetry_limitation = true
	m.primary_limit_angle = deg_to_rad(yaw_limit)
	m.secondary_limit_angle = deg_to_rad(pitch_limit)
	m.duration = 0.35
	m.transition_type = Tween.TRANS_SINE
	m.ease_type = Tween.EASE_IN_OUT
	m.influence = 0.0
	return m


func set_state(s: String) -> void:
	if tree == null or s == _state:
		return
	_state = s
	tree.set("parameters/state/transition_request", s)


func play_gesture(name: String) -> void:
	if tree == null or not has_clip(name):
		return
	var root := tree.tree_root as AnimationNodeBlendTree
	(root.get_node("gesture_anim") as AnimationNodeAnimation).animation = _clips[name]
	tree.set("parameters/gesture/request", AnimationNodeOneShot.ONE_SHOT_REQUEST_FIRE)


func set_talk_clip(name: String) -> void:
	if tree and has_clip(name):
		var root := tree.tree_root as AnimationNodeBlendTree
		(root.get_node("talk") as AnimationNodeAnimation).animation = _clips[name]


func set_conversing(on: bool) -> void:
	if on == conversing:
		return
	conversing = on
	if sitting and has_clip("sit_talk"):
		var root := tree.tree_root as AnimationNodeBlendTree if tree else null
		if root:
			var cur := String((root.get_node("sit") as AnimationNodeAnimation).animation)
			if on:
				_sit_clip_default = cur.get_slice("/", cur.get_slice_count("/") - 1)
				set_sit_clip("sit_talk")
			else:
				set_sit_clip(_sit_clip_default)


func set_sit_clip(name: String) -> void:
	if tree and has_clip(name):
		var root := tree.tree_root as AnimationNodeBlendTree
		(root.get_node("sit") as AnimationNodeAnimation).animation = _clips[name]


func bone_global(bone: String) -> Vector3:
	if skeleton == null:
		return global_position + Vector3.UP * 1.6
	var i := skeleton.find_bone(bone)
	if i == -1:
		return global_position + Vector3.UP * 1.6
	return skeleton.global_transform * skeleton.get_bone_global_pose(i).origin


func head_position() -> Vector3:
	return bone_global("head") + Vector3.UP * 0.08


func _process(dt: float) -> void:
	if tree:
		tree.set("parameters/loco/blend_position", speed)
		set_state("sit" if sitting else ("talk" if conversing and speed < 0.2 else "loco"))
	_update_look(dt)
	_update_face(dt)


func _update_look(dt: float) -> void:
	if look_target == null:
		return
	var want := 0.0
	if look_at_point != null:
		look_target.global_position = look_target.global_position.lerp(look_at_point, 1.0 - exp(-dt * 6.0)) if look_weight > 0.01 else look_at_point
		want = 1.0
	look_weight = move_toward(look_weight, want, dt * 1.6)
	var w := smoothstep(0.0, 1.0, look_weight)
	if look_mod:
		look_mod.influence = w * 0.75
	if neck_mod:
		neck_mod.influence = w * 0.35


# ------------------------------------------------------------------ face
func _set_shape(name: String, v: float) -> void:
	for mi in face_meshes:
		var idx: Dictionary = _shape_index[mi]
		if idx.has(name):
			mi.set_blend_shape_value(idx[name], v)


func _update_face(dt: float) -> void:
	if face_meshes.is_empty():
		return
	# blinking: quick close, slower open, occasional double blink
	_blink_t -= dt
	if _blink_t <= 0.0:
		_blink = 1.0
		_blink_t = randf_range(2.2, 5.5) if randf() > 0.15 else 0.22
	var b := 0.0
	if _blink > 0.0:
		_blink = maxf(_blink - dt * 7.0, 0.0)
		b = sin(_blink * PI) if _blink > 0.5 else sin(_blink * PI) * 0.95
	b = maxf(maxf(b, eyes_closed), lid_rest)
	_set_shape("eyeBlinkLeft", b)
	_set_shape("eyeBlinkRight", b)
	# lip flap: syllables at ~4.5 per second with random openness while talking; a recorded line (lip_sync)
	# drives the jaw from its loudness instead, and closes it once the clip has ended
	var synced := _lip_stream != null and is_instance_valid(_lip_player) and _lip_player.stream == _lip_stream
	talk_level = move_toward(talk_level, 1.0 if talking else 0.0, dt * (12.0 if synced else 4.0))
	if talk_level > 0.0 and synced:
		_talk_phase = fmod(_talk_phase + dt * 4.7, 1.0)
		var target := 0.0
		if _lip_player.playing:
			var f := (_lip_player.get_playback_position() + AudioServer.get_time_since_last_mix() + 0.04) * VoiceLines.ENV_RATE
			var i := int(f)
			if i + 1 < _lip_env.size():
				target = lerpf(_lip_env[i], _lip_env[i + 1], f - i)
		_syllable = lerpf(_syllable, target, 1.0 - exp(-dt * 28.0))
	elif talk_level > 0.0:
		_talk_phase += dt * randf_range(4.0, 5.5)
		if _talk_phase >= 1.0:
			_talk_phase = 0.0
			_syllable_target = randf_range(0.15, 0.75) if randf() > 0.12 else 0.0
		_syllable = lerpf(_syllable, _syllable_target * sin(_talk_phase * PI), 1.0 - exp(-dt * 30.0))
	else:
		_syllable = lerpf(_syllable, 0.0, 1.0 - exp(-dt * 12.0))
	var open := _syllable * talk_level
	_set_shape("jawOpen", open * 0.55)
	_set_shape("mouthFunnel", open * 0.25 * (0.5 + 0.5 * sin(_talk_phase * 7.0)))
	_set_shape("mouthStretchLeft", open * 0.15)
	_set_shape("mouthStretchRight", open * 0.15)
	# expressions ease in and out
	for k in expression:
		_expr_now[k] = lerpf(_expr_now.get(k, 0.0), expression[k], 1.0 - exp(-dt * 5.0))
	for k in _expr_now.keys():
		if not expression.has(k):
			_expr_now[k] = lerpf(_expr_now[k], 0.0, 1.0 - exp(-dt * 5.0))
			if _expr_now[k] < 0.002:
				_set_shape(k, 0.0)
				_expr_now.erase(k)
				continue
		_set_shape(k, _expr_now[k])
	# light into the mouth: the jaw dropping, or a grin parting the lips
	var jaw := open * 0.55 + float(_expr_now.get("jawOpen", 0.0))
	var grin := maxf(float(_expr_now.get("mouthSmileLeft", 0.0)), float(_expr_now.get("mouthSmileRight", 0.0)))
	_update_mouth_light(clampf(jaw * 4.0 + maxf(grin - 0.3, 0.0) * 1.2, 0.0, 1.0))


func _update_mouth_light(light: float) -> void:
	if _mouth_mats.is_empty():
		# the game materials go on after load_model(): pick them up once they are there
		if _mouth_tries > 60:
			return
		_mouth_tries += 1
		for mi in _find_all(self, "MeshInstance3D"):
			var m := (mi as MeshInstance3D).get_surface_override_material(0) as StandardMaterial3D if (mi as MeshInstance3D).get_surface_override_material_count() > 0 else null
			if m and m.has_meta("mouth_base"):
				_mouth_mats.append(m)
		if _mouth_mats.is_empty():
			return
	if absf(light - _mouth_light) < 0.01:
		return
	_mouth_light = light
	for m in _mouth_mats:
		CharacterMaterials.set_mouth_light(m, light)


func set_expression(name: String) -> void:
	expression = {
		"smile": {"mouthSmileLeft": 0.55, "mouthSmileRight": 0.55, "cheekSquintLeft": 0.25, "cheekSquintRight": 0.25},
		"grin": {"mouthSmileLeft": 0.85, "mouthSmileRight": 0.85, "cheekSquintLeft": 0.45, "cheekSquintRight": 0.45, "eyeSquintLeft": 0.2, "eyeSquintRight": 0.2},
		"shock": {"browInnerUp": 0.8, "browOuterUpLeft": 0.6, "browOuterUpRight": 0.6, "eyeWideLeft": 0.6, "eyeWideRight": 0.6, "jawOpen": 0.2},
		"annoyed": {"browDownLeft": 0.55, "browDownRight": 0.55, "mouthPressLeft": 0.4, "mouthPressRight": 0.4},
		"sad": {"browInnerUp": 0.6, "mouthFrownLeft": 0.45, "mouthFrownRight": 0.45},
		"smirk": {"mouthSmileLeft": 0.5, "browOuterUpLeft": 0.3},
		"tired": {"eyeBlinkLeft": 0.35, "eyeBlinkRight": 0.35, "browInnerUp": 0.2},
		"neutral": {},
	}.get(name, {})


# ------------------------------------------------------------------ helpers
static func _find_extras(n: Node, key: String) -> Dictionary:
	if n.has_meta("extras"):
		var ex = n.get_meta("extras")
		if ex is Dictionary and ex.has(key):
			return ex
	for c in n.get_children():
		var r := _find_extras(c, key)
		if not r.is_empty():
			return r
	return {}


static func _find(n: Node, cls: String) -> Node:
	if n.is_class(cls):
		return n
	for c in n.get_children():
		var r := _find(c, cls)
		if r:
			return r
	return null


static func _find_all(n: Node, cls: String, out: Array = []) -> Array:
	if n.is_class(cls):
		out.append(n)
	for c in n.get_children():
		_find_all(c, cls, out)
	return out
