extends Node
## Dev: drives the game without a player and saves screenshots to res://shots/auto_*.png.
## Godot --path . -- autotest[=plan] [shots=<subdir>] [time=<WorldEnv.TIMES preset>] [sun_nudge=<compass deg>]
##   [chapter=<n>]  (story: start at chapter n from its snapshot or its start_flags, with no dream)
## Autotests keep their own save, settings and snapshots (*.autotest.json, GameState), so they never touch the
## player's.
## Staging plans and options: look (look-ats and passing thoughts are barks: Mano is never frozen), convo
## chapter=<n> (that chapter's staging and start flags first: ids=ishita,joaquin chapter=2), babyfoot
## partner=<id> losses=<n> (2v2, Karim slower, the switch), lostfound (no right pod, C.'s note read), perf nostage
## (everyone at their home place, for an A/B of the staging's cost).
## Phone and sit-down plans: phone (chapter 3's phone: the lock screen at 100 %, the flood, a thread, a reply,
## Cristina's photo, Music, home, Find, the map's pin, the phone key in play and the dead phone before chapter 3),
## sit [ids=a,b] (each sit-down at 0, 10 and 30 s in its chapter's light, then a key: Mano stands within 0.5 s; a
## second sit on the first resumes its song). The story plan reads the phone through (shots, then skip) and stands
## Mano up from a sit-down after a few seconds.
## Cold open, finale and chapter 4 plans: cold_open (new game: the cold open's card, its three shots, the freeze,
## "Six hours earlier.", then chapter 1's card), credits (chapter 5 from the title: the steps, the toast, the group
## photo with every head in its frame, "Want one?", the credits roll with its prints, the post-credits drain, the
## recap), kebab (Joaquin's orders with real keys: two tickets wrong on purpose, Cristina's pencil line, the cook's
## read-back), findmy (the sound search in the Under: rings between the thumps and on one, the signal bar closing
## in, the battery gone, Cristina's phone, the dig), soleil ("1, 2, 3, ACU!": caught three times on purpose, then
## "I saw nothing"), moulinette night [round_time=s] (the night variant: two runs time out, Anisha takes the
## keyboard), shots ids=a,b [mano=<point>] (world.json shots as framed, for checking them). basic and opening wait
## out the cold open; story plays from the cold open to the recap, film photos and the credits included.
## Collectibles and campus-life plans (scripts/dev/autotest_life.gd): ducks, photos, overheard [ids=], looks [ids=]
## [room=] [night], side, idle, chapter_select, journal, map.

var game
var plan := "basic"
var _phone_shots := 0
var _n := 0
var _saving: Array[int] = []


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	_run.call_deferred()


## A Retina window is 3840 px wide and its PNG takes seconds to write, which stalled the game clock and threw
## the scripted shots off: the picture is saved on a worker thread, at one pixel per point unless the
## command line has "fullres".
func shot(name: String) -> void:
	await RenderingServer.frame_post_draw
	var img := get_viewport().get_texture().get_image()
	_n += 1
	var path := "%s/auto_%02d_%s.png" % [shots_dir(), _n, name]
	var k := 1.0 if "fullres" in OS.get_cmdline_user_args() else WorldView.pixels_per_point()
	_saving.append(WorkerThreadPool.add_task(func():
		if k > 1.0:
			img.resize(roundi(img.get_width() / k), roundi(img.get_height() / k), Image.INTERPOLATE_LANCZOS)
		img.save_png(path)))
	print("[autotest] shot ", name, " mode=", game.mode, " pos=", game.player.global_position if game.player else Vector3.ZERO)


func _exit_tree() -> void:
	for t in _saving:
		WorkerThreadPool.wait_for_task_completion(t)


## "shots=<name>" on the command line saves into res://shots/<name>/ (parallel runs keep their screenshots apart)
static func shots_dir() -> String:
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("shots="):
			var d := "res://shots/" + arg.substr(6)
			DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(d))
			return d
	return "res://shots"


func wait(sec: float) -> void:
	await get_tree().create_timer(sec, true, false, true).timeout


func hold(action: String, sec: float) -> void:
	Input.action_press(action)
	await wait(sec)
	Input.action_release(action)


func advance_dialogue(max_lines := 40, shoot_every := 0) -> void:
	var i := 0
	var waited := 0.0
	while not game.dialogue.running and waited < 14.0:
		await wait(0.2)
		waited += 0.2
	while game.dialogue.running and i < max_lines:
		await wait(0.9)
		if game.phone.is_open():
			# the story opened Mano's phone (`$ phone open`): read through it as a player skipping would
			if _phone_shots < 6:
				await wait(0.6)
				await shot("phone_%s" % (game.phone.app if game.phone.app != "thread" else "thread_" + game.phone.thread_id))
				_phone_shots += 1
			print("[autotest]   phone open at '%s %s', %d unread: skipped (mode %s)" % [game.phone.app, game.phone.thread_id, Chat.total_unread(), game.mode])
			game.phone.skip()
			await wait(0.4)
			i += 1
			continue
		# a hold in the scene (`$ wait`, `$ photo`, `$ caption`, a song's preview): let it play out, as a player would
		var held := 0.0
		while game.dialogue.running and game.dialogue.is_holding() and not game.phone.is_open() and held < 12.0:
			await wait(0.2)
			held += 0.2
		if not game.dialogue.running:
			break
		if game.dialogue._text.begins_with("*plink*") and game.dialogue._waiting:
			await shot("plink")
		if shoot_every > 0 and i % shoot_every == 0:
			await shot("dialogue_%d" % i)
		if not game.dialogue._choices.is_empty():
			await wait(1.2)
			print("[autotest]   choose ", game.dialogue._choices[0][0], " buttons=", game.dialogue.choice_box.get_child_count())
			game.dialogue._pick(0)
			print("[autotest]   after choice mode=", game.mode, " minigame=", game.minigame)
		else:
			game.dialogue._shown = 9999.0
			game.dialogue._next()
		i += 1


## autotest=choices: real key events through the input pipeline (GUI focus first, then _unhandled_input)
## against Ian and Silvia's pastry question. The option circled after the moves must be the one picked.
func _choice_keys() -> void:
	await wait(1.0)
	game.menus.close()
	game.resume()
	var d = game.dialogue
	var answers := ["A man of culture.", "FINALLY, someone with taste.", "Haven't seen it. This debate matters more."]
	# [name, moves, confirm key, expected option]
	var cases := [["arrow_down_e", [KEY_DOWN], KEY_E, 1], ["s_s_space", [KEY_S, KEY_S], KEY_SPACE, 2],
		["arrow_up_at_top_e", [KEY_UP, KEY_UP], KEY_E, 0], ["down_down_up_enter", [KEY_DOWN, KEY_DOWN, KEY_UP], KEY_ENTER, 1],
		["w_from_bottom_e", [KEY_DOWN, KEY_DOWN, KEY_DOWN, KEY_W], KEY_E, 1], ["number_3", [], KEY_3, 2]]
	var passed := 0
	for c in cases:
		GameState.flags["choco"] = ""
		var n = game.npcs["ian"]
		game.player.teleport(_free_spot_near(n), 0.0)
		await wait(0.5)
		game.interact(n.interact)
		var guard := 0
		while d.running and d._choices.is_empty() and guard < 10:
			await wait(0.3)
			d._next()
			guard += 1
		await wait(0.5)
		for k in c[1]:
			await _key(k)
		await wait(0.25)
		var circled: int = d._choice_i
		if c[0] == "arrow_down_e" or c[0] == "s_s_space":
			await shot("choices_%s" % c[0])
		await _key(c[2])
		await wait(0.3)
		var ok: bool = d._text == answers[c[3]] and (c[1].is_empty() or circled == c[3])
		passed += 1 if ok else 0
		print("[autotest] choices %s: circled %d, expected %d, next line \"%s\" %s" % [c[0], circled, c[3], d._text, "PASS" if ok else "FAIL"])
		while d.running:
			d._shown = 9999.0
			d._next()
			await wait(0.2)
		await wait(0.8)
	print("[autotest] choices: %d/%d passed" % [passed, cases.size()])
	# lines outside the letterbox (look-ats) with the palest thing in the game behind them: the evening sky
	for v in [["sky_up", Vector3(0, 1.6, 2.0), Vector3(-6, 30, 6)], ["sky_west", Vector3(4, 1.6, 1.0), Vector3(-60, 9, 4)]]:
		game.player.teleport(Vector3(2, 0.1, 6), 0.0)
		game.say([["think", "A bike rack. Every bike on it has a flat tyre. Consistent, at least."], ["toma", "You only have one in? Of course you do.", "grin"]])
		game.camera_rig.set_shot(v[1], v[2], 55.0, -1.0, true)
		await wait(1.0)
		await shot("subtitle_%s_nar" % v[0])
		d._next()
		await wait(1.0)
		await shot("subtitle_%s_toma" % v[0])
		while d.running:
			d._next()
			await wait(0.2)
		await wait(0.5)


## One key press and release, as the keyboard would send it.
func _key(code: Key) -> void:
	for down in [true, false]:
		var ev := InputEventKey.new()
		ev.keycode = code
		ev.physical_keycode = code
		ev.pressed = down
		Input.parse_input_event(ev)
		await get_tree().process_frame
		await get_tree().process_frame


## Mano's capsule fits at `p` (walls, props, people).
func _free_at(p: Vector3) -> bool:
	var probe := PhysicsShapeQueryParameters3D.new()
	var cap := CapsuleShape3D.new()
	cap.radius = 0.3
	cap.height = 1.6
	probe.shape = cap
	probe.collision_mask = 1 | 4 | LevelBinder.CAMERA_OCCLUDERS   # and furniture with no collider (the cafeteria's pastry vitrine)
	probe.transform = Transform3D(Basis(), p + Vector3.UP * 0.9)
	return game.get_world_3d().direct_space_state.intersect_shape(probe, 1).is_empty()


## Where a player would stand to talk to `n`: the free spot 1.3 m away closest to their front.
## Sets shadow_cut_z on every hair_scan ShaderMaterial under root (autotest=closeup nocut); returns how many.
func _set_hair_shadow_cut(root: Node, z: Vector2) -> int:
	var n := 0
	var stack: Array[Node] = [root]
	while not stack.is_empty():
		var node: Node = stack.pop_back()
		stack.append_array(node.get_children())
		var mi := node as MeshInstance3D
		if mi == null or mi.mesh == null:
			continue
		for s in mi.mesh.get_surface_count():
			var m := mi.get_active_material(s) as ShaderMaterial
			if m and m.shader and m.shader.resource_path.contains("hair_scan"):
				m.set_shader_parameter("shadow_cut_z", z)
				n += 1
	return n


## Nothing solid between two places at waist height (a counter between Mano and the one he talks to).
func _clear_line(a: Vector3, b: Vector3) -> bool:
	var q := PhysicsRayQueryParameters3D.create(a + Vector3.UP * 0.9, b + Vector3.UP * 0.9, 1)
	return game.get_world_3d().direct_space_state.intersect_ray(q).is_empty()


## The free spot `r` from `n` with nothing solid between them, within 100° of their front, nearest it; Vector3.INF if none.
func _free_clear_spot(n, r: float) -> Vector3:
	var y: float = n.rig.rotation.y
	var best := Vector3.INF
	var best_off := deg_to_rad(100.0)
	for k in 16:
		var a := y + k * TAU / 16.0
		var p: Vector3 = n.global_position + Vector3(sin(a), 0, cos(a)) * r + Vector3(0, 0.05, 0)
		var off := absf(angle_difference(y, a))
		if off <= best_off and _free_at(p) and _clear_line(n.global_position, p):
			best_off = off
			best = p
	return best


func _free_spot_near(n, r := 1.3) -> Vector3:
	var space: PhysicsDirectSpaceState3D = game.get_world_3d().direct_space_state
	var probe := PhysicsShapeQueryParameters3D.new()
	var cap := CapsuleShape3D.new()
	cap.radius = 0.3
	cap.height = 1.6
	probe.shape = cap
	probe.collision_mask = 1 | 4 | LevelBinder.CAMERA_OCCLUDERS
	var y: float = n.rig.rotation.y
	var best: Vector3 = n.global_position + Vector3(sin(y), 0, cos(y)) * r
	var best_off := INF
	for k in 16:
		var a := y + k * TAU / 16.0
		var p: Vector3 = n.global_position + Vector3(sin(a), 0, cos(a)) * r
		probe.transform = Transform3D(Basis(), p + Vector3.UP * 0.95)
		if space.intersect_shape(probe, 1).is_empty():
			var off := absf(angle_difference(y, a))
			if off < best_off:
				best_off = off
				best = p
	return best + Vector3.UP * 0.05


