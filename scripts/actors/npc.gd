class_name NPC
extends Node3D
## A named character or a background student: idle / sitting / typing / walking a path,
## turns to face Mano when talking, glances at him when he walks past; chatting or lecturing in between.
## Staging (V2-21): apply_stage() puts a character where a chapter wants them (data/chapters.json "stage", the
## `$ stage` command); follow() walks them on Mano's breadcrumb trail, about 1.6-2.2 m from him: beside and behind
## him (not between him and the follow camera), back onto the trail itself wherever a wall is in the way, and
## teleported to the trail when they fall more than 8 m behind or out of the camera's view; with no body collision
## meanwhile (a follower never blocks a door). A character off stage is hidden and stops processing.

var id := ""
var display_name := ""
var color := Color(0.8, 0.8, 0.8)
var rig: CharacterRig
var interact: Interactable
var def: Dictionary
var talking := false
var crowd := false

var _path: Array = []        # Array[Vector3]
var _path_i := 0
var _path_dir := 1
var _loop := true
var _wait := 0.0
var _speed := 1.25
var _yaw := 0.0
var _home_yaw := 0.0
var _player: Node3D
var _glance := 0.0
var _body: StaticBody3D
var _chat := -1.0
var _chair_yaw := 0.0
## The staging this character is on now (main._restage), so the same staging is not applied twice.
var stage_key := ""
var following := false
var _trail: Array[Vector3] = []   # Mano's positions every TRAIL_STEP metres, oldest first
var _paused_path := false          # staged at a point: the path walk waits until they are home again
var _follow_speed := 1.3
var _side := -1.0                  # the side of Mano a follower walks on: -1 his right, where the follow camera's
                                   # shoulder offset is, so they stay in view
var _goal_t := 0.0
var _goal := Vector3.ZERO
var _goal_vel := Vector3.ZERO      # Mano's velocity when the goal was aimed (the goal moves on with him till the next aim)
const FOLLOW_BEHIND := 0.25        # metres back along the trail (the follow camera is 2.75 m behind Mano: a
const FOLLOW_ASIDE := 1.0          # follower this close and this far aside stays in its view, never in the way)
var _walk_once := false            # walk_to(): stop at the last point, facing _final_yaw
var _final_yaw := 0.0
var _clip_loop := ""               # a staged gesture played again every few seconds (Karim's flyers)
var _clip_t := 0.0
const TRAIL_STEP := 0.4
const LEAVE_WALK := 4.0          # leave_to: metres walked off before going where they are staged
const LEAVE_MAX := 9.0           # ... and seconds at most before they are there anyway
var _leave := {}                 # leave_to in progress: {pos, yaw, st, t}
const FOLLOW_FAR := 2.2
const FOLLOW_LOST := 8.0
var _chair_home: Node3D = null   # their desk chair while they are staged away from it (apply_stage)
var swivel_chair: Node3D:    # office chair under a seated NPC: they turn on it to talk to Mano
	set(c):
		swivel_chair = c
		if c:
			_chair_yaw = c.rotation.y


