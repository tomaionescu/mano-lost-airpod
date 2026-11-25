extends RefCounted
## Dev: the autotest plans for the collectibles, life on campus, the look-ats and the journal.
## autotest.gd hands them over: ducks, photos, overheard, looks [ids=a,b] [room=<zone>], side, idle,
## chapter_select, journal. Each logs "[life] ..." lines and shoots into shots=<dir> as the other plans do.
##   ducks: each chapter from the title, its ducks out (and not the later ones), each collected on foot; the two
##     night ones in their light; eight unlock the fit, twelve the duck page; the whisperer's hint and duck zero.
##   photos: each of Ishita's ten photo spots in its chapter: photo mode framed on it, C, on the film; the journal's
##     film page; a frame that misses (turned away) does not count.
##   overheard: each loop in its chapter, Mano walking up to the pair: the loop starts while he walks (he is never
##     frozen), its lines in the corner; one walked away from fades out.
##   looks: every look-at Mano can reach in its chapter (night ones at night too): the prompt it gets in front of
##     it, the thought or the insert, the floor under it.
##   side: the four side stories on screen (the survivor's sunset, the SUP woken by the horn, the waiting student,
##     the whisperer).
##   idle: Mano stands still: after 20 s he looks round or checks his phone, never frozen.
##   chapter_select: a night with a chocolatine in chapter 1 and a duck in chapter 2, then the title's Chapters page
##     and chapter 3 from it: the choice and the duck kept, no cold open, no dream.
##   journal: every tab of the notebook, in a chapter 3 night with things in it.

var at        # the autotest node (shot, wait, advance_dialogue, _key, _free_at)
var game


func _init(a) -> void:
	at = a
	game = a.game


func _ids() -> Array:
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("ids="):
			return Array(arg.substr(4).split(","))
	return []


func _arg(key: String, def := "") -> String:
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with(key + "="):
			return arg.substr(key.length() + 1)
	return def


## A clean night without playing the opening (New game would run the cold open, which hands over to chapter 1 by
## itself, under whatever the plan starts): no snapshots from an earlier run, the flags, the ducks and the film reset.
func _fresh() -> void:
	GameState.clear_save()
	GameState.clear_chapter_saves()
	GameState.reset_flags()
	game.ducks.restore([])
	game._clear_film()


## Chapter n from the title (its snapshot or start flags), past its card and start cue, in play; `flags` set on top.
func _chapter(n: int, flags := {}, keep := false) -> void:
	game.start_chapter(n, keep)
	await at.wait(0.5)
	await at._past_cutscene(30.0)
	await _talk_out()
	for k in flags:
		GameState.flags[k] = flags[k]
	game._refresh_presence()
	if game.mode != "play":
		game.resume()
	await at.wait(0.3)


func _talk_out() -> void:
	var g := 0
	while (game.dialogue.running or game.mode == "cutscene") and g < 200:
		g += 1
		if game.phone.is_open():
			game.phone.skip()
		if game.dialogue.running:
			game.dialogue._shown = 9999.0
			if not game.dialogue._choices.is_empty():
				game.dialogue._pick(0)
			else:
				game.dialogue._next()
		if game.minigame:
			game.minigame._done.call(true)
		if game.mode == "sit":
			game.end_sit()
		await at.wait(0.25)


## Mano a couple of metres from `p`, on a free spot, facing it.
func _stand_near(p: Vector3, r := 1.4) -> Vector3:
	var best := p + Vector3(r, 0.05, 0)
	for k in 12:
		var a := k * TAU / 12.0
		var q := p + Vector3(sin(a), 0, cos(a)) * r + Vector3(0, 0.05, 0)
		if at._free_at(q) and at._clear_line(p, q):
			best = q
			break
	game.player.teleport(best, 0.0)
	game.player.face_towards(p)
	game.camera_rig.snap_behind(game.player.facing_yaw())
	return best