func _run() -> void:
	if plan == "title" and game.mode == "loading":
		await wait(0.5)
		if game.mode == "loading":
			await shot("loading")   # V2-06: the notebook's cover while the campus loads
	while game.mode == "loading":
		await wait(0.25)
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("time="):   # any plan at another time of day, e.g. autotest=perfwalk time=night
			game.world_env.apply_time(arg.substr(5))
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("lamps="):   # every lamp group at this level (lamps=1: all on, the v1 lamp load)
			for g in game.world_env.lamp_groups():
				game.world_env.set_lamps(g, float(arg.substr(6)))
	if plan == "title":
		await wait(4.0)
		await shot("title_final")
		# V2-06: the printed sheets opened from the title, then the camera further into its drift
		var back_to_title := func(): game.menus.show_title(GameState.has_save(), false)
		# Continue and its "last time" note need a save: one in the courtyard, removed again if it was made here
		var made_save := not GameState.has_save()
		if made_save:
			GameState.write_save(Transform3D(Basis(), Vector3(8.0, 0.1, 27.0)))
		back_to_title.call()
		await wait(0.8)
		await shot("title_continue")
		# V2-33: New game over a save asks first; Esc keeps the night and goes back to the title
		game.menus.confirm_new_game()
		await wait(0.9)
		await shot("title_confirm")
		var focused = game.menus.get_viewport().gui_get_focus_owner()
		print("[autotest] title_confirm: circled '%s'" % (focused.text if focused is Button else "-"))
		await _key(KEY_ESCAPE)
		await wait(0.6)
		var back_on = game.menus.get_viewport().gui_get_focus_owner()
		print("[autotest] title_confirm: Esc -> mode %s, save kept %s, menu '%s'" % [game.mode, GameState.has_save(),
			back_on.text if back_on is Button else "-"])
		if made_save:
			GameState.clear_save()
		game.menus.show_settings(back_to_title)
		await wait(1.0)
		await shot("title_settings")
		game.menus.show_credits(back_to_title)
		await wait(1.0)
		await shot("title_credits")
		back_to_title.call()
		await wait(34.0)
		await shot("title_drift")
		get_tree().quit()
		return
	if plan == "ending":
		await wait(1.0)
		game.menus.close()
		game.resume()
		for k in ["toma", "ines", "karim", "sign", "madame_met", "coffee_given", "found"]:
			GameState.flags[k] = true
		await wait(0.5)
		var n = game.npcs["madame2"]
		game.player.teleport(n.global_position + Vector3(0, 0.05, 1.2), PI)
		await wait(0.4)
		game.say(game.story.ending(), "madame2")
		var k := 0
		while game.dialogue.running and k < 20:
			await wait(1.4)
			await shot("ending_%02d" % k)
			game.dialogue._shown = 9999.0
			game.dialogue._next()
			k += 1
		await wait(1.0)
		await shot("ending_screen")
		await wait(7.5)
		await shot("ending_written")   # the last page once it has written itself
		get_tree().quit()
		return
	if plan == "convo":
		await wait(1.0)
		game.menus.close()
		game.resume()
		GameState.flags["toma"] = true
		_stage_chapter_arg()
		var ids := ["anisha", "ian", "karim"]
		for arg in OS.get_cmdline_user_args():
			if arg.begins_with("ids="):
				ids = Array(arg.substr(4).split(","))
		for id in ids:
			var n = game.npcs[id]
			game.player.teleport(_free_spot_near(n), 0.0)
			await wait(0.5)
			if not game.dialogue.running:   # a trigger by them may have started the conversation already
				game.interact(n.interact)
			await wait(1.5)
			print("[autotest] %s chair=%s home=%.2f yaw=%.2f rig=%.2f rigpos=%s talking=%s player=%s" % [id, n.swivel_chair, n._home_yaw, n._yaw, n.rig.rotation.y, n.rig.position, n.talking, game.player.global_position])
			for k in 3:
				await wait(2.2)
				await shot("convo_%s_%d" % [id, k])
				if game.dialogue._choices.is_empty():
					game.dialogue._shown = 9999.0
					game.dialogue._next()
			while game.dialogue.running:
				if not game.dialogue._choices.is_empty():
					game.dialogue._pick(game.dialogue._choices.size() - 1)
				else:
					game.dialogue._shown = 9999.0
					game.dialogue._next()
				await wait(0.3)
			await wait(1.0)
		get_tree().quit()
		return
	if plan == "choices":
		await _choice_keys()
		get_tree().quit()
		return
	if plan == "voice":
		await _voice_check()
		get_tree().quit()
		return
	if plan == "screens":
		# the menu screens no other plan shows: settings, credits, fits, photo mode
		await wait(2.0)
		game.menus.show_settings(func(): pass)
		await wait(0.8)
		await shot("settings")
		game.menus.show_credits(func(): pass)
		await wait(0.8)
		await shot("credits")
		game.menus.close()
		game.resume()
		await wait(1.0)
		game.menus.show_wardrobe()
		await wait(2.0)
		await shot("fits")
		game.resume()
		game.menus.show_photo()
		await wait(1.5)
		await shot("photo")
		get_tree().quit()
		return
	if plan == "pose":
		await wait(1.0)
		game.menus.close()
		game.resume()
		game.hud.set_hud_visible(false)
		game.player.teleport(Vector3(12, 0.05, 30), PI)
		await wait(0.5)
		var p: Vector3 = game.player.global_position
		game.camera_rig.set_shot(p + Vector3(0.6, 1.3, -2.6), p + Vector3.UP * 1.0, 50.0, -1.0, true)
		await wait(2.0)
		await shot("pose_" + str(OS.get_cmdline_user_args()))
		var tree: AnimationTree = game.player.rig.tree
		print("[autotest] loco params: ", tree.get("parameters/loco/blend_position"), " state ", tree.get("parameters/state/current_state"), " idx ", tree.get("parameters/state/current_index"))
		# walk, then jog, filmed from the side (the camera rig follows the player)
		game.camera_rig.clear_shot(true)
		Input.action_press("move_forward")
		await wait(1.6)
		await shot("pose_walk")
		Input.action_press("run")
		await wait(1.4)
		await shot("pose_jog")
		Input.action_release("run")
		Input.action_release("move_forward")
		await wait(1.0)
		# a path walker
		if game.npcs.has("yanis"):
			var y: Node3D = game.npcs["yanis"]
			var yp := y.global_position
			game.camera_rig.set_shot(yp + Vector3(3.0, 1.5, 1.5), yp + Vector3.UP * 0.9, 45.0, -1.0, true)
			await wait(0.6)
			await shot("pose_yanis")
		get_tree().quit()
		return
	if plan == "closeup":
		# Mano's face in the game's own light (the fringe shadow cut, hair_scan.gdshader shadow_cut_z): front
		# and 3/4 close-ups facing four ways, so the low sun lands on the face from each side. "nocut" switches the cut
		# off on his hair (the fringe's ends then cast onto the lids), for a side-by-side.
		await wait(1.0)
		game.menus.close()
		game.resume()
		game.hud.set_hud_visible(false)
		var nocut: bool = OS.get_cmdline_user_args().has("nocut")
		if nocut:
			print("[autotest] closeup nocut: hair materials ", _set_hair_shadow_cut(game.player, Vector2(-10.0, -9.0)))
		# yaw 0 faces the sun (the low golden-hour sun straight onto the face: the fringe's shadow falls on the lids)
		var to_sun: Vector3 = game.world_env.sun.global_transform.basis.z
		var sun_yaw := atan2(to_sun.x, to_sun.z)
		print("[autotest] closeup to_sun=", to_sun, " sun_yaw=", rad_to_deg(sun_yaw))
		game.player.teleport(Vector3(12, 0.05, 30), sun_yaw)
		await wait(3.0)   # the auto exposure settles after the title
		for deg in [0, 60, -60, 120]:
			var yaw := sun_yaw + deg_to_rad(float(deg))
			game.player.teleport(Vector3(12, 0.05, 30), yaw)
			await wait(1.2)
			var fwd := Vector3(sin(yaw), 0.0, cos(yaw))
			var right := Vector3(-fwd.z, 0.0, fwd.x)
			var look: Vector3 = game.player.rig.head_position() + Vector3.UP * -0.02 + fwd * 0.08
			game.camera_rig.set_shot(look + fwd * 0.62 + Vector3.UP * 0.02, look, 28.0, 0.62, true)
			await wait(0.8)
			await shot("closeup_%s_s%+04d_front" % ["nocut" if nocut else "cut", deg])
			game.camera_rig.set_shot(look + (fwd * cos(0.7) + right * sin(0.7)) * 0.62 + Vector3.UP * 0.02, look, 28.0, 0.62, true)
			await wait(0.6)
			await shot("closeup_%s_s%+04d_34" % ["nocut" if nocut else "cut", deg])
		get_tree().quit()
		return
	if plan == "seats":
		await wait(1.0)
		game.menus.close()
		game.resume()
		game.hud.set_hud_visible(false)
		game.player.teleport(Vector3(0, 0.1, 0), 0.0)
		var who: Array = []
		for id in ["toma", "sleeper", "student2"]:
			if game.npcs.has(id):
				who.append([id, game.npcs[id]])
		var k := 0
		for n in game.crowd:
			if n.rig.sitting and k < 4:
				who.append(["crowd%d" % k, n])
				k += 1
		for w in who:
			var n: Node3D = w[1]
			var p: Vector3 = n.global_position
			var f: Vector3 = n.rig.global_transform.basis.z
			f.y = 0
			f = f.normalized()
			var side := Vector3(-f.z, 0, f.x)
			game.camera_rig.set_shot(p + f * 1.3 + side * 0.5 + Vector3.UP * 1.0, p + Vector3.UP * 0.75, 55.0, -1.0, true)
			await wait(1.6)
			await shot("seat_" + w[0])
		get_tree().quit()
		return
	if plan == "tour":
		await wait(1.0)
		game.menus.close()
		game.resume()
		game.hud.set_hud_visible(false)
		# [name, player position, camera from, look at]
		var views := [
			["street", Vector3(-4, 0.1, 1.5), Vector3(-12, 1.8, 2.5), Vector3(6, 2.5, -2)],
			["voltaire_front", Vector3(-2, 0.1, 0.5), Vector3(4, 1.7, 3.5), Vector3(-6, 4.0, -6)],
			["lobby", Vector3(-14, 0.05, -8), Vector3(-6, 1.7, -7.5), Vector3(-18, 1.2, -10)],
			["accueil", Vector3(-3, 0.05, -21), Vector3(-1, 1.7, -19.5), Vector3(-3.5, 1.1, -24)],
			["sm14", Vector3(-10.8, 3.65, -17.5), Vector3(-6.5, 5.3, -17), Vector3(-13, 4.3, -22)],
			["courtyard", Vector3(10, 0.05, 25), Vector3(20, 1.8, 33), Vector3(4, 2.0, 20)],
			["amphi", Vector3(18.75, -0.75, 14), Vector3(26, 1.5, 17.5), Vector3(14, -1.8, 8)],
			["cafeteria", Vector3(-9.1, 0.05, 42.2), Vector3(-7.0, 1.7, 39.75), Vector3(-11.05, 1.0, 47.55)],
			["under", Vector3(12, -3.55, 43), Vector3(4, -2.0, 41), Vector3(16, -3.0, 47)],
			["ramp", Vector3(18, -1.5, 37.7), Vector3(10, 1.5, 33), Vector3(24, -2.5, 38)],
			# the south side of rue Pasteur and 24 rue Pasteur (player parked beside the camera, clear of KB1's bays)
			["paritalie_v", Vector3(-25.3, 0.1, -3.95), Vector3(-24, 1.7, -4.1), Vector3(-24, 5.5, 14)],
			["paritalie_nw", Vector3(-28.7, 0.1, -3.95), Vector3(-30, 1.7, -4.1), Vector3(-46, 4.5, 7)],
			["passage", Vector3(1.9, 0.1, -3.95), Vector3(3.2, 1.7, -4.1), Vector3(3.2, 3.4, 9)],
			["east_building", Vector3(9.3, 0.1, -4.7), Vector3(10, 1.7, -4.1), Vector3(32, 3.5, 6)],
			["street_west", Vector3(8, 0.1, 2.2), Vector3(6, 1.7, 2.0), Vector3(-30, 2.0, 1.0)],
			["south_gate", Vector3(9, 0.05, 33.0), Vector3(8, 1.7, 34), Vector3(2, 2.4, 48)],
			# KB1 and the neighbourhood (docs/DESIGN.md §8.3, §8.6; player parked in the lobby when the camera is off-limits)
			["kb1_front_east", Vector3(17.5, 0.1, -2.6), Vector3(16, 1.7, -2.4), Vector3(-10, 4.5, -5.5)],
			["kb1_from_court", Vector3(3.5, 0.05, 46.5), Vector3(3.5, 1.7, 43.5), Vector3(3.0, 12.0, -10)],
			["rue_voltaire", Vector3(-3, 0.05, -21), Vector3(-24, 1.7, -47.5), Vector3(0, 9.0, -34)],
			["peripherique", Vector3(-3, 0.05, -21), Vector3(-2, 12.95, -30), Vector3(-6, 6.0, -90)],
			["arpej_junction", Vector3(26.0, 0.1, -1.4), Vector3(27.5, 1.7, -1.2), Vector3(62, 7.0, -6)],
			["sm14_north", Vector3(-11.2, 3.65, -27.5), Vector3(-12.2, 5.3, -30.6), Vector3(-12.2, 3.0, -60)],
			["salengro", Vector3(2.0, 0.05, 46.5), Vector3(2.3, 1.7, 49.6), Vector3(-6, 3.5, 66)],
		]
		for arg in OS.get_cmdline_user_args():
			if arg.begins_with("views="):   # only these views, by name, e.g. views=rue_voltaire,sm14_north
				var keep := Array(arg.substr(6).split(","))
				views = views.filter(func(v): return keep.has(v[0]))
		for v in views:
			game.player.teleport(v[1], 0.0)
			game.camera_rig.set_shot(v[2], v[3], 55.0, -1.0, true)
			await wait(2.2)
			await shot("tour_" + v[0])
		get_tree().quit()
		return
	if plan == "times":
		# every time-of-day preset (WorldEnv.TIMES) from six fixed cameras; the preset changes under the cut
		await wait(1.0)
		game.menus.close()
		game.resume()
		game.hud.set_hud_visible(false)
		# [name, player parked at, camera from, look at]
		var cams := [
			["street_west", Vector3(8, 0.1, 2.2), Vector3(6, 1.7, 2.0), Vector3(-30, 2.0, 1.0)],
			["kb1_front", Vector3(-2, 0.1, 0.5), Vector3(4, 1.7, 3.5), Vector3(-6, 4.0, -6)],
			["passage", Vector3(3.2, 0.1, -4.6), Vector3(3.2, 1.7, -4.1), Vector3(3.2, 3.4, 9)],
			["courtyard", Vector3(10, 0.05, 25), Vector3(20, 1.8, 33), Vector3(4, 2.0, 20)],
			["sm14", Vector3(-10.8, 3.65, -17.5), Vector3(-6.5, 5.3, -17), Vector3(-13, 4.3, -22)],
			["under_ramp", Vector3(18, -1.5, 37.7), Vector3(10, 1.5, 33), Vector3(24, -2.5, 38)],
			# extra, by name only: the courtyard floor in the X's shadow under the sunlit upper floors (question 20)
			["court_east", Vector3(2, 0.05, 23), Vector3(1, 1.7, 22), Vector3(24, 8.0, 31)],
			# the sky over the roofs toward the crescent moon (SSW, 9 degrees up in the blue hour)
			["sky_moon", Vector3(0, 0.1, 0), Vector3(0, 24, 0), Vector3(-62, 39, 77)],
			# the lens and movement pass (V2-29): sunbeams and dust in Amphi 4 and the lobby, plane trees and falling
			# leaves in front of the X, the courtyard birches
			["amphi", Vector3(18.75, -0.75, 14), Vector3(26, 1.5, 17.5), Vector3(14, -1.8, 8)],
			["amphi_dust", Vector3(18.75, -0.75, 14), Vector3(17, 1.6, 15.5), Vector3(11, 2.5, 13)],
			["lobby", Vector3(-14, 0.05, -8), Vector3(-6, 1.7, -7.5), Vector3(-18, 1.2, -10)],
			["trees", Vector3(2, 0.1, -3), Vector3(-8, 1.7, 1.0), Vector3(-26, 4.5, 7.0)],
			["under_tree", Vector3(-6, 0.1, -3), Vector3(-12.5, 1.6, 0.6), Vector3(-17.0, 4.0, 4.0)],
			["court_birch", Vector3(0, 0.05, 28), Vector3(4, 1.6, 28), Vector3(14, 3.2, 26)],
			# over the roofs toward the preset's own sun (look at null), put off centre so the flare's ghosts show
			["sun_flare", Vector3(0, 0.1, 0), Vector3(0, 24, 0), null],
		]
		var by_name := {}
		for c in cams:
			by_name[c[0]] = c
		var order: Array = WorldEnv.TIMES.keys()
		var views: Array = cams.slice(0, 6)
		var blend := 0.0
		for arg in OS.get_cmdline_user_args():
			if arg.begins_with("times="):   # presets in this order (repeats allowed), default all six
				order = Array(arg.substr(6).split(","))
			elif arg.begins_with("cams="):   # cameras by name in this order (repeats allowed)
				views = Array(arg.substr(5).split(",")).map(func(n): return by_name[n])
			elif arg.begins_with("blend="):   # seconds of tween between presets (the chapter-card path)
				blend = float(arg.substr(6))
		for t in order:
			game.world_env.apply_time(t, blend)
			await wait(blend)
			for i in views.size():
				var c: Array = views[i]
				game.player.teleport(c[1], 0.0)
				var look: Vector3 = c[3] if c[3] != null else c[2] + game.world_env.sun_dir.rotated(Vector3.UP, 0.3) * 100.0 + Vector3.DOWN * 12.0
				game.camera_rig.set_shot(c[2], look, 55.0, -1.0, true)
				# the first view after a change also waits for the rebuilt SDFGI to settle
				await wait(5.0 if i == 0 else 2.4)
				if game.mode == "pause":   # the window lost focus (main.gd pauses): back to the view, no menu
					game.resume()
					game.hud.set_hud_visible(false)
					await wait(1.0)
				await shot("times_%s_%s" % [t, c[0]])
		get_tree().quit()
		return
	if plan == "story":
		await _story()
		get_tree().quit()
		return
	if plan == "look":
		await _look_plan()
		get_tree().quit()
		return
	if plan == "approach":
		# trigger conversations put Mano at a talking distance (main._approach)
		await wait(1.0)
		game.menus.close()
		game.camera_rig.clear_shot(true)
		game.resume()
		for id in ["ishita", "ian", "silvia", "karim"]:
			var n = game.npcs[id]
			for off in [Vector3(0.6, 0.05, 0.6), Vector3(4.0, 0.05, 0.0)]:
				game.player.teleport(n.global_position + off, 0.0)
				await wait(0.2)
				game._approach(n)
				await wait(0.2)
				print("[autotest] approach %s from %s: now %.2f m away" % [id, off, game.player.global_position.distance_to(n.global_position)])
		get_tree().quit()
		return
	if plan == "chapters":
		await _chapters_plan()
		get_tree().quit()
		return
	if plan == "cold_open":
		await _cold_open_plan()
		get_tree().quit()
		return
	if plan == "credits":
		await _credits_plan()
		get_tree().quit()
		return
	if plan in ["kebab", "findmy", "soleil"]:
		await _ch4_minigame_plan(plan)
		get_tree().quit()
		return
	if plan == "shots":
		await _shots_plan()
		get_tree().quit()
		return
	if plan == "phone":
		await _phone_plan()
		get_tree().quit()
		return
	if plan == "sit":
		await _sit_plan()
		get_tree().quit()
		return
	if plan == "place":
		await _place_plan()
		get_tree().quit()
		return
	if plan == "perfvar":
		await wait(1.0)
		game.menus.close()
		game.camera_rig.clear_shot(true)
		game.resume()
		var lamps: Array = []
		for l in game.find_children("*", "Light3D", true, false):
			if not (l is DirectionalLight3D) and l.shadow_enabled:
				lamps.append(l)
		var meshes: Array = []
		for n in game.npcs.values() + game.crowd + [game.player]:
			for m in n.find_children("*", "MeshInstance3D", true, false):
				if m.cast_shadow != GeometryInstance3D.SHADOW_CASTING_SETTING_OFF:
					meshes.append(m)
		print("[autotest] shadowed lamps ", lamps.size(), "  shadow-casting character meshes ", meshes.size())
		var env: Environment = game.world_env.env
		for v in ["baseline", "no_lamp_shadows", "no_char_shadows", "no_sdfgi", "scale_050", "no_volfog"]:
			# reset
			for l in lamps:
				l.shadow_enabled = true
			for m in meshes:
				m.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
			env.sdfgi_enabled = true
			env.volumetric_fog_enabled = true
			game.world_env.view_port().scaling_3d_scale = 0.62   # the 3D renders in the WorldView on HiDPI
			match v:
				"no_lamp_shadows":
					for l in lamps:
						l.shadow_enabled = false
				"no_char_shadows":
					for m in meshes:
						m.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
				"no_sdfgi":
					env.sdfgi_enabled = false
				"scale_050":
					game.world_env.view_port().scaling_3d_scale = 0.5
				"no_volfog":
					env.volumetric_fog_enabled = false
			game.player.teleport(Vector3(-22, 0.1, 0.0), PI / 2)
			game.camera_rig.snap_behind(game.player.facing_yaw())
			await wait(2.5)
			Input.action_press("move_forward")
			Input.action_press("run")
			var sum := 0.0
			var n := 0
			var t := 0.0
			while t < 6.0:
				await get_tree().process_frame
				var dt := get_process_delta_time()
				t += dt
				if t > 0.5:
					sum += dt
					n += 1
			Input.action_release("run")
			Input.action_release("move_forward")
			print("[autotest] %s  avg fps %.1f" % [v, n / sum])
		get_tree().quit()
		return
	if plan == "perflens":
		# the cost of the lens and movement pass (V2-29) switched off and on inside one run (scripts/dev/perf_lens.gd)
		var pl = load("res://scripts/dev/perf_lens.gd").new()
		await pl.run(self, game)
		get_tree().quit()
		return
	if plan == "perfwalk":
		# steady-state frame rate while actually playing: jog along rue Pasteur, then across the courtyard
		# (chapter=<n>: that chapter's staging and story lights first)
		await wait(1.0)
		game.menus.close()
		game.camera_rig.clear_shot(true)
		game.resume()
		_stage_chapter_arg()
		if "nolife" in OS.get_cmdline_user_args():
			# for an A/B: the overheard talk, the four world.json ducks and the world.json look-ats off
			game.overheard.process_mode = Node.PROCESS_MODE_DISABLED
			for it in game.ducks._items:
				if WorldData.section("ducks").get(it.id, {}).has("pos"):
					it.node.visible = false
			var ws := WorldData.section("spots")
			game.interactables = game.interactables.filter(func(x): return not (x.kind == "spot" and ws.has(x.id) and x.id != "cristina_note_cafe"))
			game.player.register_interactables(game.interactables)
			print("[autotest] perfwalk nolife: stage 5's overheard talk, new ducks and look-ats off (%d interactables)" % game.interactables.size())
		# "steps": toward the courtyard steps (the eight there in chapter 5, the fairy lights from chapter 3)
		var runs := [["street", Vector3(-22, 0.1, 0.0), PI / 2], ["courtyard", Vector3(3.0, 0.05, 33.5), PI * 0.75],
			["steps", Vector3(2.0, 0.05, 30.0), atan2(-7.0, -8.0)]]
		for r in runs:
			game.player.teleport(r[1], r[2])
			game.camera_rig.snap_behind(game.player.facing_yaw())
			await wait(3.0)
			Input.action_press("move_forward")
			Input.action_press("run")
			var worst := 1000.0
			var sum := 0.0
			var n := 0
			var t := 0.0
			while t < 7.0:
				await get_tree().process_frame
				var dt := get_process_delta_time()
				t += dt
				if t > 0.5:
					worst = minf(worst, 1.0 / maxf(dt, 0.0001))
					sum += dt
					n += 1
			Input.action_release("run")
			Input.action_release("move_forward")
			print("[autotest] %s %s  avg fps %.1f  worst frame %.1f fps  frames %d  end %s" % [GameState.settings.quality, r[0], n / sum, worst, n, game.player.global_position])
		get_tree().quit()
		return
	if plan == "perfab":
		await wait(1.0)
		game.menus.close()
		game.camera_rig.clear_shot(true)
		game.resume()
		GameState.set_setting("quality", "high")
		game.player.teleport(Vector3(10, 0.05, 31), PI)
		game.camera_rig.snap_behind(game.player.facing_yaw())
		var rigs: Array = []
		for n in game.npcs.values() + game.crowd:
			if n.rig:
				rigs.append(n.rig)
		print("[autotest] rigs ", rigs.size())
		var steps := ["baseline", "no_face", "no_anim", "no_npcs"]
		for st in steps:
			if st == "no_face":
				for r in rigs:
					r.set_process(false)
			elif st == "no_anim":
				for r in rigs:
					r.tree.active = false
			elif st == "no_npcs":
				for r in rigs:
					r.visible = false
			await wait(4.0)
			print("[autotest] %s fps %d  process %.1f ms  draws %d" % [st, Engine.get_frames_per_second(), Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0,
				RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_DRAW_CALLS_IN_FRAME)])
		get_tree().quit()
		return
	if plan.begins_with("perf"):
		# frame times, not the display's 60 Hz; on HiDPI the 3D renders in the WorldView's viewport
		DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
		var vp3: Viewport = game.world_env.view_port()
		RenderingServer.viewport_set_measure_render_time(vp3.get_viewport_rid(), true)
		await wait(1.0)
		print("[autotest] 3d view %s, lens finish in %s" % [vp3.name, game._post.get_parent().name])
		game.menus.close()
		game.camera_rig.clear_shot(true)
		game.resume()
		var qs := ["low", "medium", "high", "ultra"]
		if "scale" in plan:
			qs = ["high"]
		for arg in OS.get_cmdline_user_args():
			if arg.begins_with("qs="):   # only these presets, e.g. qs=high for a quick before/after
				qs = Array(arg.substr(3).split(","))
		var saved_quality: String = GameState.settings.get("quality", "high")
		if "nostage" in OS.get_cmdline_user_args():
			# for an A/B: everyone at their own place, the new friends off stage
			GameState.flags["stage_over"] = {"karim": "home", "ian": "home", "silvia": "home", "ishita": "hide", "joaquin": "hide", "cristina": "hide"}
		game._refresh_presence()
		var on_stage: Array = []
		for id in game.npcs:
			if game.npcs[id].visible:
				on_stage.append(id)
		print("[autotest] perf cast on stage (%s): %s" % ["nostage" if "nostage" in OS.get_cmdline_user_args() else "chapter 1 staging", on_stage])
		# the amphi (spawn) and the busiest exterior view: courtyard towards Amphi 4 with the crowd
		var spots := [["amphi", game.binder.spawn.origin, 0.0], ["courtyard", Vector3(10, 0.05, 31), PI]]
		for q in qs:
			GameState.set_setting("quality", q)
			for sp in spots:
				game.player.teleport(sp[1], sp[2])
				game.camera_rig.snap_behind(game.player.facing_yaw())
				for sc in ([0.5, 0.42, 0.36] if "scale" in plan else [-1.0]):
					if sc > 0:
						vp3.scaling_3d_scale = sc
					await wait(2.0)
					var ft := 0.0
					var nf := 0
					while ft < 2.5:
						await get_tree().process_frame
						ft += get_process_delta_time()
						nf += 1
					var vrid := vp3.get_viewport_rid()
					print("[autotest] %s %s scale %.2f win %s 3d %s  frame %.2f ms  cpu_render %.1f ms  gpu %.1f ms  process %.1f ms  fps %d  draws %d  vram %d MB" % [q, sp[0], vp3.scaling_3d_scale, DisplayServer.window_get_size(),
						vp3.get("size"), ft * 1000.0 / nf,
						RenderingServer.viewport_get_measured_render_time_cpu(vrid), RenderingServer.viewport_get_measured_render_time_gpu(vrid),
						Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0, Engine.get_frames_per_second(),
						RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_DRAW_CALLS_IN_FRAME),
						RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_VIDEO_MEM_USED) / 1048576])
		GameState.set_setting("quality", saved_quality)
		get_tree().quit()
		return
	if plan in ["moulinette", "babyfoot", "coffee", "lostfound"]:
		await wait(1.0)
		game.menus.close()
		game.camera_rig.clear_shot(true)
		game.resume()
		await wait(0.5)
		var mg_opts := {}
		if plan == "moulinette" and "night" in OS.get_cmdline_user_args():
			mg_opts["night"] = true   # a bool, as c4.dlg's `night=true` reaches it
			mg_opts["sit_at"] = "pcSeat"   # as c4.smuggled starts it: at Anisha's desk, 23:05, the `late` light
			game.world_env.apply_time("late")
			GameState.flags["clock"] = Conditions.minutes("23:05")
			for arg in OS.get_cmdline_user_args():
				if arg.begins_with("round_time="):
					mg_opts["round_time"] = float(arg.substr(11))
		if plan == "babyfoot":
			for arg in OS.get_cmdline_user_args():
				if arg.begins_with("partner="):
					GameState.flags["foot_partner"] = arg.substr(8)
					mg_opts["partner"] = arg.substr(8)
				elif arg.begins_with("losses="):
					GameState.flags["foot_losses"] = int(arg.substr(7))
			game._refresh_presence()
		game.start_minigame(plan, mg_opts, func(r): print("[autotest] minigame result ", r))
		await wait(1.5)
		if plan == "babyfoot":
			var bf = game.minigame
			print("[autotest] babyfoot: partner '%s' (%s), switched %s, Karim at %d %%, partner at the table %s" % [bf.partner,
				"2v2" if bf.partner != "" else "1v1", bf.switched, roundi(bf.karim_k * 100.0),
				bf._pnpc.global_position if bf._pnpc else "-"])
		await shot(plan + "_a")
		if plan == "coffee":
			for i in 8:
				Input.action_press("confirm")
				await wait(0.06)
				Input.action_release("confirm")
				await wait(0.06)
		elif plan == "babyfoot":
			await hold("move_back", 0.4)
			await wait(1.5)
		elif plan == "lostfound":
			var lf = game.minigame
			var right := 0
			for it in lf._items:
				right += 1 if it.def.get("right", false) else 0
			print("[autotest] lostfound: %d items, %d joke pods, %d right pods, %d empty slot" % [lf._items.size(),
				lf._items.filter(func(it): return not it.def.get("read", false)).size(), right,
				lf._items.filter(func(it): return it.def.get("read", false)).size()])
			Input.action_press("move_right")
			await wait(0.1)
			Input.action_release("move_right")
			await wait(0.8)
			# a joke pod picked: Mme Dupont's reply
			if not lf._items[lf._sel].def.get("read", false):
				await _key(KEY_E)
				await wait(0.6)
				await shot("lostfound_wrong")
			# two more wrong pods (real key events: the minigame reads input events), then Mme Dupont's nudge
			# picks the empty slot and C.'s note comes up
			var guard := 0
			while not lf._items[lf._sel].def.get("read", false) and guard < 8:
				await _key(KEY_D)
				await wait(0.3)
				if not lf._items[lf._sel].def.get("read", false):
					await _key(KEY_E)
					await wait(0.4)
				guard += 1
			print("[autotest] lostfound: %d wrong picks, slot selected %s, reply '%s'" % [lf._wrong, lf._items[lf._sel].def.get("read", false), lf._reply.text])
			await wait(0.8)
			await shot("lostfound_note")
			print("[autotest] lostfound: the slot picked, note shown %.2f: %s" % [lf._note.modulate.a, lf.NOTE_TEXT.replace("\n", " / ")])
			await _key(KEY_E)
			await wait(1.2)
			print("[autotest] lostfound: note read %s, desc '%s'" % [lf._read, lf._desc.text])
		elif plan == "moulinette" and mg_opts.has("night"):
			# the night variant left alone: the hint after 12 s, two runs time out, then Anisha takes the keyboard
			var mo = game.minigame
			var t0 := Time.get_ticks_msec() / 1000.0
			var shot_hint := false
			var shot_anisha := false
			while game.minigame != null and Time.get_ticks_msec() / 1000.0 - t0 < 120.0:
				await wait(0.25)
				if is_instance_valid(mo) and mo._hinted and not shot_hint:
					shot_hint = true
					await shot("moulinette_night_hint")
					print("[autotest] moulinette night: hint at %.1f s: %s" % [Time.get_ticks_msec() / 1000.0 - t0, mo._foot.text])
				if is_instance_valid(mo) and mo.anisha_typing and not shot_anisha:
					shot_anisha = true
					await wait(1.0)
					await shot("moulinette_night_anisha")
					print("[autotest] moulinette night: Anisha at the keyboard at %.1f s after %d runs KO" % [Time.get_ticks_msec() / 1000.0 - t0, mo.runs_failed])
			print("[autotest] moulinette night: over after %.1f s, minigame %s" % [Time.get_ticks_msec() / 1000.0 - t0, game.minigame])
		elif plan == "moulinette":
			Input.action_press("ui_down_alt")
			await wait(0.1)
			Input.action_release("ui_down_alt")
			await wait(0.5)
		await shot(plan + "_b")
		get_tree().quit()
		return
	if plan == "hud":
		await _hud_plan()
		get_tree().quit()
		return
	if plan == "dream":
		await _dream_frames()
		get_tree().quit()
		return
	if plan == "opening":
		await _opening_plan()
		get_tree().quit()
		return
	# scripts/dev/autotest_life.gd: collectibles, life on campus, the look-ats, chapter select, the journal
	if plan in ["ducks", "photos", "overheard", "looks", "side", "idle", "chapter_select", "journal", "map"]:
		await wait(1.0)
		var life = load("res://scripts/dev/autotest_life.gd").new(self)
		match plan:
			"ducks":
				await life.ducks()
			"photos":
				await life.photos()
			"overheard":
				await life.overheard()
			"looks":
				await life.looks()
			"side":
				await life.side()
			"idle":
				await life.idle()
			"chapter_select":
				await life.chapter_select()
			"journal":
				await life.journal()
			"map":
				await life.map()
		await wait(1.0)
		get_tree().quit()
		return
	await wait(3.5)   # the first title's amphi fades up behind the menu (main.TITLE_SETTLE + 1.8 s)
	await shot("title")
	game.new_game()
	await _past_cold_open(true)   # the cold open first, then chapter 1's card (opening_phase "card")
	await wait(2.6)   # the chapter card fully written
	await shot("card")
	await _past_dream()
	await wait(1.6)   # the desk shot's beat (main.WAKE_HOLD), then the close-up
	await shot("wake_blur")
	await wait(1.6)
	await shot("wake_sharp")
	await advance_dialogue(30, 3)
	await wait(1.5)
	await shot("play")
	await hold("move_forward", 2.5)
	await shot("walk")
	await hold("run", 0.1)
	Input.action_press("run")
	await hold("move_forward", 2.0)
	Input.action_release("run")
	await shot("jog")
	game.menus.show_journal()
	await wait(1.6)
	await shot("journal")
	game.resume()
	game.menus.show_map()
	await wait(0.6)
	await shot("map")
	game.resume()
	game.menus.show_pause()
	await wait(0.6)
	await shot("pause")
	game.menus.show_settings(func(): game.menus.show_pause(false))
	await wait(0.8)
	await shot("pause_settings")
	game.resume()
	await wait(0.5)
	get_tree().quit()