func setup(d: Dictionary, player: Node3D) -> void:
	def = d
	id = d.get("id", "")
	display_name = d.get("name", id.capitalize())
	color = d.get("color", Color(0.85, 0.85, 0.85))
	crowd = d.get("crowd", false)
	_player = player
	_yaw = d.get("yaw", 0.0)
	_home_yaw = _yaw
	global_position = d.get("pos", Vector3.ZERO)
	rig = CharacterRig.new()
	rig.name = "Rig"
	if randf() < 0.35 and not d.get("sit", false):
		rig.idle_clip = "idle_2"
	add_child(rig)
	rig.load_model("res://assets/characters/%s.glb" % d.get("model", id))
	CharacterMaterials.apply(rig, GameState.settings.quality, 38.0 if d.get("crowd", false) else 55.0)
	rig.rotation.y = _yaw
	rig.sitting = d.get("sit", false)
	if d.has("sit_clip"):
		rig.set_sit_clip(d.sit_clip)
	if d.get("sleep", false):
		rig.set_expression("tired")
		rig.eyes_closed = 1.0
	var s: float = d.get("scale", 1.0)
	rig.scale = Vector3.ONE * s
	_path = d.get("path", [])
	_loop = d.get("loop", true)
	_speed = d.get("speed", rig.stride_speed("walk") * randf_range(0.92, 1.02))
	if not rig.sitting:
		_make_body()
	# "lecturing": speaks on and off like someone chatting, but stands in the plain idle with no talk gestures (their
	# spread arms read as a stiff pose on someone alone at the front of a hall, seen from the back rows)
	if d.get("chatting", false) or d.get("lecturing", false):
		rig.set_conversing(d.get("chatting", false))
		_chat = randf_range(1.0, 5.0)
	if rig.anim_player:
		# desynchronise idles so a crowd never moves in lockstep
		rig.anim_player.seek(randf() * 4.0, true)


## On campus right now: `when` is a condition from data/world.json npc_when (a Conditions expression), or a
## Callable, or absent (always).
func is_present() -> bool:
	var w = def.get("when")
	if w == null or (w is String and w == ""):
		return true
	if w is String:
		return Conditions.eval(w)
	return (w as Callable).call()


## Shows or hides a character whose presence depends on the story (Mme Dupont moves to the accueil). Off stage a
## character stops processing (no animation, no look-at), which costs nothing per frame.
func set_present(on: bool) -> void:
	visible = on
	process_mode = Node.PROCESS_MODE_INHERIT if on else Node.PROCESS_MODE_DISABLED
	if _body:
		_body.collision_layer = 4 if on and not following else 0


## A standing character's body, which Mano bumps into (layer 4).
func _make_body() -> void:
	if _body:
		return
	_body = StaticBody3D.new()
	_body.collision_layer = 4
	_body.collision_mask = 0
	var cs := CollisionShape3D.new()
	var cap := CapsuleShape3D.new()
	cap.radius = 0.26
	cap.height = 1.7
	cs.shape = cap
	cs.position.y = 0.85
	_body.add_child(cs)
	add_child(_body)


## Puts the character at a staged place (a world.json point), facing `yaw`, or back home (`home`: their marker
## or cast position, and their path walk again). `st` may also carry "clip" (an idle clip), "chat" (chatting) and
## "sit" (seated there; a staged place is stood at otherwise, and home is as the cast has them: Toma, seated in
## Amphi 4 in chapters 1-2, stands on the courtyard steps in chapter 3).
func apply_stage(pos: Vector3, yaw: float, st: Dictionary, home := false) -> void:
	# someone on a desk chair (Anisha in SM14) staged away from it (on the courtyard steps, chapter 5) leaves the chair
	# behind: no swivelling about a chair across the campus, and they sit or stand as their staging says; home again,
	# they are back on it
	if swivel_chair and not home and pos.distance_to(swivel_chair.global_position) > 1.5:
		_chair_home = swivel_chair
		swivel_chair = null
		if rig:
			rig.position = Vector3.ZERO
	elif home and _chair_home and swivel_chair == null:
		swivel_chair = _chair_home
		_chair_home = null
	global_position = pos
	_yaw = yaw
	_home_yaw = yaw
	if rig:
		var sit: bool = bool(def.get("sit", false)) if home else bool(st.get("sit", false))
		# a staged seat is a plain one: the seated idle (not the desk's typing), whatever their own seat is
		if sit and rig.sitting == sit and not home and swivel_chair == null:
			rig.set_sit_clip(String(st.get("sit_clip", "sit_idle")))
		elif home and def.has("sit_clip"):
			rig.set_sit_clip(String(def.sit_clip))
		if sit != rig.sitting and swivel_chair == null:
			rig.sitting = sit
			if not sit:
				_make_body()
			if _body:
				_body.collision_layer = 4 if not sit and visible and not following else 0
		rig.rotation.y = yaw
		rig.position = Vector3.ZERO
		if _clip_loop != "" and rig.tree:
			# the staged gesture ends with its staging: someone restaged mid-pickup would stand there bent double, and
			# the conversation would frame the face where the head is then (at waist height)
			rig.tree.set("parameters/gesture/request", AnimationNodeOneShot.ONE_SHOT_REQUEST_FADE_OUT)
		_clip_loop = ""
		if st.has("clip") and rig.has_clip(String(st.clip)):
			rig.play_gesture(String(st.clip))
			_clip_loop = String(st.clip)
			_clip_t = randf_range(2.0, 3.5)
		if st.has("chat"):
			rig.set_conversing(bool(st.chat))
			_chat = randf_range(1.0, 4.0) if bool(st.chat) else -1.0
		# "awake": someone asleep at their desk (the SUP in Amphi 4) staged with their eyes open
		if bool(st.get("awake", false)) and bool(def.get("sleep", false)):
			rig.eyes_closed = 0.0
			rig.set_expression("neutral")
		elif bool(def.get("sleep", false)) and not st.has("awake"):
			rig.eyes_closed = 1.0
			rig.set_expression("tired")
	_paused_path = not home
	_walk_once = false
	if home:
		_path = def.get("path", [])
		_loop = def.get("loop", true)
		_path_i = 0
		_path_dir = 1