# ------------------------------------------------------------------ ducks
func ducks() -> void:
	await at.wait(1.0)
	_fresh()
	var sec := WorldData.section("ducks")
	for n in range(1, 6):
		await _chapter(n, {}, true)   # chapter select's way: what was found in the last chapters stays found
		var out: Array = []
		var later: Array = []
		for it in game.ducks._items:
			if it.node.visible:
				out.append(it.id)
			elif int(it.chapter) > n:
				later.append(it.id)
		print("[life] ducks chapter %d (%s): out %s, not yet %s" % [n, game.world_env.time_of_day, out, later])
		for it in game.ducks._items:
			if int(it.chapter) != n or not it.node.visible:
				continue
			var p: Vector3 = it.node.global_position
			var stood := _stand_near(p, 2.2)
			# the duck on its own: Mano out of the way, the lens 1.5 m off it, a little above
			var side: Vector3 = (stood - p) * Vector3(1, 0, 1)
			side = side.normalized() if side.length() > 0.01 else Vector3(1, 0, 0)
			game.player.teleport(stood + side * 3.0, 0.0)
			game.camera_rig.set_shot(p + side * 1.5 + Vector3.UP * 0.55, p, 38.0, 1.6, true)
			await at.wait(1.0)
			await at.shot("duck_%s" % it.id)
			game.camera_rig.clear_shot(true)
			var space: PhysicsDirectSpaceState3D = game.get_world_3d().direct_space_state
			var hit := space.intersect_ray(PhysicsRayQueryParameters3D.create(p + Vector3.UP * 0.3, p + Vector3.DOWN * 2.0, 1))
			var gap: float = p.y - hit.position.y if not hit.is_empty() else INF
			# walk into it, as a player would
			var back: Vector3 = (stood - p) * Vector3(1, 0, 1)
			game.player.teleport(Vector3(p.x, stood.y, p.z) + back.normalized() * 1.6, 0.0)
			game.player.face_towards(p)
			game.camera_rig.snap_behind(game.player.facing_yaw())
			var before: int = game.ducks.count()
			Input.action_press("move_forward")
			var w := 0.0
			while game.ducks.count() == before and w < 3.0:
				await at.wait(0.1)
				w += 0.1
			Input.action_release("move_forward")
			if game.ducks.count() == before:
				game.player.teleport(Vector3(p.x, stood.y, p.z), 0.0)   # the walk was blocked: right onto it
				await at.wait(0.4)
			print("[life] duck %s (chapter %d%s): %s, %.2f m over the floor, %d of %d, merch %s, all %s" % [it.id, n, ", glows" if it.glow else "",
				"COLLECTED" if game.ducks.count() > before else "NOT COLLECTED", gap, game.ducks.count(), game.ducks.total(),
				GameState.flags.get("merch", false), GameState.flags.get("ducks_all", false)])
			await at.wait(0.6)
		if n == 2:
			# the whisperer at six ducks: a hint
			await _whisperer("whisperer_hint")
	await _whisperer("whisperer_zero")
	game.menus.show_journal(3)
	await at.wait(1.0)
	await at.shot("journal_ducks")
	print("[life] ducks done: %d of %d, merch %s, ducks_all %s, duck_zero %s, by chapter %s" % [game.ducks.count(), game.ducks.total(),
		GameState.flags.get("merch", false), GameState.flags.get("ducks_all", false), GameState.flags.get("duck_zero", false), game.ducks.by_chapter()])
	game.resume()


func _whisperer(name: String) -> void:
	var w = game.npcs.get("whisperer")
	if w == null or not w.visible:
		print("[life] the duck whisperer is not on campus")
		return
	game.player.teleport(at._free_spot_near(w, 1.3), 0.0)
	game.player.face_towards(w.global_position)
	await at.wait(0.4)
	var tg = game.player.find_interactable()
	print("[life] %s: prompt on '%s'" % [name, tg.id if tg else "nothing"])
	game.interact(w.interact)
	var k := 0
	while game.dialogue.running and k < 14:
		await at.wait(1.0)
		if k == 1 or not game.dialogue._choices.is_empty():
			await at.shot("%s_%d" % [name, k])
		print("[life]   %s" % game.dialogue._text)
		game.dialogue._shown = 9999.0
		if not game.dialogue._choices.is_empty():
			game.dialogue._pick(0)
		else:
			game.dialogue._next()
		k += 1
	await at.wait(1.0)
	print("[life] %s: hints %d, duck_zero %s" % [name, GameState.flags.get("duck_hints", 0), GameState.flags.get("duck_zero", false)])