## autotest=hud (V2-05): the HUD in Mano's pen. The walking hint and the prompt's pen ring and leader line on a
## friend and on a spot; an objective changed during a conversation, played once it ends (struck through,
## written on, underlined) with two toasts and the next hints; the journal key held; the waypoint, switched on
## for this run only (the setting is not saved), on screen and off it; then a sheet of every doodle.
func _hud_plan() -> void:
	await wait(1.0)
	game.menus.close()
	GameState.reset_flags()
	GameState.flags["toma"] = true
	game.camera_rig.clear_shot(true)
	game.resume()
	game.hud.set_objective(game.story.objective(), false)
	var ian = game.npcs["ian"]
	game.player.teleport(_free_spot_near(ian), 0.0)
	game.player.face_towards(ian.global_position)
	game.camera_rig.snap_behind(game.player.facing_yaw())
	await wait(1.8)
	await shot("hud_prompt_npc")
	for id in ["coffee", "coin_planter"]:
		var s: Dictionary = game.binder.spots.get(id, {})
		if s.is_empty():
			continue
		game.player.teleport(_free_spot_at(s.pos, 1.3), 0.0)
		game.player.face_towards(s.pos)
		game.camera_rig.snap_behind(game.player.facing_yaw())
		await wait(1.4)
		print("[autotest] prompt on %s: %s" % [id, game.hud.prompt._words])
		await shot("hud_prompt_" + id)
	# a conversation that moves the story on: the strip waits for it to end, then plays
	game.player.teleport(_free_spot_near(ian), 0.0)
	game.player.face_towards(ian.global_position)
	game.camera_rig.snap_behind(game.player.facing_yaw())
	await wait(0.5)
	game.say([["mano", "Okay. Karim, then."], func():
		game.story.setf("ines", true)
		game.toast("+1 €", "coin")
		game.story.clue("Karim (BDE) picked up something white near my seat.")], "ian")
	await wait(1.6)
	await shot("hud_hidden_in_convo")
	while game.dialogue.running:
		game.dialogue._shown = 9999.0
		game.dialogue._next()
		await wait(0.3)
	# the letterbox leaves in 0.5 s, then the strip lands (0.22 s), strikes (0.22 s), writes, underlines
	await wait(0.85)
	await shot("hud_objective_a_strike")
	await wait(0.4)
	await shot("hud_objective_b_write")
	await wait(1.1)
	await shot("hud_objective_c_done")
	game.toast("Golden rubber duck 1/8", "duck")
	await wait(0.5)
	await shot("hud_toasts_peel")
	# the journal key held: the strip comes back and stays
	await wait(6.5)
	await _key_down(KEY_TAB, true)
	await wait(1.0)
	await shot("hud_peek")
	await _key_down(KEY_TAB, false)
	await wait(2.5)
	# the waypoint, for this run only
	GameState.settings["waypoint"] = true
	await wait(0.3)
	var wp = game.hud.waypoint_target
	if wp != null:
		game.player.face_towards(wp)
		game.camera_rig.snap_behind(game.player.facing_yaw())
		await wait(1.2)
		await shot("hud_waypoint_on")
		game.player.face_towards(game.player.global_position * 2.0 - (wp as Vector3))
		game.camera_rig.snap_behind(game.player.facing_yaw())
		await wait(1.2)
		await shot("hud_waypoint_edge")
	GameState.settings["waypoint"] = false
	# every doodle on a sheet of paper, and over the scene
	var sheet := Control.new()
	sheet.set_anchors_preset(Control.PRESET_FULL_RECT)
	sheet.draw.connect(func():
		# on paper: each doodle large (96) and at toast size (34); below, over the scene in film white
		sheet.draw_rect(Rect2(Vector2.ZERO, Vector2(sheet.size.x, 600.0)), UITheme.PAPER)
		var i := 0
		for id: String in Doodles.IDS:
			var at := Vector2(70 + (i % 10) * 148, 40 + floori(i / 10.0) * 280)
			Doodles.draw(sheet, id, Rect2(at, Vector2(96, 96)), Doodles.ink(id), 2.4)
			sheet.draw_string(UITheme.pen, at + Vector2(0, 132), id, HORIZONTAL_ALIGNMENT_LEFT, -1, 22, UITheme.PENCIL)
			Doodles.draw(sheet, id, Rect2(at + Vector2(0, 160), Vector2(34, 34)), Doodles.ink(id), 2.0)
			Doodles.draw(sheet, id, Rect2(Vector2(at.x, 640 + floori(i / 10.0) * 80), Vector2(40, 40)), UITheme.FILM_WHITE, 1.8, 0, Color(UITheme.INK_SHADOW, 0.55))
			i += 1)
	game.hud.root.add_child(sheet)
	await wait(0.5)
	await shot("hud_doodles")
	sheet.queue_free()


## A free spot `r` metres from `p` where Mano can stand (the side nearest the camera's usual angle first).
func _free_spot_at(p: Vector3, r: float) -> Vector3:
	var space: PhysicsDirectSpaceState3D = game.get_world_3d().direct_space_state
	var probe := PhysicsShapeQueryParameters3D.new()
	var cap := CapsuleShape3D.new()
	cap.radius = 0.3
	cap.height = 1.6
	probe.shape = cap
	probe.collision_mask = 1 | 4
	for k in 12:
		var a := k * TAU / 12.0
		var q := p + Vector3(sin(a), 0, cos(a)) * r
		probe.transform = Transform3D(Basis(), q + Vector3.UP * 0.95)
		if space.intersect_shape(probe, 1).is_empty():
			return q + Vector3.UP * 0.05
	return p + Vector3(0, 0.05, r)


## A key going down or up through the whole input pipeline.
func _key_down(code: Key, down: bool) -> void:
	var ev := InputEventKey.new()
	ev.keycode = code
	ev.physical_keycode = code
	ev.pressed = down
	Input.parse_input_event(ev)
	await get_tree().process_frame


