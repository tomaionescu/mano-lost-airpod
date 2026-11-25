extends RefCounted
## Dev (autotest=perflens): the frame-time cost of the lens and movement pass (V2-29) measured inside one run, so
## the machine's changing load (other builds, other runs) drops out of the comparison. At the perf spots the pass is
## switched off and on every couple of seconds, and perfwalk's two jogs are run again and again with it off and on
## (off: the v1 post finish and no lens dirt; the imported foliage materials; no falling leaves, dust or fog
## volumes); the median frame times of the two states are compared, with vsync off.
## `lens=v1` runs against plain runs measure the same thing across processes.

const ROUNDS := 8        # samples per state and spot
const SETTLE := 0.6      # seconds after a switch before measuring
const SAMPLE := 1.6      # seconds measured per sample
const WALKS := 4         # jogs per state and route (walks=<n> on the command line)
## With "parts" on the command line each part is also measured alone against the pass off.
const PARTS := {"lens": 1, "foliage": 2, "leaves": 4, "rooms": 8}

var _t: Node             # the autotest node (for wait())
var _game: Node
var _post_mat: ShaderMaterial
var _post_v2: Shader
var _post_v1: Shader
var _dirt: Texture2D
var _sway: Array = []    # [MeshInstance3D, surface, swaying ShaderMaterial]
var _walk_n := WALKS


func run(t: Node, game: Node) -> void:
	_t = t
	_game = game
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	await _t.wait(1.0)
	game.menus.close()
	game.camera_rig.clear_shot(true)
	game.resume()
	_post_mat = (game._post.get_child(0) as ColorRect).material as ShaderMaterial
	_post_v2 = _post_mat.shader
	_post_v1 = load("res://scripts/dev/post_v1.gdshader")
	_dirt = game.world_env.env.glow_map
	for mi: MeshInstance3D in game.level_root.find_children("*", "MeshInstance3D", true, false):
		if mi.mesh == null:
			continue
		for s in mi.mesh.get_surface_count():
			var m := mi.get_surface_override_material(s)
			if m is ShaderMaterial and String(m.resource_name).ends_with("_sway"):
				_sway.append([mi, s, m])
	print("[autotest] perflens quality %s, %d swaying surfaces, leaves %s, sun rooms %d" % [GameState.settings.get("quality", "high"),
		_sway.size(), game.binder.falling_leaves != null, game.binder.sun_fx.size()])
	var spots := [["amphi", game.binder.spawn.origin, 0.0], ["courtyard", Vector3(10, 0.05, 31), PI],
		["street", Vector3(-22, 0.1, 0.0), PI / 2]]
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("walks="):
			_walk_n = maxi(int(arg.substr(6)), 1)
		elif arg == "nospots":   # only the jogs
			spots.clear()
	for sp in spots:
		game.player.teleport(sp[1], sp[2])
		game.camera_rig.snap_behind(game.player.facing_yaw())
		await _t.wait(3.0)
		# one off/on cycle first: the first switch compiles the imported materials' pipelines
		_set_pass(false)
		await _t.wait(1.5)
		_set_pass(true)
		await _t.wait(1.5)
		var on: Array[float] = []
		var off: Array[float] = []
		for i in ROUNDS * 2:
			# ABBA order, so a slow drift in load weighs on both states alike
			var state := (i % 4 == 0) or (i % 4 == 3)
			_set_pass(state)
			await _t.wait(SETTLE)
			var ms: float = await _frame_ms()
			if state:
				on.append(ms)
			else:
				off.append(ms)
		_set_pass(true)
		_report(sp[0], on, off)
	# perfwalk's two jogs (rue Pasteur, then across the courtyard), each WALKS times per state in ABBA order
	var all: int = PARTS.values().reduce(func(a, b): return a | b)
	var runs := [["walk_street", Vector3(-22, 0.1, 0.0), PI / 2], ["walk_courtyard", Vector3(3.0, 0.05, 33.5), PI * 0.75]]
	for r in runs:
		await _walks(r, all, r[0])
	if "parts" in OS.get_cmdline_user_args():
		for part in PARTS:
			await _walks(runs[0], PARTS[part], "%s %s only" % [runs[0][0], part])
	if "teleport" in OS.get_cmdline_user_args():
		# the perf plan's own timing: from the amphi to the courtyard, 2 s to settle, 2.5 s measured (GI re-voxelising
		# the courtyard after the jump is in the sample)
		var on: Array[float] = []
		var off: Array[float] = []
		for i in _walk_n * 2:
			var state := (i % 4 == 0) or (i % 4 == 3)
			_set_pass(state)
			game.player.teleport(game.binder.spawn.origin, 0.0)
			game.camera_rig.snap_behind(game.player.facing_yaw())
			await _t.wait(2.0)
			game.player.teleport(Vector3(10, 0.05, 31), PI)
			game.camera_rig.snap_behind(game.player.facing_yaw())
			await _t.wait(2.0)
			var ms: float = await _frame_ms(2.5)
			if state:
				on.append(ms)
			else:
				off.append(ms)
		_report("teleport_courtyard", on, off)
	_set_pass(true)