## Walks to the last of `points` (through the others) and stops there facing `yaw` (a staged place reached on
## foot, so nobody pops into place in view). No collision is checked on the way: `points` keep to the aisles.
func walk_to(points: Array, yaw: float) -> void:
	_path = [global_position] + points
	_path_i = 1
	_path_dir = 1
	_loop = false
	_walk_once = true
	_final_yaw = yaw
	_home_yaw = yaw
	_paused_path = false
	_wait = 0.0


## Walks off a few metres away from `away_from` (Mano), then, once out of the camera's view (or after LEAVE_MAX
## seconds), is at `pos` facing `yaw` with staging `st`: someone who goes somewhere else after a scene does not pop
## out of the frame (a staging entry with "leave": Ishita after her tour, Ian and Silvia after the pastry summit).
func leave_to(pos: Vector3, yaw: float, away_from: Vector3, st := {}) -> void:
	var dir := global_position - away_from
	dir.y = 0.0
	dir = dir.normalized() if dir.length() > 0.1 else facing_dir()
	var best := global_position
	var best_d := 0.0
	for deg in [0.0, 40.0, -40.0, 80.0, -80.0, 120.0, -120.0]:
		var d := dir.rotated(Vector3.UP, deg_to_rad(deg))
		var reach := _room(global_position, d, LEAVE_WALK)
		if reach > best_d + 0.5:
			best_d = reach
			best = global_position + d * reach
		if reach >= LEAVE_WALK - 0.01:
			break
	_leave = {"pos": pos, "yaw": yaw, "st": st, "t": 0.0}
	if best_d > 0.8:
		var to := best - global_position
		walk_to([best], atan2(to.x, to.z))


## Walking off (leave_to) and not there yet.
func is_leaving() -> bool:
	return not _leave.is_empty()


func _update_leave(dt: float) -> void:
	_leave.t += dt
	var gone := float(_leave.t) > LEAVE_MAX
	var rig_cam = _player.get("camera_rig") if _player else null
	if not gone and rig_cam and rig_cam.cam and float(_leave.t) > 0.6:
		gone = not rig_cam.cam.is_position_in_frustum(global_position + Vector3.UP * 1.0)
	if gone:
		var l := _leave
		_leave = {}
		apply_stage(l.pos, l.yaw, l.st)


## Whether Mano bumps into them (a partner standing at the babyfoot table with him is not solid).
func set_solid(on: bool) -> void:
	if _body:
		_body.collision_layer = 4 if on and visible and not following else 0