## Plays the whole story: walk (teleport) to each objective, interact, answer with the first choice,
## win every minigame, until the ending screen. Chapter cards are waited out (and shot once each, with the light
## preset logged); main triggers due are visited before the next target. chapter=<n> starts at chapter n.
func _story() -> void:
	await wait(1.0)
	var start := _chapter_arg()
	if start > 0:
		game.start_chapter(start)
		await wait(0.5)
	else:
		game.new_game()
	await _past_cutscene()
	await advance_dialogue(60, _dlg_shots())
	await shot("story_start")
	var guard := 0
	var last_ch := -1
	var carded := {}
	var logged := {}
	while game.mode != "ending" and guard < 300:
		guard += 1
		await wait(0.6)
		var ch: int = Chapters.current()
		if ch != last_ch:
			last_ch = ch
			print("[autotest] chapter %d (%s), time %s, clock %s" % [ch, Chapters.info().get("title", ""), game.world_env.time_of_day, Chapters.clock_text()])
		if game.mode == "cutscene":
			if game.opening_phase == "chapter_card" and not carded.has(ch):
				carded[ch] = true
				await wait(2.4)   # the card fully written (it comes up after a 0.6 s fade to black)
				print("[autotest] chapter %d card '%s': time %s (applied under the card), clock %s" % [ch,
					Chapters.info().get("card", {}).get("chapter", ""), game.world_env.time_of_day, Chapters.clock_text()])
				await shot("chapter_%d_card" % ch)
			continue
		if game.mode == "sit":
			# a sit-down the story offered (choice 0 sits): a few seconds of it, then any key stands Mano up
			var sid := String(game._sit.get("id", ""))
			await wait(4.0)
			await shot("sit_" + sid)
			var t0 := Time.get_ticks_msec() / 1000.0
			await _key(KEY_SPACE)
			var waited := 0.0
			while game.mode == "sit" and waited < 2.0:
				await get_tree().process_frame
				waited = Time.get_ticks_msec() / 1000.0 - t0
			print("[autotest] sit %s: stood up after %.2f s, mode %s, moments %s" % [sid, Time.get_ticks_msec() / 1000.0 - t0, game.mode,
				GameState.flags.get("moments", [])])
			continue
		if game.mode == "minigame" and game.minigame:
			print("[autotest] winning minigame ", game.minigame.get_script().resource_path.get_file())
			if game.minigame.get("partner") != null:
				print("[autotest] babyfoot %s: partner '%s', switched %s, Karim at %d %%" % ["2v2" if game.minigame.partner != "" else "1v1",
					game.minigame.partner, game.minigame.switched, roundi(game.minigame.karim_k * 100.0)])
			if game.minigame.get("_items") != null:
				print("[autotest] lost & found: %d items, right pods %d, empty slot %d" % [game.minigame._items.size(),
					game.minigame._items.filter(func(it): return it.def.get("right", false)).size(),
					game.minigame._items.filter(func(it): return it.def.get("read", false)).size()])
			var mg_name: String = game.minigame.get_script().resource_path.get_file().get_basename()
			if mg_name == "moulinette":
				print("[autotest] moulinette: night %s" % game.minigame.night)
			await wait(1.0)
			await shot("mini_" + mg_name)
			game.minigame._done.call(true)
			await wait(0.5)
			await advance_dialogue(60, _dlg_shots())
			for k in ["lf_twist", "karim", "ines", "summit_done", "cristina_texted"]:
				if GameState.flags.get(k, false) and not logged.has(k):
					logged[k] = true
					print("[autotest] flag %s set (time %s, clock %s, foot_partner '%s')" % [k, game.world_env.time_of_day, Chapters.clock_text(),
						GameState.flags.get("foot_partner", "")])
			continue
		if game.mode == "credits" and game._credits:
			# the credits: two frames of the roll, the prints and the names it shows, then a key runs it to its end
			await wait(2.5)
			await shot("credits_a")
			await wait(9.0)
			await shot("credits_b")
			print("[autotest] credits: %d prints %s, names %s, camera at %s" % [game._credits.shown_prints.size(),
				game._credits.shown_prints.map(func(p): return String(p).get_file()), game._credits.names, game.camera_rig.cam.global_position.snapped(Vector3.ONE * 0.1)])
			await _key(KEY_E)
			await wait(2.5)
			continue
		if game.dialogue.running:
			if GameState.flags.get("found", false) and Chapters.current() < 4:
				# ending: walk through it slowly and film the AirPod drop
				var k := 0
				while game.dialogue.running and k < 20:
					await wait(1.3)
					if game.dialogue._text.begins_with("*plink*") or game.dialogue._text.begins_with("FINALLY"):
						await shot("ending_%d" % k)
					game.dialogue._shown = 9999.0
					game.dialogue._next()
					k += 1
				continue
			await advance_dialogue(60, _dlg_shots())
			_log_c3(logged)
			_log_c45(logged)
			continue
		if game.mode != "play":
			continue
		# a main trigger due (chapters.json): go where it fires and let the game's own poll start it
		var due: Array = Chapters.pending_triggers(null, true, INF)
		if not due.is_empty() and due[0].has("near"):
			var r: Dictionary = Chapters.resolve(String(due[0].near), "", game)
			if not r.is_empty():
				var tid := String(due[0].get("id", ""))
				print("[autotest] chapter %d trigger %s near %s" % [ch, tid, r.pos])
				game.player.teleport(r.pos + Vector3(0.6, 0.05, 0.6), 0.0)
				await wait(0.8)
				if game.dialogue.running:
					await wait(0.8)
					await shot("trigger_" + tid)
				if tid == "ishita_sm14" and game.npcs.has("ishita"):
					var ish = game.npcs["ishita"]
					print("[autotest] Ishita arrives at SM14 with Mano: %.1f m from him, zone '%s', in the conversation %s; on their marks: Mano %.2f m, Ishita %.2f m off" % [
						ish.global_position.distance_to(game.player.global_position), game.binder.zone_at(ish.global_position).get("id", ""),
						not game._conv.is_empty() and game._conv.npc == ish,
						Vector2(game.player.global_position.x, game.player.global_position.z).distance_to(Vector2(WorldData.point("sm14_meet_mano").pos.x, WorldData.point("sm14_meet_mano").pos.z)),
						Vector2(ish.global_position.x, ish.global_position.z).distance_to(Vector2(WorldData.point("sm14_meet_ishita").pos.x, WorldData.point("sm14_meet_ishita").pos.z))])
				continue
		var t: Dictionary = game.story.target()
		if t.is_empty():
			break
		print("[autotest] chapter %d objective: %s -> %s at %s" % [ch, game.story.objective(), t.label, t.pos])
		var to: Vector3 = t.pos
		# stand where a player would: in front of an NPC, or on the hotspot itself
		var p: Vector3 = to + Vector3(0, 0.05, 0)
		for id in game.npcs:
			var n = game.npcs[id]
			if n.is_present() and n.global_position.distance_to(to) < 0.2:
				var y: float = n.rig.rotation.y
				p = to + Vector3(sin(y), 0, cos(y)) * 1.1 + Vector3(0, 0.05, 0)
				if not _free_at(p) or not _clear_line(n.global_position, p):
					# a free spot on their side of whatever is in front of them, nearest their front (Ian faces the
					# cafeteria till: in front of him, then 1.95 m on, Mano stood in the pastry vitrine or behind the
					# counter); none: across a counter from them (Karim behind the Under's bar, chapter 3), or the free
					# spot nearest their front
					var side := _free_clear_spot(n, 1.3)
					var far := to + Vector3(sin(y), 0, cos(y)) * 1.95 + Vector3(0, 0.05, 0)
					p = side if side != Vector3.INF else (far if _free_at(far) else _free_spot_near(n))
		game.player.teleport(p, 0.0)
		game.player.face_towards(to)
		await wait(0.4)
		var target = game.player.find_interactable()
		if target == null:
			print("[autotest] nothing to interact with near ", t.label)
			game.player.teleport(to + Vector3(0.4, 0.05, 0.0), 0.0)
			await wait(0.3)
			target = game.player.find_interactable()
		if target:
			print("[autotest]   interact ", target.id)
			game.interact(target)
			await wait(0.3)
			await advance_dialogue(60, _dlg_shots())
			_log_c3(logged)
			_log_c45(logged)
	_log_c45(logged)
	await wait(4.0)   # the recap page written on
	await shot("story_end")
	print("[autotest] recap: %s" % [game.menus.recap_shown])
	print("[autotest] story finished: mode=", game.mode, " chapter=", Chapters.current(), " time=", game.world_env.time_of_day,
		" clock=", Chapters.clock_text(), " flags=", GameState.flags)


## Chapters 4 and 5's beats as the story passes them (once each): the meeting, the orders, the empty pocket, the
## search, found, Anisha's SOS and the case, the smuggle, the night moulinette, the steps, the toast, the group photo
## (with where each head is in its frame), the AirPod given, the credits.
func _log_c45(logged: Dictionary) -> void:
	var f := GameState.flags
	for k in ["cold_open_seen", "met_cristina", "kebab_done", "pocket_empty", "searching", "found", "anisha_sos", "airpods_case", "smuggled",
			"mouli_night", "c4_done", "toast_done", "group_photo", "c5_done", "credits_done"]:
		if bool(f.get(k, false)) and not logged.has("c45:" + k) and (k != "found" or Chapters.current() >= 4):
			logged["c45:" + k] = true
			print("[autotest] beat %s (chapter %d, clock %s, time %s): finder '%s %s', AirPods %s, kebab %d/%d wrong %s, given_to '%s', film %d" % [
				k, Chapters.current(), Chapters.clock_text(), game.world_env.time_of_day, f.get("finder_place", ""), f.get("finder_time", ""),
				"case" if f.get("airpods_case", false) else ("two" if game.player.airpods.has("right") else "one"),
				int(f.get("kebab_score", 0)), int(f.get("kebab_total", 0)), f.get("kebab_wrong", []), f.get("given_to", ""), int(f.get("film_shots", 0))])
			if k == "group_photo":
				var heads: Dictionary = game.group_photo.get("heads", {})
				var inside := heads.values().filter(func(h): return h != null).size()
				print("[autotest] group photo: %d of %d heads in the frame %s -> %s" % [inside, heads.size(), heads, game.group_photo.get("path", "")])


## Chapter 3's beats as the story passes them (once each): the phone charged, the flood, the finder, Cristina's note
## and message, the tour's stops and Ishita's favourite, the summit, the playlist, 20:40 at night.
func _log_c3(logged: Dictionary) -> void:
	var f := GameState.flags
	var beats := [["phone_charged", f.get("phone_charged", false)], ["flood", "flood" in f.get("chat_batches", [])],
		["finder", String(f.get("finder_place", "")) != ""], ["cristina_note", f.get("cristina_note", false)],
		["cristina_texted", f.get("cristina_texted", false)], ["touring", f.get("touring", false)],
		["tour_done", int(f.get("tour_count", 0)) >= 3], ["summit_done", f.get("summit_done", false)],
		["playlist", String(f.get("playlist", "")) != ""], ["c3_done", f.get("c3_done", false)]]
	for b in beats:
		if bool(b[1]) and not logged.has("c3:" + String(b[0])):
			logged["c3:" + String(b[0])] = true
			print("[autotest] chapter 3 beat %s (clock %s, time %s): chat %s unread %d, finder '%s %s', tour %d %s fav '%s', playlist '%s', moments %s" % [
				b[0], Chapters.clock_text(), game.world_env.time_of_day, f.get("chat_batches", []), Chat.total_unread(),
				f.get("finder_place", ""), f.get("finder_time", ""), int(f.get("tour_count", 0)),
				["amphi", "sofa", "stickers", "velib", "vending", "bay"].filter(func(x): return f.get("tour_" + x, false)),
				f.get("ishita_fav", ""), f.get("playlist", ""), f.get("moments", [])])


## autotest=look (V2-10): look-ats made of Mano's thoughts are barks. At each spot: interact, then check Mano is
## not frozen, the mode is still play and a bark shows, and that he walks on while it does; then a passing thought
## (a bark trigger) in the street with Ishita behind him. Prints PASS/FAIL per check.
func _look_plan() -> void:
	await wait(1.0)
	game.menus.close()
	game.camera_rig.clear_shot(true)
	game.resume()
	GameState.flags["toma"] = true
	var passed := 0
	var total := 0
	for id in ["velib", "slide", "logo", "sign"]:
		var s: Dictionary = game.binder.spots.get(id, {})
		if s.is_empty():
			continue
		game.player.teleport(_free_spot_at(s.pos, 1.0), 0.0)
		game.player.face_towards(s.pos)
		game.camera_rig.snap_behind(game.player.facing_yaw())
		await wait(0.6)
		var it = null
		for c in game.interactables:
			if c.id == id:
				it = c
		if it == null:
			continue
		game.interact(it)
		await wait(0.3)
		var p0: Vector3 = game.player.global_position
		var ok: bool = not game.player.frozen and game.mode == "play" and game.dialogue.is_barking()
		print("[autotest] look %s: think-only %s, frozen %s, mode %s, bark '%s'" % [id, DialogueData.is_think_only("use." + id),
			game.player.frozen, game.mode, game.dialogue.bark_text()])
		await shot("look_" + id)
		# walk while the thought shows: the farthest he gets in any of four directions (a spot may be in a corner)
		var moved := 0.0
		for dir in ["move_back", "move_left", "move_forward", "move_right"]:
			await hold(dir, 0.45)
			moved = maxf(moved, game.player.global_position.distance_to(p0))
		ok = ok and moved > 0.25
		total += 1
		passed += 1 if ok else 0
		print("[autotest] look %s: walked %.2f m while the thought showed: %s" % [id, moved, "PASS" if ok else "FAIL"])
		var t := 0.0
		while game.dialogue.is_barking() and t < 12.0:
			await wait(0.25)
			t += 0.25
	# a passing thought (chapters.json think_street): Ishita behind him on rue Pasteur
	GameState.flags["ishita_met"] = true
	GameState.flags["camera"] = false
	GameState.flags["following"] = ["ishita"]
	game._refresh_presence()
	game.player.teleport(Vector3(3.3, 0.1, 1.0), PI * 0.5)
	game.camera_rig.snap_behind(game.player.facing_yaw())
	game.npcs["ishita"].global_position = Vector3(3.3, 0.0, 4.0)   # as if walking with him out of the passage
	await wait(0.6)
	await hold("move_forward", 1.6)
	await wait(0.4)
	var ish = game.npcs.get("ishita")
	var trig_ok: bool = "think_street" in GameState.flags.get("triggers_fired", []) and not game.player.frozen and game.mode == "play"
	total += 1
	passed += 1 if trig_ok else 0
	print("[autotest] look think_street: fired %s, frozen %s, Ishita following %s at %.1f m: %s" % [
		"think_street" in GameState.flags.get("triggers_fired", []), game.player.frozen, ish.following if ish else false,
		ish.global_position.distance_to(game.player.global_position) if ish else -1.0, "PASS" if trig_ok else "FAIL"])
	await shot("look_think_street")
	await hold("move_forward", 2.5)
	await shot("look_follow")
	await wait(1.5)
	await shot("look_follow_stopped")
	print("[autotest] look follow: Ishita %.1f m behind after walking, solid %s" % [ish.global_position.distance_to(game.player.global_position),
		ish._body.collision_layer != 0 if ish and ish._body else false])
	print("[autotest] look follow (1.5 s after stopping): Ishita at %s visible %s in view %s, Mano at %s, camera at %s, rig %s" % [ish.global_position, ish.is_visible_in_tree(),
		game.camera_rig.cam.is_position_in_frustum(ish.global_position + Vector3.UP), game.player.global_position, game.camera_rig.cam.global_position,
		ish.rig.global_position if ish.rig else Vector3.ZERO])
	print("[autotest] look: %d/%d passed" % [passed, total])


## chapter=<n>: that chapter's start flags (over the current ones) and its staging, for a plan that is not story.
func _stage_chapter_arg() -> void:
	var ch := _chapter_arg()
	if ch <= 0 or not Chapters.has(ch):
		return
	var sf: Dictionary = Chapters.get_chapter(ch).get("start_flags", {})
	for k in sf:
		GameState.flags[k] = GameState._copy(sf[k])
	GameState.flags["chapter"] = ch
	# flags=a,b on the command line: those flags set too before the staging (ACU Léo in SM14 needs anisha_sos)
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("flags="):
			for k in arg.substr(6).split(","):
				GameState.flags[k] = true
	game._apply_stage(Chapters.get_chapter(ch))
	print("[autotest] chapter %d staging applied" % ch)


## dlgshots=<n> on the command line: the story plan shoots every n-th dialogue line (0: none).
static func _dlg_shots() -> int:
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("dlgshots="):
			return int(arg.substr(9))
	return 0


## chapter=<n> on the command line, or -1.
static func _chapter_arg() -> int:
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("chapter="):
			return int(arg.substr(8))
	return -1


## Waits while the opening or a chapter card plays (mode "cutscene"), at most `limit` seconds.
func _past_cutscene(limit := 40.0) -> void:
	var t := 0.0
	await wait(0.3)
	while game.mode == "title" and t < 3.0:   # New game fades to black for 0.5 s before the opening starts
		await wait(0.1)
		t += 0.1
	t = 0.0
	while game.mode == "cutscene" and t < limit:
		await wait(0.2)
		t += 0.2


## autotest=chapters (V2-36): every chapter in data/chapters.json started from the title as chapter select will
## (its snapshot or start_flags, no dream): its card mid-way, then its first frame of play or conversation, with
## the light preset, clock and main to-do logged.
func _chapters_plan() -> void:
	await wait(3.5)
	for n in Chapters.numbers():
		game.start_chapter(n)
		await wait(2.4)
		await shot("chapter_%d_card" % n)
		if n == 0:
			# the cold open is chapter 0: its card, then its shots, then chapter 1's own opening (card, dream, wake-up)
			print("[autotest] chapters: 0 card (the cold open), mode %s, time %s, clock %s" % [game.mode, game.world_env.time_of_day, Chapters.clock_text()])
			await _past_cold_open(false)
			await wait(2.4)
			await shot("chapter_0_then_1_card")
			print("[autotest] chapters: 0 hands over to chapter %d's card, time %s, clock %s" % [Chapters.current(), game.world_env.time_of_day, Chapters.clock_text()])
			var w := 0.0
			while not game.dialogue.running and w < 40.0:
				await wait(0.5)
				w += 0.5
			while game.dialogue.running:
				game.dialogue._shown = 9999.0
				if not game.dialogue._choices.is_empty():
					game.dialogue._pick(0)
				else:
					game.dialogue._next()
				await wait(0.2)
			await wait(0.6)
			game.show_title()
			await wait(1.5)
			continue
		print("[autotest] chapters: %d card '%s', mode %s, time %s, clock %s" % [n, Chapters.get_chapter(n).get("card", {}).get("chapter", ""),
			game.mode, game.world_env.time_of_day, Chapters.clock_text()])
		await _past_cutscene()
		await wait(1.2)
		await shot("chapter_%d_first" % n)
		print("[autotest] chapters: %d first frame, mode %s, objective '%s', snapshot %s" % [n, game.mode, game.story.objective(),
			GameState.read_chapter_save(n) != null])
		while game.dialogue.running:
			game.dialogue._shown = 9999.0
			if not game.dialogue._choices.is_empty():
				game.dialogue._pick(0)
			else:
				game.dialogue._next()
			await wait(0.2)
		if game.minigame:
			game.minigame._done.call(true)
			await wait(0.3)
		await wait(0.6)
		game.show_title()
		await wait(1.5)


