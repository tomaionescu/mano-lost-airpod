extends Node
## "1, 2, 3, ACU!" (chapter 4, V2-26, docs/DESIGN.md §3.10): the playground game "1, 2, 3, soleil" with a kebab, in SM14 at
## night. ACU Léo walks along the board, his back to the room, his footsteps on the tiles; Mano, holding the forward
## key, sneaks round the desks with Anisha's kebab (the aisle round the back row, down the east aisle, along the row
## behind Anisha's: world.json sm14_soleil_start -> sm14_pc_stand). When Léo's footsteps stop he says "hm?" and turns
## round: if Mano is still moving then, he is caught and sent back a little. Freezing strikes a pose. After three
## catches Léo gives up ("I saw nothing. Sealed water bottles only.") and stays at the board. A fixed high shot from
## the back corner shows both of them (world.json shot soleil_wide). About 60-90 s; ends with _done.call(true).

const SNEAK := 1.05            # m/s while the key is held
const GRACE := 0.3             # after "hm?", this long to let go before moving counts
const LOOK_MIN := 1.6
const LOOK_MAX := 2.4
const STOP_BEAT := 0.45        # footsteps stop, then "hm?"
const SETBACK := 3.5           # metres back along the way when caught
const GIVE_UP := 3             # catches before Léo sees nothing
const POSES := ["shrug", "look_around", "wave", "pickup"]

var game
var _done: Callable
var path: Array = []           # Mano's way to Anisha's desk, Vector3s
var _len := 0.0
var s := 0.0                   # metres along it
var catches := 0
var phase := "count"           # count (walking, back turned), stop, look, turn_back, gave_up, done
var reached := false
var _t := 0.0
var _phase_t := 0.0
var _look_for := 2.0
var _moving := false
var _speed := 0.0
var _acu: NPC = null
var _line: Array = []          # Léo's pace line along the board
var _step_t := 0.0
var _my_step := 0.0
var _posed := false
var _cam := {}
var _layer: CanvasLayer
var _status: Label
var _count: Label
var log_lines: Array = []


func setup(g, _opts: Dictionary, done: Callable) -> void:
	game = g
	_done = done
	var a := WorldData.point("sm14_soleil_start")
	var b := WorldData.point("sm14_pc_stand")
	var start: Vector3 = a.pos if not a.is_empty() else game.player.global_position
	path = [start]
	for v in WorldData.point("sm14_ishita").get("via", []).slice(3, 6):
		path.append(v)   # Ishita's way in (chapter 1): along the back row, down the east aisle, to the row behind Anisha's
	path.append(b.pos if not b.is_empty() else start)
	_len = 0.0
	for i in range(1, path.size()):
		_len += (path[i] as Vector3).distance_to(path[i - 1])
	game.player.set_physics_process(false)
	game.player.rig.sitting = false
	_place_mano()
	_acu = game.npcs.get("acu")
	var p := WorldData.point("acu_soleil")
	for v in p.get("via", []):
		_line.append(v)
	if _acu and not p.is_empty():
		_acu.apply_stage(p.pos, PI, {})
		_acu.set_present(true)
	var sh: Dictionary = WorldData.section("shots").get("soleil_wide", {})
	if not sh.is_empty():
		_cam = {"from": WorldData.vec(sh.from), "look": WorldData.vec(sh.look), "fov": float(sh.get("fov", 52.0))}
		game.camera_rig.set_shot(_cam.from, _cam.look, _cam.fov, -1.0, true)
	Sfx.music("tension", -14.0)
	_build_ui()
	_begin_count()
	print("[soleil] the way: %.1f m in %d legs; Léo at %s" % [_len, path.size() - 1, _acu.global_position if _acu else Vector3.ZERO])


func _build_ui() -> void:
	_layer = CanvasLayer.new()
	_layer.layer = 15
	add_child(_layer)
	var root := Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.theme = UITheme.theme
	_layer.add_child(root)
	var top := UITheme.over_scene(UITheme.label("1, 2, 3, ACU!", 52, UITheme.marker_title, UITheme.FILM_WHITE), 6, 0.5) as Label
	top.set_anchors_preset(Control.PRESET_CENTER_TOP)
	top.grow_horizontal = Control.GROW_DIRECTION_BOTH
	top.offset_top = 36
	root.add_child(top)
	var how := UITheme.over_scene(UITheme.label("Walk while he walks. Freeze when his footsteps stop.", 30, UITheme.pen, UITheme.FILM_WHITE), 6, 0.5) as Label
	how.set_anchors_preset(Control.PRESET_CENTER_TOP)
	how.grow_horizontal = Control.GROW_DIRECTION_BOTH
	how.offset_top = 104
	root.add_child(how)
	_count = UITheme.over_scene(UITheme.label("", 40, UITheme.marker, UITheme.FILM_WHITE), 6, 0.5) as Label
	_count.set_anchors_preset(Control.PRESET_CENTER)
	_count.grow_horizontal = Control.GROW_DIRECTION_BOTH
	_count.grow_vertical = Control.GROW_DIRECTION_BOTH
	_count.offset_top = -160
	root.add_child(_count)
	var keys := HBoxContainer.new()
	keys.add_theme_constant_override("separation", 10)
	keys.mouse_filter = Control.MOUSE_FILTER_IGNORE
	# bottom right, clear of Léo's lines (the subtitles' place, bottom centre)
	keys.set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)
	keys.grow_horizontal = Control.GROW_DIRECTION_BEGIN
	keys.grow_vertical = Control.GROW_DIRECTION_BEGIN
	keys.offset_right = -56
	keys.offset_bottom = -44
	keys.add_child(UITheme.key_cap(UITheme.action_key("move_forward"), 18))
	keys.add_child(UITheme.over_scene(UITheme.label("hold to sneak to Anisha's desk", 24, UITheme.print_500, UITheme.FILM_WHITE), 5, 0.45))
	root.add_child(keys)
	_status = UITheme.over_scene(UITheme.label("", 24, UITheme.pen, UITheme.MUTED), 5, 0.45) as Label
	_status.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
	_status.grow_vertical = Control.GROW_DIRECTION_BEGIN
	_status.offset_left = 56
	_status.offset_bottom = -44
	root.add_child(_status)