## Starts walking behind `target` (Mano) on his breadcrumb trail.
func follow(target: Node3D) -> void:
	_player = target
	if following:
		return
	following = true
	_trail.clear()
	_trail.append(target.global_position)
	if _body:
		_body.collision_layer = 0


## Forget Mano's trail (the follower or Mano was set down somewhere else, under a cut).
func reset_trail() -> void:
	_trail.clear()
	if following and _player:
		_trail.append(_player.global_position)


func unfollow() -> void:
	if not following:
		return
	following = false
	_trail.clear()
	if _body:
		_body.collision_layer = 4 if visible else 0
	if rig:
		rig.speed = 0.0


## One frame of following: keep the trail, walk to their place beside him at his pace (jog when well behind), stand
## when he stands, and jump to a trail point about 2 m behind him when lost (over 8 m away, or out of view over 4 m away).
func _follow_step(dt: float) -> bool:
	var p := _player.global_position
	if not _trail.is_empty() and _trail.back().distance_to(p) > 3.0:
		_trail.clear()   # Mano was moved (a cut, a minigame seat): the old trail leads nowhere he walked
	if _trail.is_empty() or _trail.back().distance_to(p) > TRAIL_STEP:
		_trail.append(p)
		if _trail.size() > 120:
			_trail = _trail.slice(_trail.size() - 120)
	var d := global_position.distance_to(p)
	var seen := true
	var rig_cam = _player.get("camera_rig")
	if rig_cam and rig_cam.cam:
		seen = rig_cam.cam.is_position_in_frustum(global_position + Vector3.UP)
	if d > FOLLOW_LOST or (not seen and d > 4.0):
		_jump_behind(p)
		return false
	# drop the trail points already reached
	while _trail.size() > 1 and global_position.distance_to(_trail[0]) < 0.35:
		_trail.pop_front()
	# where to be: beside and behind Mano (re-aimed 5 times a second, carried on at his velocity in between); the
	# trail itself if a wall is in the way
	var mano_v3 := Vector3.ZERO
	if _player.has_method("get_real_velocity"):
		mano_v3 = _player.get_real_velocity()
		mano_v3.y = 0.0
	var mano_v := mano_v3.length()
	var walking := mano_v > 0.3
	_goal_t -= dt
	if _goal_t <= 0.0:
		_goal_t = 0.2
		_goal = _side_goal(p)
		_goal_vel = mano_v3
		if _blocked(global_position, _goal):
			_goal = _trail[0]
			_goal_vel = Vector3.ZERO
	var goal := _goal + _goal_vel * (0.2 - _goal_t)
	var moving := rig.speed > 0.2
	var to := goal - global_position
	to.y = 0
	var gap := to.length()
	if (gap < 0.25 and not walking) or (not moving and not walking and gap < 0.5 and d < FOLLOW_FAR + 0.6) or d < 0.9:
		var to_m := p - global_position
		_yaw = atan2(to_m.x, to_m.z)
		return false
	# Mano's own pace, plus a catch-up on how far they are from their place beside him (a walk beside him, a jog to
	# catch up; the walk/jog blend follows the speed). Paced on the distance to Mano instead, a follower settles
	# 1.6-1.8 m behind him while he walks, under the bottom edge of the follow camera's frame.
	var walk := rig.stride_speed("walk")
	var spd := clampf(maxf(mano_v, walk * 0.85) + 1.4 * maxf(gap - 0.3, 0.0), walk * 0.85, rig.stride_speed("jog"))
	global_position += to.normalized() * minf(spd * dt, to.length())
	# feet on the floor under them, not at the height of the trail point they walk to: beside Mano on a stair ramp
	# the trail's height is 0.3-0.5 m off (they would float or sink); one short ray a frame
	var fy := _floor_y(global_position, goal.y)
	global_position.y = lerpf(global_position.y, fy, 1.0 - exp(-12.0 * dt))
	# on their place beside him they face the way he walks (aiming at a point a few centimetres off spins them round)
	_yaw = atan2(mano_v3.x, mano_v3.z) if walking and gap < 0.4 else atan2(to.x, to.z)
	_follow_speed = spd
	return true