## autotest=phone (V2-24): chapter 3 from the title; its start cue charges the phone (the lock screen), floods it
## and opens Messages: the list with the unread counts, the steps thread at the first unread and at its end, a
## reply (option 0) and the reactions, the promo chat with Cristina's photo, Music, the home screen; then Find and
## the map's pin; in play the phone key (Q) opens it and Esc puts it away; before chapter 3 it is the dead phone.
func _phone_plan() -> void:
	await wait(1.0)
	game.start_chapter(3)
	await _past_cutscene()
	var done := {}
	var guard := 0
	while game.dialogue.running and guard < 300:
		guard += 1
		await wait(0.35)
		if game.phone.state == "lock" and not done.has("lock") and game.phone.charged:
			done["lock"] = true
			await wait(0.9)
			await shot("phone_lock")
		if game.phone.is_open():
			if game.phone.app == "messages" and not done.has("flood"):
				done["flood"] = true
				await wait(0.8)
				print("[autotest] phone: Messages, %d unread in %s, mode %s" % [Chat.total_unread(), Chat.active_threads().map(func(x): return "%s %d" % [x, Chat.unread(x)]), game.mode])
				await shot("phone_flood_list")
				game.phone._go("thread", "steps")
				await wait(0.9)
				await shot("phone_thread_steps")
				game.phone._scroll.scroll_vertical = 100000
				await wait(0.5)
				await shot("phone_thread_steps_end")
				game.phone.reply(0)
				await wait(1.8)
				game.phone._scroll.scroll_vertical = 100000
				await wait(0.4)
				print("[autotest] phone: replied '%s' in steps; sent %s" % [GameState.flags.get("reply_steps", ""), GameState.flags.get("chat_sent", []).size()])
				await shot("phone_reply")
				game.phone._go("thread", "promo")
				await wait(0.9)
				await shot("phone_thread_promo")
				game.phone._go("music")
				await wait(0.6)
				await shot("phone_music")
				game.phone._go("home")
				await wait(0.6)
				await shot("phone_home")
				game.phone.skip()
				continue
			if game.phone.app == "find" and not done.has("find"):
				done["find"] = true
				await wait(1.0)
				print("[autotest] phone: Find, '%s %s'" % [GameState.flags.get("finder_place", ""), GameState.flags.get("finder_time", "")])
				await shot("phone_find")
				game.phone.close()
				continue
			game.phone.skip()
			continue
		if game.dialogue.is_holding():
			continue
		if not game.dialogue._choices.is_empty():
			game.dialogue._pick(0)
		else:
			game.dialogue._shown = 9999.0
			game.dialogue._next()
		await wait(0.5)
	await wait(1.0)
	game.menus.show_map()
	await wait(1.2)
	await shot("phone_map_pin")
	game.resume()
	await wait(1.0)
	# the phone key in play
	await _key(KEY_Q)
	await wait(0.8)
	print("[autotest] phone key in play: mode %s, phone %s at '%s'" % [game.mode, game.phone.state, game.phone.app])
	await shot("phone_play_home")
	await _key(KEY_ESCAPE)
	await wait(0.6)
	print("[autotest] Esc on the home screen: mode %s, phone %s" % [game.mode, game.phone.state])
	# before chapter 3: the dead phone and Mano's thought
	GameState.flags["phone_charged"] = false
	game.phone.restore(false)
	await _key(KEY_Q)
	await wait(0.7)
	print("[autotest] phone key before the charge: mode %s, phone %s, bark '%s'" % [game.mode, game.phone.state, game.dialogue.bark_text()])
	await shot("phone_dead")


## autotest=sit [ids=a,b] (V2-14): every sit-down in data/world.json in its chapter's light (time= overrides), Mano
## set down near it and sat: shots at 0, 10 and 30 s (cam A, the blend to the wide, the wide's slow move), the HUD
## hidden; then a key, and how long until he is playable and on his feet; a second sit on the first one checks the
## song resumes where it was left.
func _sit_plan() -> void:
	await wait(1.0)
	game.menus.close()
	game.camera_rig.clear_shot(true)
	game.resume()
	var ids: Array = WorldData.sit_ids()
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("ids="):
			ids = Array(arg.substr(4).split(","))
	var forced := ""
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("time="):
			forced = arg.substr(5)
	var light := {1: "golden", 2: "last_light", 3: "blue", 4: "night", 5: "late"}
	var first_song := ""
	var first_id := ""
	for id in ids:
		var s := WorldData.sit(String(id))
		if s.is_empty():
			print("[autotest] sit %s: no such sit" % id)
			continue
		var ch := int(s.chapter)
		GameState.flags["chapter"] = ch if Chapters.has(ch) else 3
		var want := forced if forced != "" else String(light.get(ch, "blue"))
		if game.world_env.time_of_day != want:
			game.world_env.apply_time(want)
			await wait(1.5)
		game._refresh_presence()
		# where a player would stand to sit there: the sit's stand point, its prompt, or in front of the seat
		var near: Vector3 = s.stand if s.stand != Vector3.INF else (s.spot if s.spot != s.pos else s.pos + Vector3(sin(s.yaw), 0, cos(s.yaw)) * 0.9)
		game.player.teleport(near + Vector3(0, 0.05, 0), s.yaw)
		game.camera_rig.snap_behind(game.player.facing_yaw())
		await wait(0.6)
		game.begin_sit(String(id))
		await wait(1.2)
		var song: String = game._sit_song(s)
		var at0: float = Sfx.position_of(song)
		print("[autotest] sit %s: mode %s, sitting %s, hud %s, letterbox %.0f, song %s at %.1f s, time %s" % [id, game.mode, game.player.rig.sitting,
			game.hud.hud_visible, game.hud.letterbox_height(), song, at0, game.world_env.time_of_day])
		await shot("sit_%s_00" % id)
		await wait(8.8)
		await shot("sit_%s_10" % id)
		await wait(10.0)
		print("[autotest] sit %s: thought '%s', moments %s" % [id, game.dialogue.bark_text(), GameState.flags.get("moments", [])])
		await wait(10.0)
		await shot("sit_%s_30" % id)
		if first_song == "":
			first_song = song
			first_id = String(id)
		var t0 := Time.get_ticks_msec() / 1000.0
		await _key(KEY_SPACE)
		var stood := -1.0
		while Time.get_ticks_msec() / 1000.0 - t0 < 2.0:
			if game.mode == "play" and not game.player.rig.sitting and not game.player.frozen:
				stood = Time.get_ticks_msec() / 1000.0 - t0
				break
			await get_tree().process_frame
		print("[autotest] sit %s: a key, then playable and standing after %.3f s (mode %s): %s; song %s left at %.1f s" % [id, stood, game.mode,
			"PASS" if stood >= 0.0 and stood <= 0.5 else "FAIL", song, Sfx.position_of(song)])
		await wait(1.0)
		await shot("sit_%s_stood" % id)
	# a second sit resumes the song where the first left it
	if first_id != "":
		var s := WorldData.sit(first_id)
		GameState.flags["chapter"] = int(s.chapter) if Chapters.has(int(s.chapter)) else 3
		var left: float = Sfx.position_of(first_song)
		game.begin_sit(first_id)
		await wait(1.5)
		var now: float = Sfx.position_of(first_song)
		print("[autotest] sit %s again: song %s left at %.1f s, now at %.1f s: %s" % [first_id, first_song, left, now,
			"PASS (resumed)" if now >= left else "FAIL (restarted)"])
		await wait(1.0)
		await _key(KEY_SPACE)
		await wait(0.5)
	# the journal's Moments, with all six written (the page must hold them)
	GameState.flags["moments"] = WorldData.sit_ids()
	game.menus.show_journal()
	await wait(1.2)
	await shot("journal_moments")
	game.resume()


## autotest=place [ids=a,b]: Mano at each data/world.json point, shot from behind and above,
## with the floor under it found by a down-ray (a point more than 0.3 m off the floor is reported).
func _place_plan() -> void:
	await wait(1.0)
	game.menus.close()
	game.resume()
	game.hud.set_hud_visible(false)
	var ids: Array = WorldData.section("points").keys()
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("ids="):
			ids = Array(arg.substr(4).split(","))
	var space: PhysicsDirectSpaceState3D = game.get_world_3d().direct_space_state
	for id in ids:
		var pt := WorldData.point(String(id))
		if pt.is_empty():
			print("[autotest] place %s: no such point" % id)
			continue
		var q := PhysicsRayQueryParameters3D.create(pt.pos + Vector3.UP * 1.5, pt.pos + Vector3.DOWN * 1.5, 1)
		var hit := space.intersect_ray(q)
		var floor_y: float = hit.position.y if not hit.is_empty() else INF
		game.player.teleport(pt.pos + Vector3.UP * 0.05, pt.yaw)
		var back := Vector3(sin(pt.yaw), 0, cos(pt.yaw))
		var from: Vector3 = pt.pos - back * 3.2 + Vector3.UP * 2.4
		game.camera_rig.set_shot(from, pt.pos + Vector3.UP * 0.9, 50.0, -1.0, true)
		await wait(1.6)
		await shot("place_" + String(id))
		var off := absf(floor_y - pt.pos.y) if floor_y != INF else INF
		print("[autotest] place %s at %s: floor %s, zone '%s'%s" % [id, pt.pos, "none" if floor_y == INF else "%.2f" % floor_y,
			game.binder.zone_at(pt.pos).get("id", ""), "" if off <= 0.3 else "  OFF THE FLOOR"])


## autotest=dream (docs/DESIGN.md §7): the two character-free frames of the opening's dream clip, in the opening's
## light, with nobody in the room and no lens finish or letterbox (the game plays the clip under them): "start",
## the empty amphi from the landing, low, down the aisle steps to the Dijkstra slide, a white earbud on the edge of
## the first step, and the sun room's shafts thickened
## for the dream; "end", the wake-up's first shot (main.wake_shots(): the desk, the notebook, as soft as the
## wake-up opens on it). Also "end_cast" (the same shot with everyone there: it must show nobody) and the close-up
## the wake-up cuts to. "recon" on the command line adds candidate views. 16:9 shots: the window is 3584x2016
## (1792x1008 shots on a Retina screen, whose usable height is under 2160 px); use shots=dream/<name>.
## "round2" renders the shipped clip's three keyframes instead (_dream_round2: start.png, mid.png, end.png; shots=dream/round2).
func _dream_frames() -> void:
	await wait(1.0)
	game.menus.close()
	game._stop_title_fade()
	game._title_pose(false)
	game.mode = "cutscene"
	game.player.frozen = true
	game.player.teleport(game.binder.spawn.origin, game._yaw_from(game.binder.spawn))
	game.world_env.apply_time(WorldEnv.DEFAULT_TIME)
	game._wake_pose()
	DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_WINDOWED)
	DisplayServer.window_set_size(Vector2i(3584, 2016))
	DisplayServer.window_set_position(Vector2i(0, 0))
	game.hud.visible = false
	game.menus.visible = false
	game._post.visible = false
	var bud := _dream_earbud()
	game.add_child(bud)
	await wait(3.2)   # as long as the opening waits under its chapter card
	var w: Array = game.wake_shots()
	var desk: Array = w[0]
	var face: Array = w[1]
	print("[autotest] dream: window ", DisplayServer.window_get_size(), " view ", game.world_env.view_port().get_visible_rect().size)
	print("[autotest] dream: desk ", desk, " face ", face, " mano ", game.player.global_position)
	if "round2" in OS.get_cmdline_user_args():
		bud.queue_free()
		await _dream_round2(desk)
		return
	var top_step := Vector3(18.8, -0.15, 16.1)
	var B: float = game.WAKE_DESK_BLUR
	# [name, from, look, fov, earbud or null, wake blur (-1: sharp), focus distance, cast too]
	var views := [
		["start", Vector3(18.8, 0.1, 16.6), Vector3(18.8, -1.2, 9.5), 46.0, Vector3(18.85, -0.15, 15.95), -1.0, 0.0, false],
		["end", desk[0], desk[1], desk[2], null, B, desk[3], true],
		["end_sharp", desk[0], desk[1], desk[2], null, -1.0, 0.0, false],
		["face", face[0], face[1], face[2], null, -1.0, 0.0, true],
	]
	if "recon" in OS.get_cmdline_user_args():
		views.append_array([
			["s1", Vector3(18.85, 0.25, 16.75), Vector3(18.7, -2.0, 9.5), 48.0, top_step, -1.0, 0.0, false],
			["s5", Vector3(18.95, 0.45, 16.95), Vector3(18.7, -1.25, 9.5), 50.0, Vector3(18.8, -0.15, 16.1), -1.0, 0.0, false],
			["s7", Vector3(18.85, 0.3, 16.8), Vector3(18.75, -1.45, 9.5), 50.0, Vector3(18.8, -0.15, 16.05), -1.0, 0.0, false],
			["s3", Vector3(19.6, 0.9, 16.9), Vector3(17.6, -1.6, 9.0), 50.0, top_step, -1.0, 0.0, false],
		])
	var room: Node = game.find_child("SunRoom_amphi", true, false)
	var fog_mat: FogMaterial = room.fog.material if room and room.fog else null
	var fog0: float = fog_mat.density if fog_mat else 0.0
	for pass_i in 2:
		var cast := pass_i == 1
		game.player.visible = cast
		for id in game.npcs:
			game.npcs[id].visible = cast and game.npcs[id].is_present()
		for n in game.crowd:
			n.visible = cast
		for v in views:
			if cast and not v[7]:
				continue
			bud.visible = v[4] != null
			if v[4] != null:
				bud.global_position = v[4]
			if fog_mat:   # the dream's air: the shafts thicker than the game's, for its first frame only
				fog_mat.density = fog0 * 2.5 if v[0].begins_with("s") else fog0
			game.camera_rig.set_shot(v[1], v[2], v[3], -1.0, true)
			if v[5] >= 0.0:
				game.world_env.set_wake_blur(v[5], v[6])
			await wait(3.0 if v == views[0] else 1.6)
			await shot(v[0] + ("_cast" if cast else ""))


## The opening's dream clip, if it plays (it starts 3.2 s into the chapter card): wait until it has dissolved into
## the desk shot.
func _past_dream() -> void:
	var t := 0.0
	while game.dream_player == null and t < 1.5:
		await wait(0.05)
		t += 0.05
	while game.dream_player != null:
		await wait(0.05)


## autotest=opening (docs/DESIGN.md §7): New game from the title through the chapter card, the dream clip (when
## assets/video/dream.ogv loads) and the wake-up, to Toma's first lines. Shots: the card, the dream in its middle
## (under the lens finish, the letterbox out), the live desk shot right after its dissolve, the cut to Mano's face,
## his face in focus, Toma talking. The clip's own frames as Godot decodes them are saved too (op_videotex_*.png,
## read back from the video texture); "dream_at=0.15,4.6" takes the dream's shots at those clip times (seconds)
## instead of 0.5 and 2.5, plus one 0.1 s before its end as always. Every shot is drawn on the spot (_shot_drawn): a
## window macOS doesn't show (another Space, a full-screen app over it) draws no frames of its own, which would hold
## shots back for seconds (the log's drawn= count shows it); each forced draw stalls the game about a second, which
## the clip rides out.
func _opening_plan() -> void:
	await wait(3.5)
	var t0 := Time.get_ticks_msec()
	var now := func() -> float: return (Time.get_ticks_msec() - t0) / 1000.0
	game.dialogue.line_shown.connect(func(who, text, _e = ""): print("[autotest] %.2f line %s: %s" % [now.call(), who, text]))
	_watch_opening(now)
	game.new_game()
	await _past_cold_open(false)
	await wait(2.6)
	_shot_drawn("op_card")
	var t := 0.0
	while game.dream_player == null and t < 1.5:
		await wait(0.02)
		t += 0.02
	var vp: VideoStreamPlayer = game.dream_player
	if vp:
		var length := vp.get_stream_length()
		print("[autotest] %.2f opening: dream playing, %.2f s, texture %s, layer %d under the post layer %d in %s" % [now.call(),
				length, vp.get_video_texture().get_size(), vp.get_parent().get_parent().layer, game._post.layer, vp.get_viewport().name])
		var ats := [0.5, 2.5, length - 0.1]   # dream_at=0.15,4.6,... picks other clip times (seconds)
		for arg in OS.get_cmdline_user_args():
			if arg.begins_with("dream_at="):
				ats = Array(arg.trim_prefix("dream_at=").split(",")).map(func(s): return float(s))
				ats.append(length - 0.1)
		for at in ats:
			while is_instance_valid(vp) and game.dream_player != null and vp.stream_position < at:
				await wait(0.02)
			if not is_instance_valid(vp) or game.dream_player == null:
				break
			vp.get_video_texture().get_image().save_png("%s/op_videotex_%.1f.png" % [shots_dir(), at])
			print("[autotest] %.2f opening: decoded frame at %.2f s" % [now.call(), vp.stream_position])
			_shot_drawn("op_dream_%.1f" % at)
		while game.dream_player != null:
			await wait(0.02)
		print("[autotest] %.2f opening: dream over" % now.call())
	else:
		print("[autotest] opening: no dream clip, straight to the wake-up")
		await wait(1.3)
	_shot_drawn("op_after_dream")
	# counted in frames from here: a forced draw stalls the game, and the next frame's step runs any timer out
	var desk_cam: Vector3 = game.camera_rig.cam.global_position
	var n := 0
	while game.camera_rig.cam.global_position.distance_to(desk_cam) < 0.5 and n < 600:
		await get_tree().process_frame
		n += 1
	print("[autotest] opening: the cut to his face %d frames after the dream" % n)
	await _frames(30)
	_shot_drawn("op_face_blur")
	await _frames(110)
	_shot_drawn("op_face_sharp")
	n = 0
	while not game.dialogue.running and n < 600:
		await get_tree().process_frame
		n += 1
	await _frames(70)
	_shot_drawn("op_toma")
	print("[autotest] %.2f opening: mode=%s dialogue=%s" % [now.call(), game.mode, game.dialogue.running])


func _frames(n: int) -> void:
	for i in n:
		await get_tree().process_frame


## A shot of the frame as it stands, drawn on the spot (RenderingServer.force_draw, no swap) rather than waiting for
## the next drawn frame, which a window macOS hides never gets: the dream's frames under the lens finish.
func _shot_drawn(name: String) -> void:
	var t := Time.get_ticks_msec()
	RenderingServer.force_draw(false, 0.0)
	var img := get_viewport().get_texture().get_image()
	var k := 1.0 if "fullres" in OS.get_cmdline_user_args() else WorldView.pixels_per_point()
	if k > 1.0:
		img.resize(roundi(img.get_width() / k), roundi(img.get_height() / k), Image.INTERPOLATE_BILINEAR)
	_n += 1
	img.save_png("%s/auto_%02d_%s.png" % [shots_dir(), _n, name])
	var view: WorldView = game.world_env.view
	print("[autotest] shot %s (drawn on the spot, %d ms) camera %s mirror %s frames %d" % [name, Time.get_ticks_msec() - t,
			game.camera_rig.cam.global_position, view._cam.global_position if view and view.is_active() else "-", Engine.get_process_frames()])