func _place_mano() -> void:
	var at := _at(s)
	var ahead := _at(minf(s + 0.4, _len))
	var d := ahead - at
	var yaw: float = atan2(d.x, d.z) if Vector2(d.x, d.z).length() > 0.01 else game.player.facing_yaw()
	game.player.teleport(at, yaw)


## The point `m` metres along Mano's way.
func _at(m: float) -> Vector3:
	var left := m
	for i in range(1, path.size()):
		var a: Vector3 = path[i - 1]
		var b: Vector3 = path[i]
		var l := a.distance_to(b)
		if left <= l:
			return a.lerp(b, left / maxf(l, 0.001))
		left -= l
	return path[-1]


func _begin_count() -> void:
	phase = "count"
	_phase_t = 0.0
	_posed = false
	_count.text = ""
	if _acu == null or _line.size() < 2:
		return
	# he walks off along the board to somewhere 1.5-4 m away, his back to the room
	var a: Vector3 = _line[0]
	var b: Vector3 = _line[1]
	var here := _acu.global_position
	var to := here
	for _i in 8:
		to = a.lerp(b, randf())
		if to.distance_to(here) >= 1.5 and to.distance_to(here) <= 4.0:
			break
	_acu.walk_to([to], PI)


func _process(dt: float) -> void:
	if phase == "done":
		return
	_t += dt
	_phase_t += dt
	# Mano: the forward key held moves him on along his way
	var hold := Input.is_action_pressed("move_forward") or Input.is_action_pressed("ui_up")
	var want := SNEAK if hold and not reached else 0.0
	_speed = move_toward(_speed, want, dt * 6.0)
	_moving = _speed > 0.08
	if _speed > 0.0:
		s = minf(s + _speed * dt, _len)
		_place_mano()
		_my_step += _speed * dt
		if _my_step > 0.8:
			_my_step = 0.0
			Sfx.footstep("carpet", game.player.global_position, false)
	game.player.rig.speed = _speed
	# the camera keeps its corner, its aim drifting a little toward him
	if not _cam.is_empty():
		var look: Vector3 = _cam.look.lerp(game.player.global_position + Vector3.UP * 1.0, 0.3)
		game.camera_rig.set_shot(_cam.from, look, _cam.fov, -1.0, true)
	_status.text = "Caught: %d of %d" % [catches, GIVE_UP] if catches > 0 and phase != "gave_up" else ""
	match phase:
		"count":
			if _acu:
				_step_t -= dt
				if _step_t <= 0.0 and not _acu._paused_path:
					_step_t = 0.48
					Sfx.footstep("tile", _acu.global_position, false)
				if _acu._paused_path or _phase_t > 6.0:
					phase = "stop"
					_phase_t = 0.0
		"stop":
			if _phase_t >= STOP_BEAT:
				phase = "look"
				_phase_t = 0.0
				_look_for = randf_range(LOOK_MIN, LOOK_MAX)
				_count.text = "Hm?"
				Sfx.ui("ui_hover", 0.0)
				if _acu:
					_acu._yaw = 0.0   # round to face the room
		"look":
			if not _moving and not _posed and _phase_t > 0.1:
				_posed = true
				game.player.rig.play_gesture(POSES[randi() % POSES.size()])   # frozen, mid-pose
			if _phase_t > GRACE and _moving:
				_caught()
			elif _phase_t >= _look_for:
				phase = "turn_back"
				_phase_t = 0.0
				_count.text = ""
				if _acu:
					_acu._yaw = PI
		"turn_back":
			if _phase_t > 0.35:
				_begin_count()
		"gave_up":
			pass
	if s >= _len - 0.05 and not reached:
		reached = true
		_finish()


func _caught() -> void:
	catches += 1
	GameState.flags["acu_catches"] = catches
	game.camera_rig.add_trauma(0.2)
	Sfx.ui("ui_back", 0.0)
	_speed = 0.0
	log_lines.append("caught %d at %.1f m" % [catches, s])
	print("[soleil] caught %d at %.1f of %.1f m (%.1f s)" % [catches, s, _len, _t])
	if catches >= GIVE_UP:
		phase = "gave_up"
		_count.text = ""
		game.dialogue.bark("acu", "I saw nothing. Sealed water bottles only.", 4.0)
		if _acu:
			_acu._yaw = PI   # back to the board for good
		print("[soleil] Léo gives up after %d catches: 'I saw nothing.'" % catches)
		return
	game.dialogue.bark("acu", ["Mano. What's in the bag?", "That bag smells of samouraï.", "I have eyes in the back of my head. And the front."][catches - 1], 2.6)
	s = maxf(s - SETBACK, 0.0)
	_place_mano()
	phase = "turn_back"
	_phase_t = -0.8


func _finish() -> void:
	print("[soleil] at Anisha's desk after %.1f s, %d catches" % [_t, catches])
	phase = "done"
	_count.text = ""
	game.player.rig.speed = 0.0
	var tw := create_tween()
	tw.tween_interval(0.6)
	tw.tween_callback(func(): _done.call(true))


func _exit_tree() -> void:
	# won from outside (the story autotest), or done: Mano at the desk, his own feet back
	if game and game.player:
		if not reached and not path.is_empty():
			s = _len
			_place_mano()
		game.player.rig.speed = 0.0
		game.player.set_physics_process(true)
