class_name Player
extends CharacterBody3D
## Mano. Camera-relative movement with eased starts/stops, rotation toward travel, jog on Shift,
## footsteps per surface, head look-at, and the interaction target under his nose.

signal stepped(surface: String, running: bool)

const WALK := 1.55
const JOG := 3.35
const ACCEL := 9.0          # exponential approach rate (1/s): ~95% of target speed in 0.33 s
const DECEL := 12.0
const TURN := 11.0          # rotation smoothing (1/s)
const GRAVITY := 18.0

var rig: CharacterRig
var camera_rig: CameraRig
var frozen := false
var outfit := "street"
var surface := "concrete"
var interact_target = null     # Interactable or null

var _yaw := 0.0
var _jog := false
var _step_dist := 0.0
var _look_timer := 0.0
var _interactables: Array = []


func _ready() -> void:
	var shape := CapsuleShape3D.new()
	shape.radius = 0.28
	shape.height = 1.72
	var col := CollisionShape3D.new()
	col.shape = shape
	col.position.y = 0.86
	add_child(col)
	floor_snap_length = 0.45
	floor_max_angle = deg_to_rad(48.0)
	floor_constant_speed = true
	floor_block_on_wall = true
	safe_margin = 0.02
	collision_layer = 2
	collision_mask = 1 | 4   # level, and standing NPC bodies


func set_model(path: String) -> void:
	if rig:
		rig.queue_free()
	rig = CharacterRig.new()
	rig.name = "Rig"
	add_child(rig)
	rig.load_model(path)
	CharacterMaterials.apply(rig, GameState.settings.quality)
	rig.rotation.y = _yaw
	_attach_airpod()


var airpods := {}   # "left" / "right" -> Node3D


## The one AirPod Mano still has, in his left ear (the plot of the game).
func _attach_airpod(side := "left") -> void:
	var sk := rig.skeleton
	if sk == null or sk.find_bone("head") == -1:
		return
	var att := BoneAttachment3D.new()
	att.bone_name = "head"
	sk.add_child(att)
	var head_rest := sk.get_bone_global_rest(sk.find_bone("head"))
	var ear_model := head_rest.origin + Vector3(0.074 if side == "left" else -0.074, 0.03, -0.004)
	var pod := Node3D.new()
	pod.position = head_rest.affine_inverse() * ear_model
	att.add_child(pod)
	var white := StandardMaterial3D.new()
	white.albedo_color = Color(0.97, 0.97, 0.96)
	white.roughness = 0.18
	white.clearcoat_enabled = true
	var bud := MeshInstance3D.new()
	var sm := SphereMesh.new()
	sm.radius = 0.0095
	sm.height = 0.019
	bud.mesh = sm
	bud.material_override = white
	pod.add_child(bud)
	var stem := MeshInstance3D.new()
	var cm := CapsuleMesh.new()
	cm.radius = 0.0032
	cm.height = 0.03
	stem.mesh = cm
	stem.position = head_rest.basis.inverse() * Vector3(0.002, -0.017, 0.006)
	stem.material_override = white
	pod.add_child(stem)
	pod.name = "AirPod_" + side
	airpods[side] = pod


func give_second_airpod() -> void:
	if not airpods.has("right"):
		_attach_airpod("right")
	if airpods.has("right"):
		airpods["right"].visible = not stowed


## Both AirPods in their case (the turn: Anisha's SOS), or back in his ears; `both` puts the right one in
## too (the post-credits: back in, then it falls out).
var stowed := false


func stow_airpods(in_case: bool, both := false) -> void:
	stowed = in_case
	if not in_case and both and not airpods.has("right"):
		_attach_airpod("right")
	for side in airpods:
		if is_instance_valid(airpods[side]):
			airpods[side].visible = not in_case


## Detach the right AirPod and let it fall with physics; returns the body (to film it).
func drop_airpod() -> RigidBody3D:
	var pod: Node3D = airpods.get("right")
	if pod == null:
		return null
	var xf := pod.global_transform
	airpods.erase("right")
	var body := RigidBody3D.new()
	body.mass = 0.004
	body.continuous_cd = true   # tiny and fast: don't tunnel through the floor
	body.collision_layer = 0
	body.collision_mask = 1
	var cs := CollisionShape3D.new()
	var sh := CapsuleShape3D.new()
	sh.radius = 0.012
	sh.height = 0.04
	cs.shape = sh
	body.add_child(cs)
	get_tree().current_scene.add_child(body)
	body.global_transform = xf
	pod.get_parent().remove_child(pod)
	body.add_child(pod)
	pod.transform = Transform3D.IDENTITY
	var fwd := Vector3(sin(_yaw), 0, cos(_yaw))
	# it pops out backwards and to his right, away from whatever he is facing
	body.linear_velocity = -fwd * 0.55 + Vector3.UP * 0.45 + Vector3(-fwd.z, 0, fwd.x) * -0.25
	body.angular_velocity = Vector3(randf_range(-8, 8), randf_range(-8, 8), randf_range(-8, 8))
	var pm := PhysicsMaterial.new()
	pm.bounce = 0.45
	pm.friction = 0.6
	body.physics_material_override = pm
	return body



