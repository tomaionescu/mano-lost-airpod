extends "res://scripts/dev/autotest.gd"
## Review harness: the main path played on foot. New game (or chapter=<n>, upto=<n>), then: walk each main
## trigger and objective along the zones' portal routes with real move input (run held, as a player on an errand),
## E at the prompt, every card advanced after it is shown, choice 0 (the critical option), minigames won from
## outside after a shot, sit-downs stood up from after 4 s, the phone skipped. Per chapter it logs the wall time
## spent walking, in talks, cutscenes, minigames and sits, the cards and their characters, the distance walked, and
## every stuck / nudge / teleport fallback, so a human estimate can be built on measured walking. Shots go to
## shots=<dir> as c<chapter>_<name>. Runs with -s (GameState test paths: res://tests/out/), never the user's files.

var _acc := {}          # chapter -> stats
var _ch := -1
var _stuck_total := 0
var _fallbacks := 0
var _lines_seen := 0
var _soft := []
var _tries := {}        # trigger or objective -> visits; a third visit with nothing happening is a soft-lock


func _arg(k: String, def := "") -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with(k + "="):
			return a.substr(k.length() + 1)
	return def


func _s() -> Dictionary:
	var c: int = Chapters.current()
	if not _acc.has(c):
		_acc[c] = {"wall0": Time.get_ticks_msec() / 1000.0, "walk": 0.0, "talk": 0.0, "cut": 0.0, "mini": 0.0, "sit": 0.0,
			"cards": 0, "chars": 0, "hold": 0.0, "think": 0, "m": 0.0, "minis": [], "stuck": 0, "nudge": 0, "fallback": 0, "phone": 0, "routes": 0}
	return _acc[c]


func shot(name: String) -> void:
	await super.shot("c%d_%s" % [Chapters.current(), name])


