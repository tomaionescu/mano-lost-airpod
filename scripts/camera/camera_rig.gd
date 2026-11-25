class_name CameraRig
extends Node3D
## Third-person follow camera with shoulder offset, damping, collision, recentering, handheld sway,
## plus scripted shots (dialogue, minigames, title) that blend in and out with depth of field.

## Radians of turn per screen point at sensitivity 1: 0.0024 per stretched pixel in a maximized 1920-point window,
## where the canvas stretch is 1.2.
const MOUSE_RAD_PER_POINT := 0.002

var target: Node3D            # the player
var world_env: WorldEnv
var cam: Camera3D

var yaw := PI
var pitch := 0.22             # radians, positive = camera above the pivot
var distance := 2.75
var shoulder := 0.42
var pivot_height := 1.52
var input_enabled := true
var recenter := true

var _pivot := Vector3.ZERO
var _dist_now := 2.75
var _idle := 0.0
var _fov_now := 52.0
var _noise := FastNoiseLite.new()
var _t := 0.0
var _trauma := 0.0

# scripted shot state
var _shot = null              # {from, look, fov, focus}
var _blend := 0.0             # 0 = follow camera, 1 = shot
var _blend_speed := 1.6
const BLEND := 1.6            # the gameplay blend in and out of a shot (1 / seconds)
var _drift := Vector3.ZERO    # set_motion: metres a second the shot's camera creeps
var _orbit := 0.0             # set_motion: radians a second it orbits _orbit_center
var _orbit_center := Vector3.ZERO
var _from_look = null          # the last shot's aim point while blending to the next by position and aim
var _from_xform := Transform3D()
var _from_fov := 52.0
var _shot_cut := false


func _ready() -> void:
	cam = Camera3D.new()
	cam.name = "Camera"
	cam.near = 0.05
	cam.far = 600.0
	cam.fov = 52.0
	# the rig places the camera every rendered frame (after the interpolated player), so it must not be interpolated itself
	physics_interpolation_mode = Node.PHYSICS_INTERPOLATION_MODE_OFF
	cam.physics_interpolation_mode = Node.PHYSICS_INTERPOLATION_MODE_OFF
	add_child(cam)
	cam.make_current()
	if world_env:
		world_env.use_camera(cam)   # HiDPI: the world renders at one pixel per point, the UI at native size
	_noise.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	_noise.frequency = 0.25
	process_priority = 100   # after the player has moved


func snap_behind(face_yaw: float) -> void:
	yaw = face_yaw + PI
	if target:
		_pivot = _target_pos() + Vector3.UP * pivot_height
	_dist_now = distance


func _target_pos() -> Vector3:
	return target.get_global_transform_interpolated().origin if target else Vector3.ZERO


func _unhandled_input(event: InputEvent) -> void:
	if not input_enabled or _shot != null:
		return
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		var d := points_moved(event as InputEventMouseMotion)
		var s: float = GameState.settings.mouse_sensitivity * MOUSE_RAD_PER_POINT
		yaw -= d.x * s
		pitch += d.y * s * (-1.0 if GameState.settings.invert_y else 1.0)
		pitch = clampf(pitch, -0.5, 1.2)
		_idle = 0.0


## Mouse travel in screen points. `relative` is scaled by the canvas stretch (so the camera turned slower
## in a bigger window); `screen_relative` is in physical pixels, which macOS multiplies by the max screen
## scale when HiDPI is on. Points are the same on every screen and at every window size.
static func points_moved(e: InputEventMouseMotion) -> Vector2:
	return e.screen_relative / WorldView.pixels_per_point()


func add_trauma(amount: float) -> void:
	_trauma = clampf(_trauma + amount, 0.0, 1.0)