## Prints the opening's state twice a second for its first 14 s (autotest=opening); drawn= is the frames drawn.
func _watch_opening(now: Callable) -> void:
	while now.call() < 14.0:
		var vp: VideoStreamPlayer = game.dream_player
		print("[autotest] %.2f drawn=%d mode=%s fade=%.2f dream=%s cam=%s" % [now.call(), Engine.get_frames_drawn(), game.mode,
				game.hud.fade.color.a, ("%.2f a=%.2f" % [vp.stream_position, vp.get_parent().modulate.a]) if vp else "-",
				game.camera_rig.cam.global_position])
		await wait(0.5)


## A white earbud lying on its side (as Player._attach_airpod builds them), for the dream's first frame.
func _dream_earbud() -> Node3D:
	var pod := Node3D.new()
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
	bud.position = Vector3(0, 0.0095, 0)
	pod.add_child(bud)
	var stem := MeshInstance3D.new()
	var cm := CapsuleMesh.new()
	cm.radius = 0.0032
	cm.height = 0.03
	stem.mesh = cm
	stem.material_override = white
	stem.rotation = Vector3(0, 0.6, PI * 0.5)
	stem.position = Vector3(0.012, 0.0035, 0.008)
	pod.add_child(stem)
	return pod


## autotest=dream round2 (assets/video/CREDITS.md): the keyframes of the dream as two first/last-frame clips
## joined on an engine-rendered middle frame, A = start -> mid (the tumble down the aisle steps, a gentle crane up),
## B = mid -> end (a drift right over the desk row, settling on the notebook). Saved as start.png, mid.png and end.png
## in shots_dir() (run it with shots=dream/round2), 1792x1008, nobody in the room, no lens finish or letterbox.
## "start": final/dream_start.png's composition with the clip's earbud (_dream_earbud2: one opaque glossy piece,
## 1.3x) on the edge of the top step in a sunbeam, the shafts thicker and dust in them; "mid": two-thirds of the way
## from the start to the desk shot, risen to seated eye level over the seat backs and desk tops, turned part-way right
## so the notebook's desk row shows ahead-right, the earbud at rest on a lower aisle step in the lower part of the
## frame; "end": the wake-up's first shot as the live game has it (the game's own air, no earbud, as soft as the
## wake-up opens), which must still match final/dream_end.png. "recon" adds candidate views; "pathcheck" also tests
## the camera path start -> mid -> end against the level's collision.
func _dream_round2(desk: Array) -> void:
	var args := OS.get_cmdline_user_args()
	game.player.visible = false
	for id in game.npcs:
		game.npcs[id].visible = false
	for n in game.crowd:
		n.visible = false
	var bud := _dream_earbud2(DREAM2_BUD_SCALE, DREAM2_BUD_ROLL)
	game.add_child(bud)
	var room: Node = game.find_child("SunRoom_amphi", true, false)
	var fog_mat: FogMaterial = room.fog.material if room and room.fog else null
	var fog0: float = fog_mat.density if fog_mat else 0.0
	var sun: DirectionalLight3D = game.world_env.sun
	var sun_fog0 := sun.light_volumetric_fog_energy
	var dust: GPUParticles3D = _dream_dust(room)
	var beam := _dream_beam(DREAM2_START_BUD[0], sun)
	var vp: Viewport = game.world_env.view_port()
	var scale0 := vp.scaling_3d_scale
	var env: Environment = game.world_env.env
	var fog_len0 := env.volumetric_fog_length
	var gi0 := env.volumetric_fog_gi_inject
	var froxels0 := Vector2i(ProjectSettings.get_setting("rendering/environment/volumetric_fog/volume_size", 64),
			ProjectSettings.get_setting("rendering/environment/volumetric_fog/volume_depth", 64))
	print("[autotest] dream2: toward the sun ", sun.global_transform.basis.z, " sun energy ", sun.light_energy, " colour ",
			sun.light_color, " fog ", fog0, " sun fog ", sun_fog0, " 3d scale ", scale0, " view ", vp.get_visible_rect().size)
	# the other rolls of the earbud, beside it on the top step, for "r_buds"
	var variants: Array[Node3D] = []
	if "recon" in args:
		for i in DREAM2_ROLLS.size():
			var vb := _dream_earbud2(DREAM2_BUD_SCALE, DREAM2_ROLLS[i])
			vb.visible = false
			game.add_child(vb)
			vb.global_position = DREAM2_START_BUD[0] + Vector3(-0.52 + 0.26 * i + (0.26 if i >= 2 else 0.0), 0, 0)
			vb.rotation.y = DREAM2_START_BUD[1]
			variants.append(vb)
	# [name, from, look, fov, earbud [position, yaw] or null, air (1: the game's; >1: the dream's, the fog that much
	# thicker, with the sun's shafts, the sunbeam and the dust), depth of field (-1: the wake-up's blur, else none or a
	# DREAM2_DOF), saved]. The end is shot exactly as plain autotest=dream shoots the clip's end frame
	# (final/dream_end.png): 1.6 s after a cut from 3 s on the start view in its 2.5x fog, the game's 3D scale, so the
	# level's light has settled for as long (SDFGI keeps converging for seconds after the scene loads: shot 1.6 s
	# earlier or later, the desk comes out a few levels darker or lighter).
	var views := [
		["prime", DREAM2_START[0], DREAM2_START[1], DREAM2_START[2], null, 2.5, [], false],
		["end", desk[0], desk[1], desk[2], null, 1.0, -1.0, true],
		["start", DREAM2_START[0], DREAM2_START[1], DREAM2_START[2], DREAM2_START_BUD, DREAM2_FOG, DREAM2_START[3], true],
		["mid", DREAM2_MID[0], DREAM2_MID[1], DREAM2_MID[2], DREAM2_MID_BUD, DREAM2_FOG, DREAM2_MID[3], true],
	]
	if "recon" in args:
		views.append_array([
			["r_over", Vector3(18.8, 2.6, 17.6), Vector3(18.9, -1.4, 12.5), 62.0, DREAM2_START_BUD, DREAM2_FOG, [], true],
			["r_buds", DREAM2_START_BUD[0] + Vector3(0.0, 0.3, 0.5), DREAM2_START_BUD[0], 50.0, DREAM2_START_BUD, DREAM2_FOG, [], true],
			["r_bud", Vector3(18.95, 0.0, 16.25), DREAM2_START_BUD[0], 30.0, DREAM2_START_BUD, DREAM2_FOG, [], true],
			["r_bud_mid", DREAM2_MID_BUD[0] + Vector3(0.05, 0.25, 0.35), DREAM2_MID_BUD[0], 30.0, DREAM2_MID_BUD, DREAM2_FOG, [], true],
			["r_side", Vector3(23.0, 1.6, 15.8), Vector3(19.0, -0.6, 14.6), 55.0, DREAM2_MID_BUD, DREAM2_FOG, [], true],
		])
	for v in views:
		bud.visible = v[4] != null
		if v[4] != null:
			bud.global_position = v[4][0]
			bud.rotation.y = v[4][1]
		for vb in variants:
			vb.visible = v[0] == "r_buds"
		var air: float = v[5]
		var dream := air > 2.6
		if fog_mat:
			fog_mat.density = fog0 * air
		sun.light_volumetric_fog_energy = sun_fog0 * DREAM2_SUN_FOG if dream else sun_fog0
		env.volumetric_fog_gi_inject = DREAM2_GI_INJECT if dream else gi0
		if dust:
			dust.visible = dream
		beam.visible = dream
		vp.scaling_3d_scale = DREAM2_SCALE if dream else scale0
		# finer fog cells over a shorter fog for the dream's frames, so the window bars cut sharper shafts
		var fx: Vector2i = DREAM2_FROXELS if dream else froxels0
		RenderingServer.environment_set_volumetric_fog_volume_size(fx.x, fx.y)
		env.volumetric_fog_length = DREAM2_FOG_LENGTH if dream else fog_len0
		game.camera_rig.set_shot(v[1], v[2], v[3], -1.0, true)
		if v[6] is float:
			game.world_env.set_wake_blur(game.WAKE_DESK_BLUR, desk[3])
		elif not v[6].is_empty():
			_dream2_dof(v[6])
		var f0 := Engine.get_frames_drawn()
		await wait(3.0 if v[0] in ["prime", "start"] else 1.6)
		print("[autotest] dream2: %s after %d frames" % [v[0], Engine.get_frames_drawn() - f0])
		if v[7]:
			await _shot_file(v[0])
		else:
			await RenderingServer.frame_post_draw
		if v[0] == "start" and "clipA" in args:   # the engine clip A, from this very state (_dream3_clip_a)
			await _dream3_clip_a(bud)
	RenderingServer.environment_set_volumetric_fog_volume_size(froxels0.x, froxels0.y)
	env.volumetric_fog_length = fog_len0
	env.volumetric_fog_gi_inject = gi0
	if "pathcheck" in args:
		_dream2_path_check(desk)


## The round-2 dream keyframes: [from, look, fov, depth of field (_dream2_dof)] and the earbud's [position, yaw]. The
## middle frame is two-thirds of the way from the start to the desk shot (z 16.6 -> 15.3 -> 14.7), in the aisle at
## seated eye level over its second tier (0.22 m over the seat backs, 0.38 m over the end panels, 0.42 m over the desk
## tops), turned 19 degrees of the desk shot's 32 to the right and looking down at the earbud on the third tier's step.
const DREAM2_START := [Vector3(18.8, 0.1, 16.6), Vector3(18.8, -1.2, 9.5), 46.0, [8.0, 8.0, 0.42, 0.25, 0.035]]
const DREAM2_START_BUD := [Vector3(18.86, -0.15, 15.985), 0.35]
const DREAM2_MID := [Vector3(18.9, 0.6, 15.3), Vector3(19.56, -0.83, 13.35), 44.0, [4.5, 8.0, 0.0, 0.0, 0.045]]
const DREAM2_MID_BUD := [Vector3(19.05, -0.75, 14.12), -0.4]
const DREAM2_BUD_SCALE := 1.3
const DREAM2_BUD_ROLL := -0.6
const DREAM2_ROLLS := [0.0, -1.2, -1.5708, 0.6]
const DREAM2_FOG := 3.0        # the dream's air: the sun room's fog this much thicker
const DREAM2_SUN_FOG := 2.5    # the sun this much brighter in it,
const DREAM2_GI_INJECT := 0.2  # and the fog's ambient light lower (the game's: 0.6), so the shafts stand out of the shade
const DREAM2_SCALE := 1.0      # the 3D resolution scale for the dream's own frames (the game runs FSR2 at 0.62)
const DREAM2_FROXELS := Vector2i(192, 128)   # the volumetric fog's cells across and deep (the game's: 64, 64)
const DREAM2_FOG_LENGTH := 24.0              # over this much depth (the game's: 48 m; the amphi is 12 m deep)


## The sunbeam the start frame's earbud lies in: the real sun can't reach the aisle's top step past the rows on its
## west side, so a narrow spot along the sun's own direction, from just inside the aisle, lights a streak of the step
## and the earbud (its own shadow too) and draws a short shaft in the dream's fog. No GI (SDFGI keeps nothing of it).
func _dream_beam(target: Vector3, sun: DirectionalLight3D) -> SpotLight3D:
	var to_sun := sun.global_transform.basis.z.normalized()
	var s := SpotLight3D.new()
	s.light_color = sun.light_color
	s.light_energy = sun.light_energy * DREAM2_BEAM[0]
	s.light_volumetric_fog_energy = DREAM2_BEAM[1]
	s.spot_range = 3.0
	s.spot_attenuation = 0.0
	s.spot_angle = DREAM2_BEAM[2]
	s.spot_angle_attenuation = 0.5
	s.shadow_enabled = true
	s.light_bake_mode = Light3D.BAKE_DISABLED
	game.add_child(s)
	s.global_position = target + to_sun * 0.9
	s.look_at(target, Vector3.UP)
	return s


## [energy (times the sun's), fog energy, half angle (degrees)]
const DREAM2_BEAM := [1.6, 10.0, 9.0]


## A touch of depth of field for the dream's frames, [far blur from (m), its transition, near blur inside (m; 0:
## none), its transition, amount]: the far wall and the slide a little soft, the earbud sharp.
func _dream2_dof(d: Array) -> void:
	var attrs: CameraAttributesPractical = game.world_env.attrs
	attrs.dof_blur_far_enabled = true
	attrs.dof_blur_far_distance = d[0]
	attrs.dof_blur_far_transition = d[1]
	attrs.dof_blur_near_enabled = d[2] > 0.0
	attrs.dof_blur_near_distance = d[2]
	attrs.dof_blur_near_transition = d[3]
	attrs.dof_blur_amount = d[4]


## A shot saved as <shots_dir>/<name>.png, at one pixel per point as shot() saves them.
func _shot_file(name: String) -> void:
	await RenderingServer.frame_post_draw
	var img := get_viewport().get_texture().get_image()
	var path := "%s/%s.png" % [shots_dir(), name]
	var k := 1.0 if "fullres" in OS.get_cmdline_user_args() else WorldView.pixels_per_point()
	_saving.append(WorkerThreadPool.add_task(func():
		if k > 1.0:
			img.resize(roundi(img.get_width() / k), roundi(img.get_height() / k), Image.INTERPOLATE_LANCZOS)
		img.save_png(path)))
	print("[autotest] shot %s camera %s" % [path, game.camera_rig.cam.global_position])


## Extra dust for the dream's frames: the sun room's motes (only lit where the sun reaches them), denser and brighter
## down the room ahead of the cameras (none within a metre of the lens, where a mote would be a blurred blob), so
## the shafts carry specks. Hidden for the end frame, which must match the live game.
func _dream_dust(room: Node) -> GPUParticles3D:
	if room == null or not room.has_method("_make_dust"):
		return null
	var box := AABB(Vector3(15.5, -1.6, 7.5), Vector3(8.0, 4.8, 7.1))
	var p: GPUParticles3D = room._make_dust(box.size, DREAM2_DUST[0])
	var quad: QuadMesh = p.draw_pass_1
	quad.size = Vector2(DREAM2_DUST[1], DREAM2_DUST[1])
	(quad.material as ShaderMaterial).set_shader_parameter("strength", DREAM2_DUST[2])
	p.emitting = true
	p.position = box.get_center()
	game.add_child(p)
	p.global_position = box.get_center()
	return p


## [motes, size (m), brightness (the room's own: 0.045)]
const DREAM2_DUST := [4000, 0.016, 0.2]


## The round-2 earbud: one solid piece of glossy white plastic, its stem growing out of the bud through a smooth neck
## (a lathe, bent so the bud leans off the stem as a real one does), a dark speaker grille on the bud's inner face and
## the stem's grey end, `k` times the size of _dream_earbud's. `roll` turns it about the stem before it settles. It
## lies at rest: tipped about its cross axis until its centre of mass is lowest, the origin on the floor under it.
func _dream_earbud2(k := 1.3, roll := 0.0) -> Node3D:
	var stem_r := 0.003
	var tip_r := 0.0012          # the stem's flat end, rounded off
	var head_c := 0.031          # the stem's end to the bud's centre, along the axis (+X)
	var head_r := 0.0088
	var egg := 1.12              # the bud a little longer than wide, along the axis
	var pivot := 0.0215          # where the bud leans off the stem's axis (toward +Y)
	var bend := deg_to_rad(32.0)
	var fillet := 0.0055
	var rings := 80
	var segs := 40
	var total := head_c + head_r * egg
	var white := Color(0.94, 0.94, 0.92)
	var grey := Color(0.55, 0.55, 0.57)
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var verts: Array[Vector3] = []
	for i in rings + 1:
		var u := total * float(i) / rings
		var rs := 0.0
		if u < tip_r:
			rs = stem_r - tip_r + sqrt(maxf(tip_r * tip_r - (tip_r - u) * (tip_r - u), 0.0))
		elif u <= head_c:
			rs = stem_r * (1.0 + 0.08 * (u / head_c))   # the stem thickens a little toward the bud
		var e := (u - head_c) / egg
		var rh := sqrt(maxf(head_r * head_r - e * e, 0.0))
		var r := rh
		if u <= head_c:   # a polynomial smooth max: the neck flares into the bud
			var h := maxf(fillet - absf(rs - rh), 0.0) / fillet
			r = maxf(rs, rh) + h * h * fillet * 0.25
		if i == 0 or i == rings:
			r = 0.0
		var a := bend * smoothstep(pivot - 0.004, pivot + 0.006, u)
		for j in segs:
			var phi := TAU * float(j) / segs
			var p := Vector3(u - pivot, r * cos(phi), r * sin(phi))
			p = Vector3(p.x * cos(a) - p.y * sin(a), p.x * sin(a) + p.y * cos(a), p.z) + Vector3(pivot, 0, 0)
			st.set_color(grey if u < 0.0014 else white)
			st.add_vertex(p * k)
			verts.append(p * k)
	for i in rings:
		for j in segs:
			var a0 := i * segs + j
			var a1 := i * segs + (j + 1) % segs
			var b0 := a0 + segs
			var b1 := a1 + segs
			st.add_index(a0); st.add_index(b0); st.add_index(a1)
			st.add_index(a1); st.add_index(b0); st.add_index(b1)
	st.generate_normals()
	var mat := StandardMaterial3D.new()
	mat.vertex_color_use_as_albedo = true
	mat.roughness = 0.3
	mat.metallic_specular = 0.4
	mat.clearcoat_enabled = true
	mat.clearcoat = 0.3
	mat.clearcoat_roughness = 0.2
	var body := MeshInstance3D.new()
	body.mesh = st.commit()
	body.material_override = mat
	# the speaker grille: a dark grey oval on the bud's inner face (toward +Z, off the bend)
	var head_at := Vector3(pivot + (head_c - pivot) * cos(bend), (head_c - pivot) * sin(bend), 0.0)
	var n := Vector3(0.15, 0.1, 1.0).normalized().rotated(Vector3.BACK, bend)
	var grille := MeshInstance3D.new()
	var gm := SphereMesh.new()
	gm.radius = 0.0024
	gm.height = 0.0048
	grille.mesh = gm
	var dark := StandardMaterial3D.new()
	dark.albedo_color = Color(0.22, 0.22, 0.23)
	dark.roughness = 0.6
	grille.material_override = dark
	var gb := Basis(Quaternion(Vector3.UP, n))
	grille.transform = Transform3D(gb * Basis.from_scale(Vector3(1.25, 0.3, 0.9)), head_at + n * (head_r * 0.98))
	var g_holder := Node3D.new()
	g_holder.transform = Transform3D(Basis.from_scale(Vector3.ONE * k), Vector3.ZERO)
	g_holder.add_child(grille)
	var piece := Node3D.new()
	piece.add_child(body)
	piece.add_child(g_holder)
	var lie := Basis(Vector3.RIGHT, roll)
	var centre := Vector3.ZERO
	for p in verts:
		centre += p
	centre /= verts.size()
	var best := INF
	var best_b := lie
	for t in range(-50, 51):
		var b := Basis(Vector3.BACK, deg_to_rad(t * 0.5)) * lie
		var lo := INF
		for p in verts:
			lo = minf(lo, (b * p).y)
		var hgt := (b * centre).y - lo
		if hgt < best:
			best = hgt
			best_b = b
	var lo2 := INF
	for p in verts:
		lo2 = minf(lo2, (best_b * p).y)
	var c := best_b * centre
	piece.transform = Transform3D(best_b, Vector3(-c.x, -lo2, -c.z))
	var pod := Node3D.new()
	pod.add_child(piece)
	return pod