func _run() -> void:
	while game.mode == "loading":
		await wait(0.25)
	await wait(2.0)
	game.dialogue.line_shown.connect(func(who, text, _e):
		var s := _s()
		s.cards += 1
		s.chars += String(text).length()
		if who == "think":
			s.think += 1
		_lines_seen += 1
		print("[line] c%d %s: %s" % [Chapters.current(), who, text]))
	var start := int(_arg("chapter", "-1"))
	var upto := int(_arg("upto", "99"))
	game.menus.close()
	if start >= 0:
		game.start_chapter(start)
	else:
		game.new_game()
	var t_all := Time.get_ticks_msec() / 1000.0
	var guard := 0
	var idle := 0.0
	while game.mode != "ending" and guard < 900:
		guard += 1
		var c: int = Chapters.current()
		if c != _ch:
			_ch = c
			print("[walk] CHAPTER %d '%s' at %.1f s, time %s clock %s objective '%s'" % [c, Chapters.info().get("title", ""),
				Time.get_ticks_msec() / 1000.0 - t_all, game.world_env.time_of_day, Chapters.clock_text(), game.story.objective()])
			if c > upto:
				break
		var s := _s()
		var t0 := Time.get_ticks_msec() / 1000.0
		if game.mode == "cutscene" or game.mode == "title":
			if game.opening_phase == "chapter_card":
				await wait(2.6)
				await shot("card")
			await wait(0.5)
			s.cut += Time.get_ticks_msec() / 1000.0 - t0
			continue
		if game.mode == "sit":
			await wait(4.0)
			await shot("sit_" + String(game._sit.get("id", "")))
			await _key(KEY_SPACE)
			await wait(1.0)
			s.sit += Time.get_ticks_msec() / 1000.0 - t0
			continue
		if game.mode == "minigame" and game.minigame:
			var mg: String = game.minigame.get_script().resource_path.get_file().get_basename()
			await wait(1.5)
			await shot("mini_" + mg)
			s.minis.append(mg)
			game.minigame._done.call(true)
			await wait(0.6)
			s.mini += Time.get_ticks_msec() / 1000.0 - t0
			continue
		if game.mode == "credits" and game._credits:
			await wait(3.0)
			await shot("credits_a")
			await wait(8.0)
			await shot("credits_b")
			await _key(KEY_E)
			await wait(2.5)
			s.cut += Time.get_ticks_msec() / 1000.0 - t0
			continue
		if game.dialogue.running:
			await _talk_on()
			s.talk += Time.get_ticks_msec() / 1000.0 - t0
			continue
		if game.mode != "play":
			await wait(0.4)
			idle += 0.4
			if idle > 30.0:
				print("[walk] FAIL: mode '%s' for 30 s with no dialogue (chapter %d)" % [game.mode, c])
				_soft.append("mode %s c%d" % [game.mode, c])
				break
			continue
		idle = 0.0
		var due: Array = Chapters.pending_triggers(null, true, INF)
		if not due.is_empty() and due[0].has("near"):
			var r: Dictionary = Chapters.resolve(String(due[0].near), "", game)
			if not r.is_empty():
				var tid := String(due[0].get("id", ""))
				_tries[tid] = int(_tries.get(tid, 0)) + 1
				if _tries[tid] > 3:
					print("[walk] FAIL: trigger %s still due after 3 visits (chapter %d)" % [tid, c])
					_soft.append("trigger %s c%d" % [tid, c])
					await shot("stuck_trigger")
					break
				var why := await _walk_to("trig_" + tid, r.pos, minf(float(due[0].get("radius", 5.0)) * 0.6, 2.0))
				if why == "arrived" and game.mode == "play" and not game.dialogue.running:
					await wait(1.0)   # the game's own poll
					if game.mode == "play" and not game.dialogue.running:
						print("[walk] trigger %s did not fire on arrival at %s (zone %s); teleport like autotest=story" % [tid, game.player.global_position, game.zone_id()])
						s.fallback += 1
						_fallbacks += 1
						game.player.teleport(r.pos + Vector3(0.6, 0.05, 0.6), 0.0)
						await wait(1.0)
				continue
		var t: Dictionary = game.story.target()
		if t.is_empty():
			await wait(1.0)
			if game.dialogue.running or game.mode != "play":
				continue
			print("[walk] FAIL: no objective target and no trigger due in chapter %d, objective '%s'" % [c, game.story.objective()])
			_soft.append("no target c%d '%s'" % [c, game.story.objective()])
			await shot("no_target")
			break
		var okey := "%d|%s" % [c, game.story.objective()]
		_tries[okey] = int(_tries.get(okey, 0)) + 1
		if _tries[okey] > 4:
			print("[walk] FAIL: objective '%s' unchanged after 4 visits (chapter %d)" % [game.story.objective(), c])
			_soft.append("objective '%s' c%d" % [game.story.objective(), c])
			await shot("stuck_objective")
			break
		print("[walk] c%d objective '%s' -> %s at %s" % [c, game.story.objective(), t.label, t.pos])
		var why := await _walk_to("obj", t.pos, 0.8)
		if game.mode != "play" or game.dialogue.running:
			continue
		var it = await _prompt_for(t.pos)
		if it == null:
			print("[walk] no prompt for '%s' at %s from %s: teleport like autotest=story" % [t.label, t.pos, game.player.global_position])
			s.fallback += 1
			_fallbacks += 1
			var p: Vector3 = _free_spot_at(t.pos, 1.0)
			game.player.teleport(p, 0.0)
			game.player.face_towards(t.pos)
			await wait(0.5)
			it = await _prompt_for(t.pos)
			if it == null:
				print("[walk] FAIL: still no prompt for '%s'" % t.label)
				_soft.append("no prompt '%s' c%d" % [t.label, c])
				await shot("no_prompt")
				break
		await shot("prompt_" + String(it.id))
		await _key(KEY_E)
		await wait(0.5)
	var total := Time.get_ticks_msec() / 1000.0 - t_all
	await wait(3.0)
	await shot("end")
	print("[walk] END mode %s chapter %d after %.1f s; stuck %d, fallbacks %d, lines %d, soft-locks %s" % [game.mode, Chapters.current(),
		total, _stuck_total, _fallbacks, _lines_seen, _soft])
	var wsp: float = game.player.rig.stride_speed("walk") * 1.12 if game.player.rig else 1.4
	var jsp: float = game.player.rig.stride_speed("jog") * 1.05 if game.player.rig else 3.5
	print("[walk] speeds: walk %.2f m/s, jog %.2f m/s" % [wsp, jsp])
	for c in _acc:
		var a: Dictionary = _acc[c]
		print("[walk] STATS c%d: walk %.0f s (%.0f m, %.0f s at walking pace), talk %.0f s, cut %.0f s, mini %.0f s %s, sit %.0f s, cards %d (think %d), chars %d, stuck %d, nudges %d, fallbacks %d, phone %d, holds %.0f s" % [
			c, a.walk, a.m, a.m / wsp, a.talk, a.cut, a.mini, a.minis, a.sit, a.cards, a.think, a.chars, a.stuck, a.nudge, a.fallback, a.phone, a.hold])
	get_tree().quit()