## Blend to a fixed shot. `cut` jumps instantly (shot/reverse-shot cuts in dialogue). With a focus distance the
## shot gets depth of field: `dof` names a WorldEnv.DOF kind ("sit", "insert"...), or the lens picks one.
## `blend_speed` is how fast the blend runs (1 / seconds): BLEND, or a sit-down's slow 0.12 (an 8 s move, V2-14).
## A new shot drops the last one's drift and orbit (set_motion).
func set_shot(from: Vector3, look: Vector3, fov := 40.0, focus := -1.0, cut := false, dof := "", blend_speed := BLEND) -> void:
	if _shot == null or not cut:
		_from_xform = cam.global_transform
		_from_fov = cam.fov
	# a slow blend from one shot to another (a sit-down's medium to its wide) moves the camera and its aim point
	# together, so it keeps looking at what it frames on the way (a turned basis looked at the wall half-way)
	_from_look = _shot.look if _shot != null and not cut and blend_speed < BLEND else null
	_shot = {"from": from, "look": look, "fov": fov, "focus": focus}
	_shot_cut = cut
	_blend_speed = blend_speed
	_drift = Vector3.ZERO
	_orbit = 0.0
	if cut:
		_blend = 1.0
	elif _blend >= 1.0:
		_blend = 0.0
	if world_env:
		var kind := "" if focus <= 0 else (dof if dof != "" else WorldEnv.dof_kind(fov, focus))
		world_env.set_focus_preset(kind, focus)


## A slow move on the current shot (the sit-downs, docs/DESIGN.md §4.1): the camera creeps `drift` metres a second, and
## orbits `orbit_deg` degrees a second about the vertical through `center` (the shot's look point when omitted),
## its look point staying put. Both stop at the next set_shot or clear_shot.
func set_motion(drift := Vector3.ZERO, orbit_deg := 0.0, center = null) -> void:
	_drift = drift
	_orbit = deg_to_rad(orbit_deg)
	_orbit_center = center if center is Vector3 else (_shot.look if _shot != null else Vector3.ZERO)


## The current shot as it stands now (its camera may have crept or orbited): {from, look, fov, focus}, or {}.
func shot_now() -> Dictionary:
	return _shot.duplicate() if _shot != null else {}


func clear_shot(cut := false) -> void:
	if _shot == null:
		return
	_from_xform = cam.global_transform
	_from_fov = cam.fov
	_shot = null
	_blend = 0.0 if cut else 1.0
	_shot_cut = cut
	_blend_speed = BLEND
	_drift = Vector3.ZERO
	_orbit = 0.0
	_from_look = null
	if world_env:
		world_env.set_focus(0.0, false)


func has_shot() -> bool:
	return _shot != null


## What the current shot looks at (the speaker's face in a conversation), or null in the follow camera.
func shot_look():
	return _shot.look if _shot != null else null


func forward_yaw() -> float:
	return yaw + PI


func _process(dt: float) -> void:
	_t += dt
	_idle += dt
	_trauma = maxf(_trauma - dt * 1.2, 0.0)
	# gamepad look
	if input_enabled and _shot == null:
		var look := Input.get_vector("look_left", "look_right", "look_up", "look_down")
		if look.length() > 0.05:
			var ps: float = GameState.settings.pad_sensitivity
			yaw -= look.x * dt * 2.6 * ps
			pitch = clampf(pitch + look.y * dt * 1.8 * ps * (-1.0 if GameState.settings.invert_y else 1.0), -0.5, 1.2)
			_idle = 0.0

	var follow := _follow_transform(dt)
	var follow_fov := _follow_fov(dt)
	if _shot != null:
		if _drift != Vector3.ZERO:
			_shot.from += _drift * dt
		if _orbit != 0.0:
			var arm: Vector3 = _shot.from - _orbit_center
			_shot.from = _orbit_center + arm.rotated(Vector3.UP, _orbit * dt)
		var shot_xf := Transform3D(Basis.looking_at(_shot.look - _shot.from, Vector3.UP), _shot.from)
		_blend = minf(_blend + dt * _blend_speed, 1.0)
		var k := _ease(_blend)
		if _from_look != null and _blend < 1.0:
			var pos := _from_xform.origin.lerp(_shot.from, k)
			var aim: Vector3 = (_from_look as Vector3).lerp(_shot.look, k)
			cam.global_transform = Transform3D(Basis.looking_at(aim - pos, Vector3.UP), pos)
		else:
			cam.global_transform = _from_xform.interpolate_with(shot_xf, k)
		cam.fov = lerpf(_from_fov, _shot.fov, k)
	elif _blend > 0.0:
		_blend = maxf(_blend - dt * _blend_speed, 0.0)
		var k := _ease(_blend)
		cam.global_transform = follow.interpolate_with(_from_xform, k)
		cam.fov = lerpf(follow_fov, _from_fov, k)
	else:
		cam.global_transform = follow
		cam.fov = follow_fov
	_apply_sway(dt)