# ------------------------------------------------------------------ Ishita's film
func photos() -> void:
	await at.wait(1.0)
	_fresh()
	var all := Film.spots()
	var ids := _ids()
	var order := [1, 2, 3]
	var missed_done := false
	for n in order:
		var flags := {"camera": true}
		if n == 2:
			# the Under's main trigger (Joaquin's intro) would start over photo mode at the stickers and the sofa
			flags["lf_twist"] = false
			flags["joaquin_met"] = true
		await _chapter(n, flags, true)
		for id in all:
			var s: Dictionary = all[id]
			if not ids.is_empty() and not id in ids:
				continue
			if int(s.chapter) != n:
				continue
			if Film.taken().has(id) or not Film.open_now(s):
				continue
			# Mano a little ahead of the photographer's spot, toward what is framed; photo mode's camera behind him
			var look: Vector3 = s.look if s.look != null else s.pos + Vector3(0, 1.2, 0) + Vector3(0, 0, -1.5)
			var dir: Vector3 = (look - s.pos)
			dir.y = 0.0
			dir = dir.normalized() if dir.length() > 0.01 else Vector3(0, 0, -1)
			var mano: Vector3 = s.pos + dir * 1.2 + Vector3(0, 0.05, 0)
			if not at._free_at(mano):
				mano = s.pos + Vector3(0, 0.05, 0)
			game.player.teleport(mano, atan2(dir.x, dir.z))
			game.camera_rig.snap_behind(game.player.facing_yaw())
			await at.wait(0.6)
			game.menus.show_photo()
			await at.wait(0.2)
			# the orbit camera behind Mano, looking past him at what is framed
			game.menus._photo.yaw = atan2(-dir.x, -dir.z)
			game.menus._photo.pitch = 0.12
			game.menus._photo.dist = 2.0
			game.menus._photo.height = clampf(look.y - mano.y, 0.6, 1.8)
			if not missed_done:
				# first, turned away from it: the note stays empty and C keeps a photo for the player only
				missed_done = true
				game.menus._photo.yaw += PI * 0.75
				await at.wait(0.9)
				print("[life] photo %s turned away: framed '%s'" % [id, game.menus.photo_framed.get("id", "")])
				game.menus._photo.yaw -= PI * 0.75
			await at.wait(1.0)
			var framed := String(game.menus.photo_framed.get("id", ""))
			await at.shot("photo_%s_framed" % id)
			var before := int(GameState.flags.get("film_shots", 0))
			await at._key(KEY_C)
			await at.wait(0.8)
			print("[life] photo %s (chapter %d): framed '%s', note '%s', film %d -> %d, on the film %s" % [id, n, framed,
				game.menus._film_note.text if game.menus._film_note else "", before, int(GameState.flags.get("film_shots", 0)), Film.taken().has(id)])
			await at._key(KEY_P)
			await at.wait(0.5)
	# the tour's and the sunset's `$ photo film` are story ones: one where no spot is near, one where the spot is taken
	print("[life] film: %d spots on the film %s, %d exposures, %d left" % [Film.taken().size(), Film.taken(), int(GameState.flags.get("film_shots", 0)), Film.left()])
	game.menus.show_journal(2)
	await at.wait(1.0)
	await at.shot("journal_film")
	game.resume()