## autotest=dream round2 clipA: the engine's own clip A of the dream (start.png -> mid.png, 4 s at 24 fps), the
## tumble that opens the dream clip (assets/video/CREDITS.md). Run it windowed with a fixed step, e.g.
##   python3.11 tools/dev/godot.py --timeout 900 -- --path . --resolution 1600x900 --fixed-fps 72 -- autotest=dream
##       round2 clipA shots=../tools/out/dream/engine/keys
## (shots= keeps this run's keyframes away from shots/dream/round2). It plays tools/out/dream/engine/clipA_track.json,
## written by tools/out/dream/engine/tumble.py: per render step (3 per frame, 72 Hz) the camera (the path from
## the start camera to the mid camera), its field of view and depth of field, and the earbud's pose (a deterministic
## rigid-body tumble down the aisle steps, sim.py, ending exactly in mid.png's pose). The scene is stepped by hand:
## each step's state is set, one frame is drawn (--fixed-fps makes every frame's delta 1/72 s however long it takes to
## draw, so the dust and the temporal effects advance by the same step; two runs differ by about 0.4 levels, the
## dust's random seeds), and every third frame the 3D view (the WorldView's SubViewport,
## set to 1920x1080 for the clip) is read back and saved as tools/out/dream/engine/clipA/fNNN.png. The camera rig is
## paused meanwhile (its handheld sway is in the track instead). It starts right after the "start" keyframe is shot,
## holding the first step for 1.5 s first so the temporal buffers settle at the new size. Then
## tools/out/dream/engine/finish.py matches the ends' levels to the keyframes and encodes clipA.mp4 (BT.709).
## "track=<name>" plays tools/out/dream/engine/<name>.json instead (tumble.py --warp: the slowed clip with several
## steps per frame, run with --fixed-fps 24 x its "sub"); a track's "out" names the frames' folder (default clipA) and
## its "save" lists which steps of each frame are saved, as fNNN_m.png (default: the first, as fNNN.png).
## "passes=normal,plate,white,black" plays the track once per pass, in that order, each
## into <out>_<pass>/ ("normal", the default, into <out>/): "plate" without the earbud; "white" and "black" with the
## earbud unshaded white (DREAM3_MATTE_WHITE) or black, and the fogs, glow, SSR, SSIL, colour adjustment, auto
## exposure and every particle (the dust) off under a linear tonemap, so (white - black) in linear light is the
## earbud's coverage: its soft matte with the shutter's motion blur and whatever hides it (tools/video/dream_matte.py).
## "crop=WxH" saves only that region of each step, centred on the earbud's projected centre at the frame's first saved
## step, the same in every pass (listed in <dir>/crops.json as frame: [x, y, w, h]).
func _dream3_clip_a(bud: Node3D) -> void:
	var track_name := "clipA_track"
	var passes: Array = ["normal"]
	var crop := Vector2i.ZERO
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("track="):
			track_name = arg.substr(6)
		elif arg.begins_with("passes="):
			passes = Array(arg.trim_prefix("passes=").split(","))
		elif arg.begins_with("crop="):
			var wh := arg.trim_prefix("crop=").split("x")
			crop = Vector2i(int(wh[0]), int(wh[1]))
	var track_path := ProjectSettings.globalize_path("res://tools/out/dream/engine/%s.json" % track_name)
	var track = JSON.parse_string(FileAccess.get_file_as_string(track_path))
	if track == null:
		push_error("dream3: no track at " + track_path)
		return
	var out_base := ProjectSettings.globalize_path("res://tools/out/dream/engine/%s" % str(track.get("out", "clipA")))
	var sv: Viewport = game.world_env.view_port()
	var svp := sv as SubViewport
	var size0 := svp.size if svp else Vector2i.ZERO
	if svp:
		svp.size = DREAM3_SIZE
	var rig = game.camera_rig
	rig.set_process(false)
	bud.physics_interpolation_mode = Node.PHYSICS_INTERPOLATION_MODE_OFF
	for pi in passes.size():
		var pass_name: String = passes[pi]
		var out_dir := out_base if pass_name == "normal" else "%s_%s" % [out_base, pass_name]
		var restore := _dream3_pass(pass_name, bud)
		await _dream3_play(track, out_dir, bud, crop, 1.5 if pi == 0 else 3.0, pass_name)
		restore.call()
	if svp:
		svp.size = size0
	rig.set_process(true)


## One pass of _dream3_clip_a: the track played step by step into out_dir.
func _dream3_play(track: Dictionary, out_dir: String, bud: Node3D, crop: Vector2i, settle: float, pass_name: String) -> void:
	DirAccess.make_dir_recursive_absolute(out_dir)
	var samples: Array = track["samples"]
	var sub := int(track["sub"])
	var save_steps: Array = track.get("save", [0])
	var sub_named: bool = track.has("save")
	var view: WorldView = game.world_env.view
	var sv: Viewport = game.world_env.view_port()
	var rig = game.camera_rig
	var cam: Camera3D = rig.cam
	var mirror: Camera3D = view._cam if view and view.is_active() else null
	_dream3_apply(samples[0], cam, mirror, bud)
	await wait(settle)
	print("[autotest] dream3: clip A pass %s, %d steps, %d per frame, view %s, played at %.2fx, sway %s, into %s" % [
			pass_name, samples.size(), sub, sv.get_visible_rect().size, track["slowmo"], track["sway"], out_dir])
	var space: PhysicsDirectSpaceState3D = game.get_world_3d().direct_space_state
	var q := PhysicsShapeQueryParameters3D.new()
	var sphere := SphereShape3D.new()
	sphere.radius = 0.06
	q.shape = sphere
	var worst := INF
	var blocked := 0
	var dt_lo := INF
	var dt_hi := 0.0
	var f0 := Engine.get_frames_drawn()
	var n := 0
	var rects := {}
	for j in samples.size():
		var s: Dictionary = samples[j]
		_dream3_apply(s, cam, mirror, bud)
		var p := cam.global_position
		var clear := _dream2_clearance(p)
		worst = minf(worst, clear)
		q.transform = Transform3D(Basis(), p)
		if not space.intersect_shape(q, 1).is_empty() or clear < 0.06:
			blocked += 1
		await RenderingServer.frame_post_draw
		if j > 0:
			dt_lo = minf(dt_lo, get_process_delta_time())
			dt_hi = maxf(dt_hi, get_process_delta_time())
		var m := j % sub
		if not save_steps.has(float(m)) and not save_steps.has(m):
			continue
		var img := sv.get_texture().get_image()
		var fi := floori(float(j) / sub)
		if crop.x > 0:
			if not rects.has(fi):
				var on0: Vector2 = (mirror if mirror else cam).unproject_position(bud.global_transform * DREAM3_BUD_COM)
				var x0 := clampi(roundi(on0.x) - int(crop.x * 0.5), 0, DREAM3_SIZE.x - crop.x)
				var y0 := clampi(roundi(on0.y) - int(crop.y * 0.5), 0, DREAM3_SIZE.y - crop.y)
				rects[fi] = [x0, y0, crop.x, crop.y]
			var r: Array = rects[fi]
			img = img.get_region(Rect2i(r[0], r[1], r[2], r[3]))
		var path := ("%s/f%03d_%d.png" % [out_dir, fi, m]) if sub_named else ("%s/f%03d.png" % [out_dir, n])
		_saving.append(WorkerThreadPool.add_task(func():
			img.convert(Image.FORMAT_RGB8)
			img.save_png(path)))
		if sub_named and m != int(save_steps[0]):
			continue
		if n % 12 == 0 or j == samples.size() - 1:
			var com: Vector3 = bud.global_transform * DREAM3_BUD_COM
			var on: Vector2 = (mirror if mirror else cam).unproject_position(com)
			print("[autotest] dream3: frame %d camera %s clearance %.3f earbud %s on screen %s" % [n, p, clear,
					bud.global_position, on])
		n += 1
	if crop.x > 0:
		var fa := FileAccess.open(out_dir + "/crops.json", FileAccess.WRITE)
		fa.store_string(JSON.stringify(rects))
		fa.close()
	print("[autotest] dream3: %d steps drawn in %d frames, step delta %.4f..%.4f s; camera: %d steps blocked, nearest furniture %.3f m" % [
			samples.size(), Engine.get_frames_drawn() - f0, dt_lo, dt_hi, blocked, worst])


## The look of a _dream3_clip_a pass (see there); returns what puts the scene back.
func _dream3_pass(pass_name: String, bud: Node3D) -> Callable:
	if pass_name == "plate":
		bud.visible = false
		return func(): bud.visible = true
	if pass_name != "white" and pass_name != "black":
		return func(): pass
	var env: Environment = game.world_env.env
	var attrs: CameraAttributesPractical = game.world_env.attrs
	var keys := ["glow_enabled", "tonemap_mode", "tonemap_exposure", "volumetric_fog_enabled", "fog_enabled",
			"ssr_enabled", "ssil_enabled", "adjustment_enabled"]
	var saved := {}
	for key in keys:
		saved[key] = env.get(key)
	var ae0: bool = attrs.auto_exposure_enabled
	env.glow_enabled = false
	env.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	env.tonemap_exposure = 1.0
	env.volumetric_fog_enabled = false
	env.fog_enabled = false
	env.ssr_enabled = false
	env.ssil_enabled = false
	env.adjustment_enabled = false
	attrs.auto_exposure_enabled = false
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	var v := DREAM3_MATTE_WHITE if pass_name == "white" else 0.0
	mat.albedo_color = Color(v, v, v)
	var meshes := bud.find_children("*", "MeshInstance3D", true, false)
	var mats := []
	for mi in meshes:
		mats.append((mi as MeshInstance3D).material_override)
		(mi as MeshInstance3D).material_override = mat
	var hidden := []
	for pt in game.find_children("*", "GPUParticles3D", true, false):
		if (pt as Node3D).visible:
			hidden.append(pt)
			(pt as Node3D).visible = false
	print("[autotest] dream3: pass %s: %d earbud meshes unshaded %.2f, %d particle systems hidden, exposure x%.3f" % [
			pass_name, meshes.size(), v, hidden.size(), attrs.exposure_multiplier])
	return func():
		for key in keys:
			env.set(key, saved[key])
		attrs.auto_exposure_enabled = ae0
		for i in meshes.size():
			(meshes[i] as MeshInstance3D).material_override = mats[i]
		for pt in hidden:
			(pt as Node3D).visible = true


## The matte passes' white (sRGB; linear 0.60, under a linear tonemap's clip even at 1.6x exposure).
const DREAM3_MATTE_WHITE := 0.8


## The clip's frame size (the 3D view is resized to it; the window caps nothing, the view is a SubViewport) and the
## earbud's centre of mass in its pod frame (sim.py), only for the log.
const DREAM3_SIZE := Vector2i(1920, 1080)
const DREAM3_BUD_COM := Vector3(0.0081, 0.0111, -0.0011)


## One step of clip A's track: the camera (origin, then the basis' x, y, z columns), its fov and depth of field
## (_dream2_dof), the earbud's pod (origin and basis).
func _dream3_apply(s: Dictionary, cam: Camera3D, mirror: Camera3D, bud: Node3D) -> void:
	var c: Array = s.cam
	var xf := Transform3D(Basis(Vector3(c[3], c[4], c[5]), Vector3(c[6], c[7], c[8]), Vector3(c[9], c[10], c[11])),
			Vector3(c[0], c[1], c[2]))
	cam.global_transform = xf
	cam.fov = s.fov
	if mirror:
		mirror.global_transform = xf
		mirror.fov = s.fov
	var b: Array = s.bud
	bud.global_transform = Transform3D(Basis(Vector3(b[3], b[4], b[5]), Vector3(b[6], b[7], b[8]), Vector3(b[9], b[10], b[11])),
			Vector3(b[0], b[1], b[2]))
	var d: Array = s.dof
	_dream2_dof(d)
	game.world_env.attrs.dof_blur_near_enabled = d[2] > 0.001


## autotest=dream round2 pathcheck: the camera's way from the start through the middle frame to the desk shot,
## sampled along a smooth curve, tested against the level's collision (a 6 cm sphere) and against the boxes of the
## amphi's rows (writing tablets, end panels, seat backs; campus_props.amphi_row) and aisle steps.
func _dream2_path_check(desk: Array) -> void:
	var p0: Vector3 = DREAM2_START[0]
	var p1: Vector3 = DREAM2_MID[0]
	var p2: Vector3 = desk[0]
	var space: PhysicsDirectSpaceState3D = game.get_world_3d().direct_space_state
	var sphere := SphereShape3D.new()
	sphere.radius = 0.06
	var q := PhysicsShapeQueryParameters3D.new()
	q.shape = sphere
	var hits := 0
	var worst := INF
	var n := 60
	for i in n + 1:
		var t := float(i) / n
		# Catmull-Rom through the three keys, with the ends' tangents along their own legs
		var p := _dream2_path(p0, p1, p2, t)
		q.transform = Transform3D(Basis(), p)
		var res: Array = space.intersect_shape(q, 4)
		var clear := _dream2_clearance(p)
		worst = minf(worst, clear)
		if not res.is_empty() or clear < 0.06:
			hits += 1
			print("[autotest] dream2 path: t=%.2f at %s collides (%d bodies) clearance %.3f" % [t, p, res.size(), clear])
	print("[autotest] dream2 path: %d of %d samples blocked, nearest furniture %.3f m; start %.3f, mid %.3f, end %.3f" % [
			hits, n + 1, worst, _dream2_clearance(p0), _dream2_clearance(p1), _dream2_clearance(p2)])


func _dream2_path(p0: Vector3, p1: Vector3, p2: Vector3, t: float) -> Vector3:
	var m0 := (p1 - p0)
	var m1 := (p2 - p0) * 0.5
	var m2 := (p2 - p1)
	if t < 0.5:
		var s := t * 2.0
		return _hermite(p0, m0, p1, m1, s)
	var s2 := t * 2.0 - 1.0
	return _hermite(p1, m1, p2, m2, s2)


func _hermite(a: Vector3, ma: Vector3, b: Vector3, mb: Vector3, s: float) -> Vector3:
	var s2 := s * s
	var s3 := s2 * s
	return a * (2 * s3 - 3 * s2 + 1) + ma * (s3 - 2 * s2 + s) + b * (-2 * s3 + 3 * s2) + mb * (s3 - s2)


## Distance from p to the nearest amphi furniture or floor box near the aisle (campus_south.amphi_interior,
## campus_dress.amphi, campus_props.amphi_row: tiers 0.95 m deep, 0.3 m high, rows facing -Z, aisle x 17.9..19.65).
func _dream2_clearance(p: Vector3) -> float:
	var best := INF
	var boxes: Array[AABB] = []
	boxes.append(AABB(Vector3(9.65, -0.3, 16.4), Vector3(18.2, 0.3, 1.8)))   # entrance landing
	for k in range(1, 8):
		var z1 := 16.4 - 0.95 * (k - 1)
		var z0 := z1 - 0.95
		var top := -0.3 * k
		var zm := (z0 + z1) * 0.5
		boxes.append(AABB(Vector3(9.65, top - 0.4, z0), Vector3(18.2, 0.4, 0.95)))       # the tier
		boxes.append(AABB(Vector3(17.9, top, zm), Vector3(1.75, 0.15, z1 - zm)))         # the aisle's half step
		var zr := (z0 + z1) * 0.5 + 0.05   # the row's origin; rotated PI, local z -> -z
		for row in [[14.1, 3.8], [23.45, 3.8]]:
			var xc: float = row[0]
			var h: float = row[1]
			boxes.append(AABB(Vector3(xc - h, top + 0.74, zr - 0.36), Vector3(2 * h, 0.04, 0.32)))   # tablet
			boxes.append(AABB(Vector3(xc - h, top, zr - 0.36), Vector3(2 * h, 0.74, 0.04)))          # modesty panel
			boxes.append(AABB(Vector3(xc - h, top, zr - 0.38), Vector3(0.04, 0.82, 0.8)))            # end panels
			boxes.append(AABB(Vector3(xc + h - 0.04, top, zr - 0.38), Vector3(0.04, 0.82, 0.8)))
			boxes.append(AABB(Vector3(xc - h, top + 0.36, zr - 0.04), Vector3(2 * h, 0.1, 0.42)))    # seats
			boxes.append(AABB(Vector3(xc - h, top + 0.45, zr + 0.36), Vector3(2 * h, 0.55, 0.12)))   # seat backs
	for b in boxes:
		var c := Vector3(clampf(p.x, b.position.x, b.end.x), clampf(p.y, b.position.y, b.end.y), clampf(p.z, b.position.z, b.end.z))
		best = minf(best, c.distance_to(p))
	return best