## Jogs along `route` with the parts in `mask` on and with the pass off, _walk_n times each in ABBA order.
func _walks(route: Array, mask: int, label: String) -> void:
	var on: Array[float] = []
	var off: Array[float] = []
	for i in _walk_n * 2:
		var state := (i % 4 == 0) or (i % 4 == 3)
		_set_parts(mask if state else 0)
		_game.player.teleport(route[1], route[2])
		_game.camera_rig.snap_behind(_game.player.facing_yaw())
		await _t.wait(2.0)
		Input.action_press("move_forward")
		Input.action_press("run")
		await _t.wait(0.5)
		var ms: float = await _frame_ms(5.0)
		Input.action_release("run")
		Input.action_release("move_forward")
		if state:
			on.append(ms)
		else:
			off.append(ms)
	_report(label, on, off)


func _report(what: String, on: Array[float], off: Array[float]) -> void:
	var a := _median(on)
	var b := _median(off)
	print("[autotest] perflens %s  pass on %.2f ms  off %.2f ms  cost %+.2f ms (%+.1f %%)  on %s  off %s" % [what, a, b, a - b,
		(a - b) / b * 100.0, _fmt(on), _fmt(off)])


## The pass on or off (what lens=v1 leaves out, as far as it can change at run time).
func _set_pass(on: bool) -> void:
	_set_parts(PARTS.values().reduce(func(a, b): return a | b) if on else 0)


## Parts of the pass by PARTS bit: the lens finish (post shader and lens dirt), the swaying foliage, the falling
## leaves, the sunbeam rooms.
func _set_parts(mask: int) -> void:
	var post: bool = (mask & PARTS["lens"]) != 0
	_post_mat.shader = _post_v2 if post else _post_v1
	_game.world_env.env.glow_map = _dirt if post else null
	for e in _sway:
		(e[0] as MeshInstance3D).set_surface_override_material(e[1], e[2] if (mask & PARTS["foliage"]) != 0 else null)
	var leaves: GPUParticles3D = _game.binder.falling_leaves
	if leaves:
		leaves.visible = (mask & PARTS["leaves"]) != 0
		leaves.emitting = leaves.visible
	var sun_up: bool = _game.world_env.sun.visible and _game.world_env.sun_dir.y > 0.0
	for room in _game.binder.sun_fx:
		if is_instance_valid(room):
			if (mask & PARTS["rooms"]) != 0:
				room.set_lit(sun_up)
			else:
				room.visible = false


## Mean frame time (ms) over the next `seconds`.
func _frame_ms(seconds := SAMPLE) -> float:
	var ft := 0.0
	var nf := 0
	while ft < seconds:
		await _t.get_tree().process_frame
		ft += _t.get_process_delta_time()
		nf += 1
	return ft * 1000.0 / maxf(nf, 1)


static func _median(v: Array[float]) -> float:
	var s := v.duplicate()
	s.sort()
	var n := s.size()
	return (s[n / 2] + s[(n - 1) / 2]) * 0.5 if n > 0 else 0.0


static func _fmt(v: Array[float]) -> String:
	var parts := PackedStringArray()
	for x in v:
		parts.append("%.1f" % x)
	return "[" + ", ".join(parts) + "]"