# ------------------------------------------------------------------ overheard talk
func overheard() -> void:
	await at.wait(1.0)
	_fresh()
	var sec := WorldData.section("overheard")
	var ids := _ids()
	var by_chapter := {}
	for id in sec:
		if not ids.is_empty() and not id in ids:
			continue
		var n := _first_chapter(String(sec[id].get("when", "")))
		if not by_chapter.has(n):
			by_chapter[n] = []
		by_chapter[n].append(id)
	var fired := 0
	var tried := 0
	for n in [1, 2, 3, 4]:
		if not by_chapter.has(n):
			continue
		for id in by_chapter[n]:
			var e: Dictionary = sec[id]
			var flags := _flags_for(String(e.get("when", "")))
			await _chapter(n, flags)
			tried += 1
			var p: Array = game.overheard.pair_of(e)
			if p.is_empty() or not p[0].visible or not p[1].visible:
				print("[life] overheard %s (chapter %d): the pair is not on campus (%s)" % [id, n, p.map(func(x): return x.id if x else "?")])
				continue
			var mid: Vector3 = (p[0].global_position + p[1].global_position) * 0.5
			# 10 m off, on a free spot in view of them, then walking in
			var start := mid
			var radius: float = float(e.get("radius", 6.0))
			var found := false
			for dist in [radius + 3.0, radius + 1.5, radius * 0.8]:
				for k in 16:
					var a := k * TAU / 16.0
					var q: Vector3 = mid + Vector3(sin(a), 0, cos(a)) * dist
					q.y = mid.y
					if at._free_at(q) and at._clear_line(mid, q):
						start = q
						found = true
						break
				if found:
					break
			game.overheard.only = id
			game.player.teleport(start + Vector3(0, 0.05, 0), 0.0)
			game.player.face_towards(mid)
			game.camera_rig.snap_behind(game.player.facing_yaw())
			await at.wait(0.6)
			game.overheard._stop(false)
			game.overheard._last_end.erase(id)
			game.overheard._gap = 0.0
			Input.action_press("move_forward")
			var w := 0.0
			var started_at := -1.0
			var frozen_seen := false
			var moved_while := 0.0
			var last: Vector3 = game.player.global_position
			while w < 9.0:
				await at.wait(0.1)
				w += 0.1
				if game.overheard.playing() == id and started_at < 0.0:
					started_at = w
				if started_at >= 0.0:
					frozen_seen = frozen_seen or game.player.frozen or game.mode != "play"
					moved_while += game.player.global_position.distance_to(last)
				last = game.player.global_position
				if started_at >= 0.0 and w - started_at > 1.6:
					break
				if game.player.global_position.distance_to(mid) < 2.2:
					Input.action_release("move_forward")
			Input.action_release("move_forward")
			if started_at >= 0.0:
				fired += 1
				await at.wait(0.4)
				await at.shot("over_%s" % id)
			print("[life] overheard %s (chapter %d, %s): %s while walking (%.1f m walked during it), Mano frozen %s, line '%s'" % [id, n,
				game.world_env.time_of_day, ("STARTED %.1f s in" % started_at) if started_at >= 0.0 else "NOT STARTED", moved_while, frozen_seen,
				game.overheard.line_text()])
			# stand and hear it out
			var h := 0.0
			while game.overheard.playing() == id and h < 30.0:
				await at.wait(0.5)
				h += 0.5
			print("[life] overheard %s: heard %s" % [id, id in GameState.flags.get("overheard", [])])
			game.overheard.only = ""
	# walking away fades one out
	if by_chapter.has(2):
		var id: String = by_chapter[2][0]
		var e: Dictionary = sec[id]
		await _chapter(2, _flags_for(String(e.get("when", ""))))
		GameState.flags["overheard"] = []
		game.overheard.only = id
		game.overheard._stop(false)
		game.overheard._last_end.clear()
		game.overheard._gap = 0.0
		var p: Array = game.overheard.pair_of(e)
		if not p.is_empty():
			var mid: Vector3 = (p[0].global_position + p[1].global_position) * 0.5
			_stand_near(mid, 3.0)
			var w := 0.0
			while game.overheard.playing() == "" and w < 4.0:
				await at.wait(0.2)
				w += 0.2
			var away: Vector3 = game.player.global_position + (game.player.global_position - mid).normalized() * 12.0
			game.player.teleport(away, 0.0)
			await at.wait(1.0)
			print("[life] overheard walked away from %s: still playing '%s' (should be empty)" % [id, game.overheard.playing()])
	print("[life] overheard: %d of %d loops started while Mano walked" % [fired, tried])


func _first_chapter(expr: String) -> int:
	var m := RegEx.create_from_string("chapter\\s*(==|>=)\\s*(\\d+)").search(expr)
	return int(m.get_string(2)) if m else 1