## autotest=voice [ids=prof,karim,...]: the recorded NPC lines (VoiceLines, scripts/story/voice.gd). Talks to each
## NPC and logs every card: whether it has a recording, that it plays on the Voice bus with the music ducked, the
## speaker's jaw while it plays, and that the next card cuts it. Friends' cards must have none. Headless is enough.
func _voice_check() -> void:
	await wait(1.0)
	game.menus.close()
	game.resume()
	GameState.flags["toma"] = true
	var d = game.dialogue
	var ids := ["prof", "madame", "karim", "acu", "student2", "chloe", "toma"]
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("ids="):
			ids = Array(arg.substr(4).split(","))
		if arg.begins_with("flags="):   # e.g. flags=ines,karim,coffee_given: later conversations (madame2's)
			for k in arg.substr(6).split(","):
				GameState.flags[k] = true
	var voiced := 0
	var good := 0
	var silent := 0
	for id in ids:
		var n = game.npcs.get("madame2" if id == "ending" else id)
		if n == null:
			print("[autotest] voice: no NPC ", id)
			continue
		game.player.teleport(_free_spot_near(n), 0.0)
		await wait(0.5)
		if id == "ending":   # the closing scene with Mme Dupont at the accueil
			game.say(game.story.ending(), "madame2")
		else:
			game.interact(n.interact)
		var guard := 0
		while not d.running and guard < 30:
			await wait(0.1)
			guard += 1
		var cards := 0
		while d.running and cards < 12:
			await wait(0.1)
			var who: String = d._last_who
			if d.voice.is_empty():
				silent += 1
				print("[autotest] voice  -  %s: \"%s\" (no recording)" % [who, d._text])
			else:
				voiced += 1
				var p: AudioStreamPlayer = d.voice_player
				var secs: float = d.voice.seconds
				var key: String = d.voice.key
				var text: String = d._text
				var stream: AudioStream = p.stream
				var rig = game._speaker_rig
				var jaw := 0.0
				var pos := 0.0
				var t := 0.0
				var duck: float = Sfx._vduck_target
				while t < minf(secs, 2.5) and p.playing:
					await get_tree().process_frame
					t += get_process_delta_time()
					pos = maxf(pos, p.get_playback_position())
					if rig:
						jaw = maxf(jaw, rig._syllable)
				var was_playing := p.playing or pos > 0.0
				# the next card (or the end) must cut the clip
				if not d._choices.is_empty():
					d._pick(d._choices.size() - 1)
				else:
					d._shown = 9999.0
					d._next()
				var cut: bool = p.stream != stream or not p.playing   # stopped, or the next card's clip took over
				var ok: bool = was_playing and p.bus == "Voice" and duck < 1.0 and cut and (rig == null or jaw > 0.05)
				good += 1 if ok else 0
				print("[autotest] voice %s %s (%s): %.2f s on bus %s, played to %.2f s, music duck %.2f, jaw max %.2f%s, cut by the next card %s: \"%s\"" % [
					"OK " if ok else "BAD", key, who, secs, p.bus, pos, duck, jaw, "" if rig else " (no rig)", cut, text])
				cards += 1
				continue
			if not d._choices.is_empty():
				d._pick(d._choices.size() - 1)
			else:
				d._shown = 9999.0
				d._next()
			cards += 1
		while d.running:
			d._shown = 9999.0
			d._next()
			await wait(0.2)
		await wait(0.6)
	print("[autotest] voice: %d voiced cards played, %d OK; %d cards without a recording" % [voiced, good, silent])


# ------------------------------------------------------------------ the cold open and the finale (V2-26, V2-27)
## Waits out the cold open after New game (chapter 0), up to chapter 1's card (opening_phase "card"), moving its two
## lines on as a player would. `shoot`: a frame of each of its shots, the freeze and the caption.
func _past_cold_open(shoot := false) -> void:
	var t := 0.0
	var last_from := Vector3.INF
	var took := {}
	while game.opening_phase != "card" and t < 70.0:
		await wait(0.1)
		t += 0.1
		var sh: Dictionary = game.camera_rig.shot_now()
		if shoot and not sh.is_empty() and sh.from.distance_to(last_from) > 0.3 and game.opening_phase == "cold_open_shots":
			last_from = sh.from
			await wait(0.7)
			t += 0.7
			await shot("cold_shot_%d" % took.size())
			took[took.size()] = true
		if shoot and game.hud._freeze != null and not took.has("freeze"):
			took["freeze"] = true
			await wait(0.5)
			await shot("cold_freeze")
		if shoot and game.hud._caption != null and not took.has("caption"):
			took["caption"] = true
			await wait(1.2)
			await shot("cold_caption")
		if game.dialogue.running and game.dialogue._waiting:
			await wait(1.2)
			t += 1.2
			if shoot:
				await shot("cold_line_%s" % game.dialogue._text.left(12).to_lower().replace(" ", "_").replace(".", "").replace("?", ""))
			print("[autotest] cold open line: %s (%s)" % [game.dialogue._text, game.opening_phase])
			game.dialogue._shown = 9999.0
			game.dialogue._next()
	print("[autotest] cold open over after %.1f s: opening_phase '%s', chapter %d, time %s, clock %s" % [t, game.opening_phase,
		Chapters.current(), game.world_env.time_of_day, Chapters.clock_text()])


## autotest=cold_open (V2-27): New game; the cold open's card ("23:41 / cour Pasteur"), its three shots with where the
## eight heads are in the wide one, "Want one?", the freeze and "Okay. How did I get here?", "Six hours earlier.",
## then chapter 1's card; each shot logged with the camera and the light.
func _cold_open_plan() -> void:
	await wait(3.5)
	game.new_game()
	var t := 0.0
	while game.opening_phase != "cold_open" and t < 6.0:
		await wait(0.1)
		t += 0.1
	await wait(2.4)
	await shot("cold_card")
	print("[autotest] cold open card: time %s, clock %s, chapter %d, Mano at %s" % [game.world_env.time_of_day, Chapters.clock_text(),
		Chapters.current(), game.player.global_position.snapped(Vector3.ONE * 0.01)])
	while game.opening_phase != "cold_open_shots" and t < 20.0:
		await wait(0.1)
		t += 0.1
	await wait(1.6)
	var heads := {}
	for id in ["toma", "anisha", "ian", "silvia", "ishita", "cristina", "joaquin"]:
		var n = game.npcs.get(id)
		heads[id] = game._in_frame(n.rig.head_position()) if n and n.visible else null
	heads["mano"] = game._in_frame(game.player.rig.head_position())
	print("[autotest] cold open wide: %d of 8 heads in the frame %s" % [heads.values().filter(func(h): return h != null).size(), heads])
	await _past_cold_open(true)
	await wait(2.6)
	await shot("cold_then_card")
	print("[autotest] after the cold open: chapter %d card, time %s, clock %s, freeze %s" % [Chapters.current(), game.world_env.time_of_day,
		Chapters.clock_text(), game.hud._freeze != null])


## autotest=credits (V2-27): chapter 5 from the title; the steps and the toast (frames every 4 lines), the group photo
## (every head in its frame), "Want one?" to Toma, the song, the credits roll (frames at 2.5, 15 and 30 s, then
## played to its end), the post-credits (the drain grate), the recap page.
func _credits_plan() -> void:
	await wait(3.5)
	# a print from a tour stop first, as chapter 3 leaves one in the film folder
	game.start_chapter(5)
	await _past_cutscene()
	await advance_dialogue(80, 4)
	await wait(0.5)
	var heads: Dictionary = game.group_photo.get("heads", {})
	print("[autotest] credits: group photo %s: %d of %d heads in the frame %s" % [game.group_photo.get("path", "-"),
		heads.values().filter(func(h): return h != null).size(), heads.size(), heads])
	await shot("credits_after_photo")
	# "Want one?" to Toma (the to-do's target)
	var toma = game.npcs["toma"]
	game.player.teleport(_free_spot_near(toma), 0.0)
	game.player.face_towards(toma.global_position)
	await wait(0.6)
	game.interact(toma.interact)
	await advance_dialogue(20, 1)
	var t := 0.0
	while game.mode != "credits" and t < 10.0:
		await wait(0.2)
		t += 0.2
	print("[autotest] credits: mode %s, given_to '%s', score '%s'" % [game.mode, GameState.flags.get("given_to", ""), game._score])
	for at in [2.5, 15.0, 30.0]:
		while t < at and game.mode == "credits":
			await wait(0.25)
			t += 0.25
		await shot("credits_%02d" % int(at))
	if game._credits:
		print("[autotest] credits: %d prints %s, names %s" % [game._credits.shown_prints.size(), game._credits.shown_prints.map(func(p): return String(p).get_file()), game._credits.names])
	t = 0.0
	while game.mode == "credits" and t < 30.0:
		await wait(0.25)
		t += 0.25
	print("[autotest] credits: over, mode %s, clock %s" % [game.mode, Chapters.clock_text()])
	await wait(1.4)
	await shot("post_first")
	await advance_dialogue(30, 2)
	await wait(4.0)
	await shot("recap")
	print("[autotest] recap: mode %s, lines %s" % [game.mode, game.menus.recap_shown])


## autotest=kebab | findmy | soleil (V2-26): chapter 4's three new minigames, each played with real keys from where the
## story starts it, with its a/b frames, its fail-forward, and how long it took.
func _ch4_minigame_plan(which: String) -> void:
	await wait(1.0)
	game.menus.close()
	game.camera_rig.clear_shot(true)
	game.resume()
	var sf: Dictionary = Chapters.get_chapter(4).get("start_flags", {})
	for k in sf:
		GameState.flags[k] = GameState._copy(sf[k])
	GameState.flags["chapter"] = 4
	GameState.flags["met_cristina"] = true
	GameState.flags["clock"] = Conditions.minutes({"kebab": "21:05", "findmy": "21:25", "soleil": "21:58"}.get(which, "21:00"))
	if which != "kebab":
		GameState.flags["kebab_done"] = true
		GameState.flags["pocket_empty"] = true
	if which == "findmy":
		GameState.flags["following"] = ["cristina"]
		GameState.flags["searching"] = true   # or the under_search trigger plays c4.search over the minigame
	# the minigame is started here, not by its scene: its main trigger must not play that scene over it
	GameState.flags["triggers_fired"] = ["under_search", "sm14_acu"]
	if which == "soleil":
		GameState.flags["found"] = true
		GameState.flags["anisha_sos"] = true
		GameState.flags["airpods_case"] = true
	game.world_env.apply_time("night")
	game._apply_stage(Chapters.get_chapter(4))
	await wait(0.6)
	if which == "findmy":
		game.place_at("mano", "under_entry")
		game.npcs["cristina"].global_position = game.player.global_position + Vector3(0.0, 0.0, 1.2)
	elif which == "soleil":
		game.place_at("mano", "sm14_soleil_start")
		game.place_at("acu", "acu_soleil")
	else:
		game.place_at("mano", "pasteur_east")
	await wait(1.0)
	var t0 := Time.get_ticks_msec() / 1000.0
	var res := [null]
	game.start_minigame(which, {}, func(r): res[0] = r)
	await wait(1.2)
	await shot(which + "_a")
	match which:
		"kebab":
			await _drive_kebab()
		"findmy":
			await _drive_findmy()
		"soleil":
			await _drive_soleil()
	var t := 0.0
	while game.minigame != null and t < 20.0:
		await wait(0.25)
		t += 0.25
	await wait(0.6)
	await shot(which + "_end")
	print("[autotest] %s: result %s after %.1f s (mode %s)" % [which, res[0], Time.get_ticks_msec() / 1000.0 - t0, game.mode])


func _move_to_option(mg, idx: int) -> void:
	var guard := 0
	while mg._sel != idx and guard < 12:
		await _key(KEY_RIGHT)
		await wait(0.12)
		guard += 1
	await _key(KEY_E)
	await wait(0.25)


func _drive_kebab() -> void:
	var kb = game.minigame
	var took := {}
	var guard := 0
	while is_instance_valid(kb) and kb.phase != "over" and guard < 400:
		guard += 1
		await wait(0.15)
		if not is_instance_valid(kb):
			break
		match String(kb.phase):
			"show":
				if not took.has("show"):
					took["show"] = true
					await wait(0.6)
					await shot("kebab_ticket")
			"build":
				var f := String(kb._fields()[kb._field])
				var opts: Array = kb.options(f)
				var want := opts.find(String(kb.order_of(kb._who()).get(f, "")))
				# the first two tickets wrong on purpose: Cristina's pencil line comes on the third
				if kb._r == 0 and kb._k < 2 and f == "sauce":
					want = (want + 1) % opts.size()
				if kb._help and not took.has("help"):
					took["help"] = true
					await wait(0.4)
					await shot("kebab_help")
					print("[autotest] kebab: Cristina's pencil line on %s's ticket (%s)" % [kb._who(), f])
				if not took.has("build"):
					took["build"] = true
					await wait(0.4)
					await shot("kebab_b")
				await _move_to_option(kb, want)
			"readback":
				var o: Dictionary = kb.order_of(kb._who())
				var right := String(kb._rb_cook) == String(o.get("sauce", ""))
				var pick := 0 if right else 1
				if kb._who() == "ian":
					pick = 0   # the cook's "ketchup" for Ian let through: a joke for the steps
				if not took.has("readback"):
					took["readback"] = true
					await wait(0.4)
					await shot("kebab_readback")
				await _move_to_option(kb, pick)
			"result":
				if not took.has("result_%d" % kb._r):
					took["result_%d" % kb._r] = true
					await shot("kebab_result_%d" % kb._r)
	print("[autotest] kebab: score %d of %d, wrong %s, Cristina helped %d, log %s" % [kb.score, kb.total, kb.wrong.keys(), kb.helped, kb.log_lines] if is_instance_valid(kb) else "[autotest] kebab: over")


func _drive_findmy() -> void:
	var fm = game.minigame
	var pod: Vector3 = fm.pod_pos
	var start: Vector3 = game.player.global_position
	print("[autotest] findmy: start %.1f m from the AirPod" % fm._dist())
	# one ring right on a thump: drowned out
	var guard := 0
	while fm._since_thump > 0.1 and guard < 60:
		await get_tree().process_frame
		guard += 1
	await _key(KEY_Q)
	await wait(0.6)
	await shot("findmy_drowned")
	# then closer and closer, each ring between two thumps
	for k in [0.35, 0.6, 0.8, 0.92]:
		var p: Vector3 = start.lerp(Vector3(pod.x, start.y, pod.z), k)
		game.player.teleport(p, atan2(pod.x - p.x, pod.z - p.z))
		game.camera_rig.snap_behind(game.player.facing_yaw())
		await wait(4.2)
		guard = 0
		while not (fm._since_thump > 0.6 and fm._since_thump < 0.9) and guard < 200:
			await get_tree().process_frame
			guard += 1
		await _key(KEY_Q)
		await wait(0.5)
		print("[autotest] findmy: %.1f m: signal %d, rings left %d, status '%s'" % [fm._dist(), fm.signal_now, fm.rings_left, fm._status.text])
		if k == 0.6:
			await shot("findmy_ring")
	# the battery is out: Cristina's phone
	await wait(4.2)
	await _key(KEY_Q)
	await wait(0.6)
	print("[autotest] findmy: rings %d (clear %d), Cristina's phone %s, hint %s" % [fm.rings, fm.clear_rings, fm.borrowed, fm._hinted])
	var near := Vector3(pod.x, start.y, pod.z) + (start - pod).normalized() * 1.2
	near.y = start.y
	game.player.teleport(near, atan2(pod.x - near.x, pod.z - near.z))
	game.camera_rig.snap_behind(game.player.facing_yaw())
	await wait(1.0)
	await shot("findmy_near")
	await _key(KEY_E)
	await wait(0.3)
	print("[autotest] findmy: found %s at %.1f m" % [fm.found if is_instance_valid(fm) else true, fm._dist() if is_instance_valid(fm) else 0.0])


func _drive_soleil() -> void:
	var so = game.minigame
	var t := 0.0
	var took := {}
	while is_instance_valid(so) and so.phase != "done" and t < 150.0:
		await wait(0.1)
		t += 0.1
		if not is_instance_valid(so):
			break
		# moves while he counts; through his first three looks too (caught), then freezes as he should
		var hold: bool = so.phase in ["count", "turn_back", "gave_up"] or (so.phase == "look" and so.catches < 3) or (so.phase == "stop" and so.catches < 3)
		if hold and not Input.is_action_pressed("move_forward"):
			Input.action_press("move_forward")
		elif not hold and Input.is_action_pressed("move_forward"):
			Input.action_release("move_forward")
		if so.phase == "look" and not took.has("look"):
			took["look"] = true
			await wait(0.3)
			await shot("soleil_look")
		if so.catches == 1 and not took.has("caught"):
			took["caught"] = true
			await shot("soleil_caught")
		if so.phase == "gave_up" and not took.has("gave_up"):
			took["gave_up"] = true
			await wait(0.6)
			await shot("soleil_gave_up")
		if so.s > so._len * 0.5 and so.catches >= 3 and not took.has("half"):
			took["half"] = true
			await shot("soleil_b")
	Input.action_release("move_forward")
	print("[autotest] soleil: %s after %.1f s, %d catches, at %.1f of %.1f m" % ["done" if not is_instance_valid(so) or so.phase == "done" else so.phase, t,
		so.catches if is_instance_valid(so) else 3, so.s if is_instance_valid(so) else 0.0, so._len if is_instance_valid(so) else 0.0])


## autotest=shots ids=a,b [mano=<point>] [chapter=<n>]: world.json shots as framed (a relative one around Mano at
## `mano`), one frame each, with that chapter's staging and light.
func _shots_plan() -> void:
	await wait(1.0)
	game.menus.close()
	game.resume()
	GameState.flags["toma"] = true
	_stage_chapter_arg()
	var ch := _chapter_arg()
	if Chapters.has(ch):
		game.world_env.apply_time(String(Chapters.get_chapter(ch).get("time", "golden")))
		game._show_lights()
	var ids: Array = []
	var mano := ""
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("ids="):
			ids = Array(arg.substr(4).split(","))
		elif arg.begins_with("mano="):
			mano = arg.substr(5)
	if mano != "":
		game.place_at("mano", mano)
	game.hud.set_hud_visible(false)
	await wait(2.0)
	for entry in ids:
		# `id@point` or `id@x:y:z` puts Mano there first (a world.json point, or game coordinates)
		var id := String(entry).get_slice("@", 0)
		var at := String(entry).get_slice("@", 1) if String(entry).contains("@") else ""
		if at.contains(":"):
			var c := at.split(":")
			game.player.teleport(Vector3(float(c[0]), float(c[1]), float(c[2])), game.player.facing_yaw())
		elif at != "":
			game.place_at("mano", at)
		game.mode = "dialogue"
		game.camera_shot(id)
		await wait(1.2)
		await shot("shot_" + id + ("_" + at.replace(":", "_") if at != "" else ""))
		var heads := {}
		for n in game.npcs:
			if game.npcs[n].visible:
				var h = game._in_frame(game.npcs[n].rig.head_position())
				if h != null:
					heads[n] = h
		heads["mano"] = game._in_frame(game.player.rig.head_position())
		print("[autotest] shot %s%s: camera %s, heads in the frame %s" % [id, " (Mano at %s)" % at if at != "" else "", game.camera_rig.cam.global_position.snapped(Vector3.ONE * 0.01), heads])