func facing_yaw() -> float:
	return _yaw


func is_jogging() -> bool:
	return _jog and Vector2(velocity.x, velocity.z).length() > 2.0


func teleport(pos: Vector3, yaw: float) -> void:
	global_position = pos
	velocity = Vector3.ZERO
	_yaw = yaw
	if rig:
		rig.rotation.y = yaw
	reset_physics_interpolation()


func face_towards(p: Vector3) -> void:
	var d := p - global_position
	if Vector2(d.x, d.z).length() > 0.05:
		_yaw = atan2(d.x, d.z)


func register_interactables(list: Array) -> void:
	_interactables = list


func _physics_process(dt: float) -> void:
	var input := Vector2.ZERO
	if not frozen:
		input = Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	_jog = Input.is_action_pressed("run") and not frozen
	var walk := rig.stride_speed("walk") * 1.12 if rig else WALK
	var jog := rig.stride_speed("jog") * 1.05 if rig else JOG
	var target_speed := (jog if _jog else walk) * minf(input.length(), 1.0)
	var dir := Vector3.ZERO
	if input.length() > 0.05 and camera_rig:
		var cy := camera_rig.forward_yaw()
		var fwd := Vector3(sin(cy), 0, cos(cy))
		var right := Vector3(-fwd.z, 0, fwd.x)
		dir = (fwd * -input.y + right * input.x).normalized()
	var hv := Vector3(velocity.x, 0, velocity.z)
	var want := dir * target_speed
	var rate := ACCEL if want.length() > hv.length() else DECEL
	hv = hv.lerp(want, 1.0 - exp(-rate * dt))
	if want.length() < 0.01 and hv.length() < 0.05:
		hv = Vector3.ZERO
	velocity.x = hv.x
	velocity.z = hv.z
	if is_on_floor():
		velocity.y = -0.5
	else:
		velocity.y -= GRAVITY * dt
	move_and_slide()

	# face the direction of travel; sharp reversals turn faster
	if dir.length() > 0.1:
		var want_yaw := atan2(dir.x, dir.z)
		var diff := absf(angle_difference(_yaw, want_yaw))
		var k := TURN * (1.6 if diff > 2.0 else 1.0)
		_yaw = lerp_angle(_yaw, want_yaw, 1.0 - exp(-k * dt))
	if rig:
		rig.rotation.y = _yaw
		var speed := Vector2(get_real_velocity().x, get_real_velocity().z).length()
		rig.speed = lerpf(rig.speed, speed, 1.0 - exp(-12.0 * dt))
		_footsteps(speed, dt)


func _footsteps(speed: float, dt: float) -> void:
	if speed < 0.3 or not is_on_floor():
		_step_dist = 0.35
		return
	_step_dist += speed * dt
	var stride := 0.72 if speed < 2.2 else 1.05
	if _step_dist >= stride:
		_step_dist -= stride
		Sfx.footstep(surface, global_position, speed > 2.2)
		stepped.emit(surface, speed > 2.2)


func _process(dt: float) -> void:
	if rig == null:
		return
	# look at the most interesting thing ahead (current interaction target first)
	_look_timer -= dt
	if _look_timer <= 0.0:
		_look_timer = 0.15
		var p = null
		if interact_target != null:
			p = interact_target.look_point()
		rig.look_at_point = p


## Best interactable in range and roughly in front (or very close), for the prompt and the E key.
func find_interactable() -> Variant:
	var best = null
	var best_score := INF
	var fwd := Vector3(sin(_yaw), 0, cos(_yaw))
	for it in _interactables:
		if not it.is_available():
			continue
		var d: Vector3 = it.position_for(global_position) - global_position
		d.y *= 0.5
		var dist := d.length()
		if dist > it.range:
			continue
		var flat := Vector3(d.x, 0, d.z)
		var facing := fwd.dot(flat.normalized()) if flat.length() > 0.01 else 1.0
		if facing < -0.2 and dist > 0.9:
			continue
		# someone walking with Mano is beside or behind him: offered only once he turns to them (or their "Talk to"
		# sits over the pair for the whole walk)
		if it.npc != null and bool(it.npc.get("following")) and facing < 0.5:
			continue
		# who Mano faces wins over who is merely nearer: with the facing counting for only 0.6 m, someone standing 1 m
		# to the side takes the prompt from the person in front of him.
		# Right on top of a spot the direction means nothing (the sofa's euro under his feet, Chloé beside it), so
		# the facing counts in full only from 0.8 m.
		var score := dist + (1.0 - facing) * 2.0 * clampf(dist / 0.8, 0.0, 1.0)
		if score < best_score:
			best_score = score
			best = it
	return best