## The flags a loop's `when` wants, beyond its chapter (staging and the story's state, roughly).
func _flags_for(expr: String) -> Dictionary:
	var f := {}
	if expr.contains("choco != \"\""):
		f["choco"] = "pac"
	if expr.contains("joaquin_met"):
		f["joaquin_met"] = true
	if expr.contains("tour_count >= 3"):
		f["tour_count"] = 3
	if expr.contains("not karim"):
		f["karim"] = false
	if expr.contains("chapter == 2") or expr.contains("chapter >= 2"):
		f["joaquin_met"] = true   # Joaquin's intro (the Under's main trigger) would cut the loop off
	if expr.contains("not coffee_given"):
		f["coffee_given"] = false
	if expr.contains("not summit_done"):
		f["summit_done"] = false
	return f


# ------------------------------------------------------------------ look-ats and readables
func looks() -> void:
	await at.wait(1.0)
	_fresh()
	var ids := _ids()
	var room := _arg("room")
	var night := "night" in OS.get_cmdline_user_args()
	var sec := WorldData.section("spots")
	var space: PhysicsDirectSpaceState3D = game.get_world_3d().direct_space_state
	var n_ok := 0
	var n_all := 0
	var bad: Array = []
	var chapter := 4 if night else 2
	await _chapter(chapter, {"camera": true})
	for id in sec:
		if not ids.is_empty() and not id in ids:
			continue
		var e: Dictionary = sec[id]
		var pos := WorldData.vec(e.pos)
		var zone := String(game.binder.zone_at(pos).get("id", ""))
		if room != "" and zone != room:
			continue
		if String(e.get("when", "")) != "" and not Conditions.eval(String(e.when)):
			continue
		n_all += 1
		var hit := space.intersect_ray(PhysicsRayQueryParameters3D.create(pos + Vector3.UP * 1.2, pos + Vector3.DOWN * 1.5, 1))
		var floor_y: float = hit.position.y if not hit.is_empty() else INF
		var stood := _stand_near(pos, minf(float(e.get("range", 1.8)) * 0.6, 1.1))
		await at.wait(0.5)
		var tg = game.player.find_interactable()
		var got := String(tg.id) if tg else "nothing"
		if got != String(id) and tg:
			# the prompt went to something else: from straight in front of the spot instead
			game.player.teleport(pos + (stood - pos).normalized() * 0.5, 0.0)
			game.player.face_towards(pos)
			await at.wait(0.3)
			tg = game.player.find_interactable()
		var got2 := String(tg.id) if tg else "nothing"
		var it = null
		for x in game.interactables:
			if x.id == String(id) and x.kind == "spot":
				it = x
		var thought := ""
		if it:
			game.interact(it)
			await at.wait(0.9)
			thought = game.dialogue._text if game.dialogue.running else game.dialogue.bark_text()
			await at.shot("look_%s" % id)
			await _talk_out()
			game.dialogue.clear_barks()
			if game.mode != "play":
				game.resume()
		var fl := absf(floor_y - pos.y) if floor_y != INF else INF
		var ok := got == String(id) or got2 == String(id)
		n_ok += 1 if ok else 0
		if not ok or fl > 0.35:
			bad.append(id)
		print("[life] look %s (%s, %s): prompt '%s'%s, floor %s%s, thought '%s'" % [id, zone, e.get("kind", "look"), got,
			"" if got == got2 else " then '%s'" % got2, "none" if floor_y == INF else "%.2f" % (floor_y - pos.y),
			"" if fl <= 0.35 else "  OFF THE FLOOR", thought])
	print("[life] looks: %d of %d got their own prompt; to check: %s" % [n_ok, n_all, bad])