## The walkable floor (layer 1) under `at`, within 0.9 m above and 1.2 m below `near_y`; `near_y` when none.
func _floor_y(at: Vector3, near_y: float) -> float:
	var from := Vector3(at.x, near_y + 0.9, at.z)
	var q := PhysicsRayQueryParameters3D.create(from, Vector3(at.x, near_y - 1.2, at.z), 1)
	var hit := get_world_3d().direct_space_state.intersect_ray(q)
	return near_y if hit.is_empty() else float(hit.position.y)


## FOLLOW_BEHIND back along Mano's trail and FOLLOW_ASIDE to one side of it (less if a wall is closer; the other
## side if this one has no room).
func _side_goal(p: Vector3) -> Vector3:
	var base := Vector3.INF
	for i in range(_trail.size() - 1, -1, -1):
		if _trail[i].distance_to(p) >= FOLLOW_BEHIND:
			base = _trail[i]
			break
	var back: Vector3
	if base == Vector3.INF:
		var y: float = _player.call("facing_yaw") if _player.has_method("facing_yaw") else 0.0
		back = -Vector3(sin(y), 0, cos(y))
		base = p + back * FOLLOW_BEHIND
	else:
		back = base - p
		back.y = 0
		back = back.normalized() if back.length() > 0.05 else Vector3.BACK
	for attempt in 2:
		var side := Vector3(-back.z, 0, back.x) * _side
		var reach := _room(base, side, FOLLOW_ASIDE)
		if reach > 0.35 or attempt == 1:
			return base + side * reach
		_side = -_side
	return base


## How far (up to `want`) one can step from `at` toward `dir` before a wall or someone standing there (layer 4:
## without it a follower's place beside Mano at the foot of the steps can be inside Toma), keeping 0.35 m from it.
func _room(at: Vector3, dir: Vector3, want: float) -> float:
	var from := at + Vector3.UP * 1.0
	var q := PhysicsRayQueryParameters3D.create(from, from + dir * (want + 0.35), 1 | 4)
	var hit := get_world_3d().direct_space_state.intersect_ray(q)
	if hit.is_empty():
		return want
	return maxf(0.0, from.distance_to(hit.position) - 0.35)


## A wall between two points at waist height (the follower then keeps to the trail itself).
func _blocked(a: Vector3, b: Vector3) -> bool:
	var q := PhysicsRayQueryParameters3D.create(a + Vector3.UP * 0.9, b + Vector3.UP * 0.9, 1)
	return not get_world_3d().direct_space_state.intersect_ray(q).is_empty()


## Lost: onto the trail point nearest 2 m behind Mano (or just behind him), facing him.
func _jump_behind(p: Vector3) -> void:
	var at := -1
	for i in range(_trail.size() - 1, -1, -1):
		if _trail[i].distance_to(p) >= 1.9:
			at = i
			break
	var q: Vector3
	if at >= 0:
		q = _trail[at]
		_trail = _trail.slice(at)
	else:
		var y: float = _player.call("facing_yaw") if _player.has_method("facing_yaw") else 0.0
		q = p - Vector3(sin(y), 0, cos(y)) * 1.9
		_trail.clear()
		_trail.append(p)
	global_position = q
	var to_m := p - q
	_yaw = atan2(to_m.x, to_m.z)
	if rig:
		rig.rotation.y = _yaw


func start_talk() -> void:
	talking = true
	rig.set_conversing(true)
	if _player and (not rig.sitting or swivel_chair):
		var d := _player.global_position - global_position
		var want := atan2(d.x, d.z)
		if rig.sitting:
			# swivel round on the chair, but not all the way through the desk
			want = _home_yaw + clampf(angle_difference(_home_yaw, want), -2.1, 2.1)
		_yaw = want