## The interactable the prompt offers near `at` (turning to it first), or null.
func _prompt_for(at: Vector3):
	for k in 3:
		game.player.face_towards(at)
		await wait(0.35)
		var it = game.player.find_interactable()
		if it != null and it.position_for(game.player.global_position).distance_to(at) < 1.2:
			return it
		if k == 1:
			var d: Vector3 = at - game.player.global_position
			d.y = 0
			if d.length() > 0.9:
				await hold("move_forward", 0.25)
	return null


func _talk_on() -> void:
	var i := 0
	while game.dialogue.running and i < 200:
		await wait(0.8)
		if game.phone.is_open():
			_s().phone += 1
			await wait(0.8)
			await shot("phone_%s" % game.phone.app)
			print("[walk] phone open at '%s %s', %d unread: skipped" % [game.phone.app, game.phone.thread_id, Chat.total_unread()])
			game.phone.skip()
			await wait(0.4)
			continue
		var held := 0.0
		while game.dialogue.running and game.dialogue.is_holding() and not game.phone.is_open() and held < 14.0:
			await wait(0.2)
			held += 0.2
		_s().hold += held
		if not game.dialogue.running:
			break
		if i % 5 == 0:
			await shot("talk_%03d" % _lines_seen)
		if not game.dialogue._choices.is_empty():
			await wait(0.6)
			print("[walk] choose '%s' of %s" % [game.dialogue._choices[0][0], game.dialogue._choices.map(func(c): return String(c[0]))])
			await shot("choice_%03d" % _lines_seen)
			await _key(KEY_1)
			await wait(0.3)
			if not game.dialogue._choices.is_empty():
				game.dialogue._pick(0)
		else:
			game.dialogue._shown = 9999.0
			game.dialogue._next()
		i += 1


func _route(goal: Vector3) -> Array:
	var here := String(game.binder.zone_at(game.player.global_position).get("id", ""))
	if here == "":
		here = game.zone_id()
	var there := String(game.binder.zone_at(goal).get("id", ""))
	var pts: Array = []
	if here != "" and there != "" and here != there:
		var prev := {here: ""}
		var q: Array = [here]
		while not q.is_empty():
			var z: String = q.pop_front()
			if z == there:
				break
			for nb in game._graph.get(z, []):
				if not prev.has(nb):
					prev[nb] = z
					q.append(nb)
		if prev.has(there):
			var chain: Array = [there]
			while String(prev[chain[0]]) != "":
				chain.push_front(prev[chain[0]])
			for i in chain.size() - 1:
				var pp: Array = game.binder.portals.get("%s|%s" % [chain[i], chain[i + 1]], [])
				if pp.is_empty():
					pp = game.binder.portals.get("%s|%s" % [chain[i + 1], chain[i]], []).duplicate()
					pp.reverse()
				pts.append_array(pp)
			print("[walk] route %s -> %s: %s" % [here, there, chain])
		else:
			print("[walk] route %s -> %s: none" % [here, there])
	pts.append(goal)
	return pts