# ------------------------------------------------------------------ side stories
func side() -> void:
	await at.wait(1.0)
	_fresh()
	# "Is the sun still yellow?": asked in chapter 2 before the twist, at the planter wall for the sunset
	await _chapter(2)
	var s2 = game.npcs.get("student2")
	await _talk_with(s2, "survivor_ask")
	print("[life] survivor: survivor_out %s" % GameState.flags.get("survivor_out", false))
	GameState.flags["lf_twist"] = true
	game._refresh_presence()
	await at.wait(0.5)
	print("[life] survivor after the twist: at %s (planter_survivor %s)" % [s2.global_position.snapped(Vector3.ONE * 0.1), WorldData.point("planter_survivor").pos])
	game.time_cut("last_light", 0.2)
	await at.wait(1.0)
	game.say(game.story.steps("c2.sunset"))
	var k := 0
	while game.dialogue.running and k < 24:
		await at.wait(1.0)
		if game.dialogue._text.contains("Orange") or game.dialogue._text.contains("still there"):
			await at.shot("survivor_sunset_%d" % k)
		game.dialogue._shown = 9999.0
		if not game.dialogue._choices.is_empty():
			game.dialogue._pick(1 if game.dialogue._text.contains("Sit, or go") else 0)
		else:
			game.dialogue._next()
		k += 1
	await at.wait(1.0)
	await _talk_out()
	print("[life] survivor: survivor_sun %s" % GameState.flags.get("survivor_sun", false))
	# "Segmentation fault": the horn in the Under, then Amphi 4 before 19:00
	await _chapter(2, {"sup_clue": true})
	var horn = null
	for x in game.interactables:
		if x.id == "horn":
			horn = x
	if horn:
		_stand_near(horn.pos, 1.0)
		await at.wait(0.5)
		var tg = game.player.find_interactable()
		print("[life] horn: prompt on '%s' (%s)" % [tg.id if tg else "nothing", tg.label if tg else ""])
		await at.shot("horn_prompt")
		game.interact(horn)
		await at.wait(1.0)
		await _talk_out()
	print("[life] horn: %s" % GameState.flags.get("horn", false))
	GameState.flags["clock"] = Conditions.minutes("18:44")
	var sl = game.npcs.get("sleeper")
	await _talk_with(sl, "sup_horn")
	print("[life] sup: awake %s, how '%s'" % [GameState.flags.get("sup_awake", false), GameState.flags.get("sup_how", "")])
	await _chapter(4, {"sup_awake": true, "sup_how": "horn"})
	sl = game.npcs.get("sleeper")
	print("[life] sup in chapter 4: at %s, eyes %.1f" % [sl.global_position.snapped(Vector3.ONE * 0.1), sl.rig.eyes_closed])
	await _talk_with(sl, "sup_passed")
	print("[life] sup: sup_after %s" % GameState.flags.get("sup_after", false))
	# "Back in 5 min": served (chapter 2, Mme Dupont back), goodnight (chapter 4)
	await _chapter(2, {"coffee_given": true})
	await _talk_with(game.npcs.get("waiting"), "waiting_served")
	await _chapter(4, {"side_waiting": true})
	await _talk_with(game.npcs.get("waiting"), "waiting_bye")
	await at.wait(0.6)
	print("[life] waiting: side_waiting %s, waiting_bye %s, still on campus %s" % [GameState.flags.get("side_waiting", false),
		GameState.flags.get("waiting_bye", false), game.npcs["waiting"].visible])
	# the whisperer, met
	await _chapter(1)
	await _whisperer("whisperer_meet")
	game.menus.show_journal(5)
	await at.wait(1.0)
	await at.shot("journal_side")
	game.resume()


func _talk_with(n, name: String) -> void:
	if n == null or not n.visible:
		print("[life] %s: nobody there" % name)
		return
	game.player.teleport(at._free_spot_near(n, 1.3), 0.0)
	game.player.face_towards(n.global_position)
	await at.wait(0.4)
	game.interact(n.interact)
	var k := 0
	while game.dialogue.running and k < 20:
		await at.wait(0.9)
		if k == 1 or k == 3 or not game.dialogue._choices.is_empty():
			await at.shot("%s_%d" % [name, k])
		print("[life]   %s: %s" % [name, game.dialogue._text])
		game.dialogue._shown = 9999.0
		if not game.dialogue._choices.is_empty():
			game.dialogue._pick(0)
		else:
			game.dialogue._next()
		k += 1
	await at.wait(0.8)
	await _talk_out()