## Where this character is facing, or turning to face (cameras frame for the end of a turn).
func facing_dir() -> Vector3:
	return Vector3(sin(_yaw), 0, cos(_yaw))


func end_talk() -> void:
	talking = false
	rig.talking = false
	rig.set_conversing(def.get("chatting", false))
	if not rig.sitting or swivel_chair:
		_yaw = _home_yaw


func _process(dt: float) -> void:
	if rig == null:
		return
	# chatting groups take turns talking with small gestures
	if _chat >= 0.0 and not talking:
		_chat -= dt
		if _chat <= 0.0:
			_chat = randf_range(3.0, 7.0)
			rig.talking = not rig.talking and randf() < 0.6
			if rig.talking and randf() < 0.5 and not def.get("lecturing", false):
				rig.play_gesture("talk_1" if randf() < 0.5 else "talk_2")
	if _clip_loop != "" and not talking and not following:
		_clip_t -= dt
		if _clip_t <= 0.0:
			_clip_t = randf_range(2.6, 4.2)
			rig.play_gesture(_clip_loop)
	var moving := false
	if not _leave.is_empty() and not talking:
		_update_leave(dt)
	if following and not talking and _player:
		moving = _follow_step(dt)
	elif not talking and _path.size() >= 2 and not _paused_path:
		moving = _walk(dt)
	rig.speed = lerpf(rig.speed, (_follow_speed if following else _speed) if moving else 0.0, 1.0 - exp(-8.0 * dt))
	rig.rotation.y = lerp_angle(rig.rotation.y, _yaw, 1.0 - exp(-(3.5 if rig.sitting else 7.0) * dt))
	if swivel_chair:
		# turn body and chair together about the chair's column
		var turn := angle_difference(_home_yaw, rig.rotation.y)
		var pivot := swivel_chair.global_position - global_position
		pivot.y = 0
		rig.position = pivot - pivot.rotated(Vector3.UP, turn)
		swivel_chair.rotation.y = _chair_yaw + turn
	# glances: look at Mano when he is close and in front, unless asleep or busy
	if _player and not def.get("sleep", false) and not def.get("no_look", false):
		var to := _player.global_position - global_position
		var fwd := Vector3(sin(rig.rotation.y), 0, cos(rig.rotation.y))
		var near := to.length() < (3.2 if not crowd else 2.2)
		var in_front := fwd.dot(to.normalized()) > -0.1
		if talking or (near and in_front):
			_glance = 3.0
		_glance -= dt
		if _glance > 0.0 and _player.get("rig") and _player.rig:
			rig.look_at_point = _player.rig.head_position()
		else:
			rig.look_at_point = null


func _walk(dt: float) -> bool:
	if _wait > 0.0:
		_wait -= dt
		return false
	var target: Vector3 = _path[_path_i]
	var to := target - global_position
	to.y = 0
	if to.length() < 0.25:
		if _walk_once and _path_i >= _path.size() - 1:
			_walk_once = false
			_paused_path = true
			_yaw = _final_yaw
			return false
		_path_i += _path_dir
		if _path_i >= _path.size() or _path_i < 0:
			if _loop:
				_path_i = 0
			else:
				_path_dir *= -1
				_path_i = clampi(_path_i + _path_dir * 2, 0, _path.size() - 1)
				_wait = randf_range(1.5, 4.0)
		return false
	# politely stop if Mano is in the way
	if _player and _player.global_position.distance_to(global_position + to.normalized() * 0.8) < 0.7:
		return false
	var step := to.normalized() * _speed * dt
	global_position += step
	global_position.y = lerpf(global_position.y, target.y, 1.0 - exp(-6.0 * dt))
	_yaw = atan2(to.x, to.z)
	return true