func _follow_transform(dt: float) -> Transform3D:
	if target == null:
		return cam.global_transform
	var want := _target_pos() + Vector3.UP * pivot_height
	# damping: quick horizontally, slower vertically (stairs, jumps, sitting down)
	var kx := 1.0 - exp(-dt / 0.08)
	var ky := 1.0 - exp(-dt / 0.28)
	_pivot.x = lerpf(_pivot.x, want.x, kx)
	_pivot.z = lerpf(_pivot.z, want.z, kx)
	_pivot.y = lerpf(_pivot.y, want.y, ky)

	# recenter behind the player after a while without camera input, only while walking
	var speed := 0.0
	if target.has_method("get_real_velocity"):
		var v: Vector3 = target.get_real_velocity()
		speed = Vector2(v.x, v.z).length()
	if recenter and _idle > 2.0 and speed > 0.6 and target.has_method("facing_yaw"):
		var want_yaw: float = target.facing_yaw() + PI
		yaw = lerp_angle(yaw, want_yaw, 1.0 - exp(-dt * 0.9 * clampf((_idle - 2.0) / 1.5, 0.0, 1.0)))
		pitch = lerpf(pitch, 0.2, 1.0 - exp(-dt * 0.6))

	var basis := Basis(Vector3.UP, yaw)
	var right := basis.x
	var offset_dir := Vector3(0, sin(pitch), cos(pitch))
	offset_dir = basis * offset_dir
	var origin := _pivot + right * shoulder * 0.35
	var desired_dist := distance
	# collision: sphere sweep from the pivot; snap in, ease back out
	var allowed := _sweep(origin, origin + offset_dir * desired_dist + right * shoulder * 0.65)
	if allowed < _dist_now:
		_dist_now = allowed
	else:
		_dist_now = lerpf(_dist_now, allowed, 1.0 - exp(-dt * 1.6))
	var f := clampf(_dist_now / desired_dist, 0.0, 1.0)
	var pos := origin + offset_dir * _dist_now + right * shoulder * 0.65 * f
	var look_at_p := _pivot + right * shoulder * 0.9 + Vector3.UP * 0.05
	if pos.distance_to(look_at_p) < 0.05:
		pos += offset_dir * 0.05
	return Transform3D(Basis.looking_at(look_at_p - pos, Vector3.UP), pos)


func _sweep(from: Vector3, to: Vector3) -> float:
	var space := get_world_3d().direct_space_state
	var shape := SphereShape3D.new()
	shape.radius = 0.2
	var q := PhysicsShapeQueryParameters3D.new()
	q.shape = shape
	q.transform = Transform3D(Basis(), from)
	q.motion = to - from
	q.collision_mask = 1
	if target is CollisionObject3D:
		q.exclude = [(target as CollisionObject3D).get_rid()]
	var r := space.cast_motion(q)
	var full := from.distance_to(to)
	if r.size() == 0 or r[0] >= 1.0:
		return distance
	return clampf(r[0] * full, 0.35, distance)


func _follow_fov(dt: float) -> float:
	var base: float = GameState.settings.get("fov", 52.0)
	var jog := 0.0
	if target and target.has_method("is_jogging") and target.is_jogging():
		jog = 4.5
	_fov_now = lerpf(_fov_now, base + jog, 1.0 - exp(-dt * 3.0))
	return _fov_now


func _apply_sway(_dt: float) -> void:
	# handheld breathing: a fraction of a degree, slow; stronger in cinematic shots, plus trauma shake
	var amp := deg_to_rad(0.18 + 0.22 * _blend)
	var shake := _trauma * _trauma * deg_to_rad(2.5)
	var rx := _noise.get_noise_2d(_t * 12.0, 0.0) * (amp + shake)
	var ry := _noise.get_noise_2d(0.0, _t * 12.0 + 40.0) * (amp + shake)
	var rz := _noise.get_noise_2d(_t * 12.0 + 90.0, 7.0) * shake * 0.6
	cam.rotate_object_local(Vector3.RIGHT, rx)
	cam.rotate_object_local(Vector3.UP, ry)
	cam.rotate_object_local(Vector3.BACK, rz)


static func _ease(t: float) -> float:
	return t * t * (3.0 - 2.0 * t)