# ------------------------------------------------------------------ idle life
func idle() -> void:
	await at.wait(1.0)
	_fresh()
	for n in [1, 3]:
		await _chapter(n)
		# somewhere no story trigger fires: rue Pasteur's north pavement (chapter 1's pastry war is in the court)
		game.player.teleport(Vector3(20.0, 0.15, -4.6), -PI / 2)
		game.camera_rig.snap_behind(0.0)
		var before: int = game.idle_beats.size()
		var t := 0.0
		while game.idle_beats.size() == before and t < 26.0:
			await at.wait(0.5)
			t += 0.5
		await at.wait(0.6)
		await at.shot("idle_ch%d" % n)
		print("[life] idle chapter %d: %s after %.1f s standing, mode %s, frozen %s" % [n, game.idle_beats.slice(before), t, game.mode, game.player.frozen])
		Input.action_press("move_forward")
		await at.wait(0.5)
		Input.action_release("move_forward")
		print("[life] idle chapter %d: moving again resets it (%.1f s)" % [n, game._idle_t])


# ------------------------------------------------------------------ chapter select
func chapter_select() -> void:
	await at.wait(1.0)
	# a night: chapter 1 with a chocolatine, a duck in chapter 2, then on into chapter 3 (each card writes its snapshot)
	_fresh()
	await _chapter(1)
	GameState.flags["choco"] = "choco"
	GameState.flags["ines"] = true
	GameState.flags["c1_done"] = true
	game.begin_chapter(2)
	await at.wait(0.5)
	await at._past_cutscene(20.0)
	await _talk_out()
	var d2 := ""
	for it in game.ducks._items:
		if int(it.chapter) == 2:
			d2 = it.id
			game.ducks._collect(it)
			break
	GameState.flags["c2_done"] = true
	game.begin_chapter(3)
	await at.wait(0.5)
	await at._past_cutscene(20.0)
	await _talk_out()
	game.save()
	print("[life] select: night played to chapter 3, snapshots %s, choco '%s', duck %s" % [GameState.chapter_saves(), GameState.flags.get("choco", ""), d2])
	# a later duck after the snapshot: chapter select must keep it
	for it in game.ducks._items:
		if int(it.chapter) == 3:
			game.ducks._collect(it)
			print("[life] select: and %s found in chapter 3, after its snapshot" % it.id)
			break
	game.save()
	game.show_title()
	await at.wait(2.0)
	await at.shot("title_with_chapters")
	var page_btn = null
	for b in game.menus.current.find_children("*", "Button", true, false):
		if (b as Button).text == "Chapters":
			page_btn = b
	print("[life] select: the title has Chapters %s" % (page_btn != null))
	game.menus.show_chapters()
	await at.wait(1.0)
	await at.shot("chapters_page")
	var btn3 = null
	for b in game.menus.current.find_children("*", "Button", true, false):
		print("[life] select:   page item '%s'" % (b as Button).text)
		if (b as Button).text.begins_with("3"):
			btn3 = b
	if btn3 == null:
		print("[life] select: NO chapter 3 on the page")
		return
	(btn3 as Button).grab_focus()
	await at.wait(0.3)
	# a night is in progress (the save above): the page asks first, "Keep my night" circled; Esc keeps the night
	var before = GameState.read_save()
	await at._key(KEY_ENTER)
	await at.wait(1.0)
	await at.shot("chapters_confirm")
	var words := []
	var focused := ""
	for b in game.menus.current.find_children("*", "Button", true, false):
		words.append((b as Button).text)
		if (b as Button).has_focus():
			focused = (b as Button).text
	print("[life] select: asked first: %s, circled '%s', mode %s" % [words, focused, game.mode])
	await at._key(KEY_ESCAPE)
	await at.wait(1.0)
	var after = GameState.read_save()
	btn3 = null
	for b in game.menus.current.find_children("*", "Button", true, false):
		if (b as Button).text.begins_with("3"):
			btn3 = b
	print("[life] select: Esc -> back on the chapter list %s, save kept %s (chapter %s pos %s)" % [btn3 != null,
		before.get("pos") == after.get("pos") and before.get("chapter") == after.get("chapter"), after.get("chapter"), after.get("pos")])
	if btn3 == null:
		return
	(btn3 as Button).grab_focus()
	await at.wait(0.3)
	await at._key(KEY_ENTER)
	await at.wait(1.0)
	for b in game.menus.current.find_children("*", "Button", true, false):
		if (b as Button).text == "Go back":
			(b as Button).grab_focus()
	await at.wait(0.3)
	await at._key(KEY_ENTER)
	await at.wait(1.0)
	var dream: bool = game.dream_player != null
	await at._past_cutscene(20.0)
	await at.wait(1.0)
	await at.shot("chapter_3_from_select")
	print("[life] select: chapter %d, choco '%s' (kept: %s), ducks %s, dream %s, cold open %s, mode %s" % [Chapters.current(),
		GameState.flags.get("choco", ""), GameState.flags.get("choco", "") == "choco", GameState.ducks_found, dream,
		GameState.flags.get("cold_open_seen", false), game.mode])