## Real move input along the route (run held); strafes when blocked, a 1 m nudge after 6 strafes, a teleport to the
## goal after 60 s stuck or 150 s in all (each reported). Stops early when the mode leaves play (a trigger fired).
func _walk_to(tag: String, goal: Vector3, stop_r: float) -> String:
	var s := _s()
	s.routes += 1
	var pts := _route(goal)
	var t := 0.0
	var i := 0
	var last: Vector3 = game.player.global_position
	var still := 0.0
	var stuck := 0
	var next_shot := 3.0
	var why := "timeout"
	Input.action_press("run")
	Input.action_press("move_forward")
	while t < 150.0:
		if game.mode != "play" or game.dialogue.running:
			why = game.mode if game.mode != "play" else "talk"
			break
		var q: Vector3 = pts[i]
		var to: Vector3 = q - game.player.global_position
		to.y = 0
		var r := stop_r if i == pts.size() - 1 else 0.6
		if to.length() < r:
			if i == pts.size() - 1:
				why = "arrived" if absf(q.y - game.player.global_position.y) < 1.5 else "wrong_floor"
				break
			i += 1
			continue
		var want := atan2(to.x, to.z) + PI
		if absf(angle_difference(game.camera_rig.yaw, want)) > 1.0:
			game.camera_rig.yaw = want
			game.player.face_towards(q)
		else:
			game.camera_rig.yaw = lerp_angle(game.camera_rig.yaw, want, 0.5)
		await wait(0.1)
		t += 0.1
		var p: Vector3 = game.player.global_position
		s.m += Vector2(p.x - last.x, p.z - last.z).length()
		still = still + 0.1 if p.distance_to(last) < 0.03 else 0.0
		last = p
		if still > 1.2 and game.mode == "play" and i == pts.size() - 1 and to.length() < 1.7 and absf(q.y - p.y) < 1.5:
			why = "arrived"
			break
		if still > 1.2 and game.mode == "play":
			stuck += 1
			s.stuck += 1
			_stuck_total += 1
			print("[walk] %s: stuck at %s (next %s, zone %s), strafe %d" % [tag, p, q, game.zone_id(), stuck])
			Input.action_release("move_forward")
			await hold("move_back", 0.3)
			await hold("move_right" if stuck % 2 == 1 else "move_left", 0.7)
			Input.action_press("move_forward")
			t += 1.0
			still = 0.0
			var dir: Vector3 = q - p
			dir.y = 0
			if stuck % 6 == 0 and _clear_line(p, p + dir.normalized() * minf(1.3, dir.length())):
				game.player.teleport(p + dir.normalized() * minf(1.0, dir.length()) + Vector3.UP * 0.05, atan2(dir.x, dir.z))
				s.nudge += 1
				print("[walk] %s: NUDGED toward %s" % [tag, q])
			if stuck >= 18:
				break
		if t >= next_shot and game.mode == "play":
			next_shot += 9.0
			await shot("walk_%s_%03d" % [tag, roundi(t)])
	Input.action_release("move_forward")
	Input.action_release("run")
	s.walk += t
	if (why == "timeout" or why == "wrong_floor") and game.mode == "play" and not game.dialogue.running:
		print("[walk] %s: FALLBACK teleport to %s after %.0f s (stuck %d, point %d/%d)" % [tag, goal, t, stuck, i + 1, pts.size()])
		s.fallback += 1
		_fallbacks += 1
		game.player.teleport(_free_spot_at(goal, 1.0), 0.0)
		await wait(0.6)
	print("[walk] %s: %s after %.1f s, point %d/%d, stuck %d, now %s zone %s" % [tag, why, t, i + 1, pts.size(), stuck,
		game.player.global_position, game.zone_id()])
	await wait(0.2)
	return why