# ------------------------------------------------------------------ the journal
func journal() -> void:
	await at.wait(1.0)
	_fresh()
	var sf: Dictionary = Chapters.get_chapter(4).get("start_flags", {})
	await _chapter(3, {"sup_clue": true, "survivor_out": true, "survivor_sun": true, "side_waiting": true, "whisperer_met": true, "film_shots": 3,
		"photos_taken": sf.get("photos_taken", {}), "moments": ["sit_bay", "sit_planter"]})
	for k in ["tour_count", "tour_amphi", "tour_stickers", "tour_velib", "ishita_fav", "cristina_texted", "summit_done"]:
		if sf.has(k):
			GameState.flags[k] = sf[k]
	game.menus.show_journal(0)
	for i in game.menus.JOURNAL_TABS.size():
		await at.wait(0.9)
		await at.shot("journal_%d_%s" % [i, String(game.menus.JOURNAL_TABS[i]).replace(" ", "_")])
		print("[life] journal tab %d '%s'" % [i, game.menus.JOURNAL_TABS[i]])
		await at._key(KEY_D)
	await at.wait(0.6)
	print("[life] journal: back on tab %d after a full turn" % game.menus.journal_tab)
	await at._key(KEY_TAB)
	await at.wait(0.6)
	print("[life] journal closed: mode %s" % game.mode)
	# with a pad in use, the hint names the pad's buttons
	GameState.using_pad = true
	game.menus.show_journal(0)
	await at.wait(0.9)
	for l in game.menus.current.find_children("*", "Label", true, false):
		if (l as Label).text.contains("turn the page"):
			print("[life] journal hint with a pad: '%s'" % (l as Label).text)
	await at.shot("journal_pad_hint")
	GameState.using_pad = false
	await at._key(KEY_TAB)
	await at.wait(0.6)


# ------------------------------------------------------------------ the M map
func map() -> void:
	await at.wait(1.0)
	_fresh()
	for n in [1, 3, 5]:
		var seen := ["amphi", "court", "passage", "street"]
		if n >= 3:
			seen += ["volt_gf", "volt_f1", "sm14", "under", "cafe"]
		await _chapter(n, {"zones_seen": seen})
		if n == 5:
			game.player.teleport(WorldData.point("steps5_mano").pos + Vector3(0, 0.05, 0), 0.0)
		await at.wait(0.5)
		game.menus.show_map()
		await at.wait(1.2)
		await at.shot("map_ch%d" % n)
		var mv = game.menus._map_view
		var all: Array = mv.static_rects + mv.overlay_rects
		var overlaps := 0
		for i in all.size():
			for j in range(i + 1, all.size()):
				if (all[i] as Rect2).intersects(all[j] as Rect2):
					overlaps += 1
		var on_dots := 0
		for r in mv.overlay_rects:
			for d in mv.overlay_dots:
				if (r as Rect2).intersects(d as Rect2):
					on_dots += 1
		print("[life] map chapter %d: %d static labels, %d live ones, %d overlapping pairs, %d live labels over %d dots, sheet %s" % [n,
			mv.static_rects.size(), mv.overlay_rects.size(), overlaps, on_dots, mv.overlay_dots.size(), mv.sheet])
		await at._key(KEY_M)
		await at.wait(0.5)
		print("[life] map closed: mode %s" % game.mode)
