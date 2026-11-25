extends RefCounted
## Shared pieces for the headless tests (tests/test_runner.gd): a report that counts, a stand-in for main.gd with
## the calls Story and StoryCommands make, and a dialogue runner that plays compiled steps without a screen.

const MARKERS := "res://tests/fixtures/markers.json"


static func read_json(path: String):
	if not FileAccess.file_exists(path):
		return null
	var j := JSON.new()
	if j.parse(FileAccess.get_file_as_string(path)) != OK:
		return null
	return j.data


static func v3(a) -> Vector3:
	return Vector3(float(a[0]), float(a[1]), float(a[2])) if a is Array and a.size() >= 3 else Vector3.ZERO


## Counts checks; a failed check prints at once, passing ones only in the totals.
class Report:
	extends RefCounted
	var name := ""
	var passed := 0
	var failed := 0
	var warned := 0
	var fails: Array = []

	func ok(cond: bool, msg: String) -> bool:
		if cond:
			passed += 1
		else:
			failed += 1
			fails.append(msg)
			print("[test]   FAIL %s: %s" % [name, msg])
		return cond

	func fail(msg: String) -> void:
		ok(false, msg)

	func warn(msg: String) -> void:
		warned += 1
		print("[test]   warn %s: %s" % [name, msg])

	func info(msg: String) -> void:
		print("[test]   %s: %s" % [name, msg])


## Plays compiled steps the way Dialogue does (Callables run, a choice continues with the rest of the queue), with
## no screen: every card shown is recorded, and `choose` (Callable: choice step -> index) answers questions.
class HeadlessDialogue:
	extends RefCounted
	var queue: Array = []
	var running := false
	var shown: Array = []        # [who, text] in order
	var choices: Array = []      # [line text, [labels], picked index]
	var choose: Callable
	var _ended := false

	func say(steps: Array) -> void:
		queue = steps.duplicate()
		running = true
		_ended = false
		var guard := 0
		while not queue.is_empty() and guard < 2000:
			guard += 1
			var step = queue.pop_front()
			if step is Callable:
				step.call()
				if _ended:
					break
				continue
			if step is Array:
				shown.append([String(step[0]), String(step[1])])
				continue
			if step is Dictionary:
				shown.append([String(step.who), String(step.t)])
				var ask: Array = step.get("ask", [])
				if ask.is_empty():
					continue
				var i: int = choose.call(step) if choose.is_valid() else 0
				i = clampi(i, 0, ask.size() - 1)
				var labels: Array = []
				for a in ask:
					labels.append(String(a[0]))
				choices.append([String(step.t), labels, i])
				queue = ask[i][1] + queue
		running = false
		_ended = false
		queue.clear()

	func push(s: Array) -> void:
		queue = s + queue

	func jump(s: Array) -> void:
		queue = s.duplicate()

	func end_now() -> void:
		queue.clear()
		_ended = true

	func pause_for(_s: float) -> void:
		pass


class FakeHud:
	extends RefCounted
	var banners: Array = []
	var hints: Array = []

	func show_banner(title: String, sub := "") -> void:
		banners.append([title, sub])

	func hint(id: String) -> void:
		hints.append(id)

	func set_objective(_t: String, _flash := true) -> void:
		pass


class FakePlayer:
	extends RefCounted
	var airpods := 1

	func give_second_airpod() -> void:
		airpods = 2

	var stowed := false

	func stow_airpods(in_case: bool, _both := false) -> void:
		stowed = in_case


class FakeEnv:
	extends RefCounted
	var lamps: Array = []

	func set_lamps(group: String, level: float, seconds := 0.0) -> void:
		lamps.append([group, level, seconds])


## main.gd as the story sees it. Conversations and minigames started from a step wait in `pending` /
## `minigames` until the current one is over, as they would on screen; positions come from the level's markers
## (tests/fixtures/markers.json) and data/world.json.
class FakeGame:
	extends RefCounted
	var dialogue := HeadlessDialogue.new()
	var hud := FakeHud.new()
	var player := FakePlayer.new()
	var world_env := FakeEnv.new()
	var story: Story
	var markers: Dictionary = {}
	var pos := Vector3.ZERO
	var pending: Array = []       # [steps, with]
	var minigames: Array = []     # [name, opts, cb]
	var chapters_begun: Array = []
	var ended := false
	var toasts: Array = []
	var times: Array = []
	var log: Array = []
	var restaged: Array = []      # ids main.restage() would have moved (`$ stage now`, `$ follow`, `$ unfollow`)
	var phone_log: Array = []     # [action, who, text]
	var shots: Array = []

	func _init() -> void:
		var m = load("res://tests/support.gd").read_json("res://tests/fixtures/markers.json")
		markers = m if m is Dictionary else {}
		story = Story.new(self)

	func say(steps: Array, with_npc := "") -> void:
		pending.append([steps, with_npc])

	func start_minigame(name: String, opts: Dictionary, cb: Callable) -> void:
		minigames.append([name, opts, cb])
		log.append("minigame %s %s" % [name, opts])

	var card_clocks: Array = []   # [n, the story clock just before chapter n's card]

	func begin_chapter(n: int, _replay := false) -> void:
		if not Chapters.has(n):
			card_clocks.append([n, Chapters.clock()])
			log.append("bridge to the ending (no chapter %d)" % n)
			say(story.steps("bridge.end"))
			return
		var ch: Dictionary = Chapters.get_chapter(n)
		card_clocks.append([n, Chapters.clock()])
		GameState.flags["chapter"] = n
		GameState.flags["banners"] = []
		var m := Conditions.minutes(String(ch.get("clock", "")))
		if m >= 0:
			GameState.flags["clock"] = m
		GameState.flags["time"] = String(ch.get("time", GameState.flags.get("time", "golden")))
		chapters_begun.append(n)
		log.append("chapter %d card '%s' at %s, %s" % [n, ch.get("card", {}).get("chapter", ""), ch.get("clock", ""), ch.get("time", "")])
		Chapters.reset_tracking()
		var cue := String(ch.get("start_cue", ""))
		if cue != "":
			say(story.steps(cue), String(ch.get("start_with", "")))

	func show_ending() -> void:
		ended = true
		log.append("ending")

	func toast(text: String, _doodle := "") -> void:
		toasts.append(text)

	func drop_airpod(_grate := false) -> void:
		player.airpods = 1

	# the finale as main.gd plays it, with nothing on screen
	var photos: Array = []        # `$ photo` kinds, in order
	var credits_rolled := 0
	var recap_shown := false
	var score := ""
	var captions: Array = []

	func take_photo(kind: String) -> float:
		photos.append(kind)
		log.append("photo %s" % kind)
		if kind == "film":
			# as main.take_photo: the photo spot where Mano stands goes on Ishita's film
			log.append("film %s" % Film.take_at(pos))
		return 0.0

	func set_airpods(where: String) -> void:
		GameState.flags["airpods_case"] = where == "case"
		player.stow_airpods(where == "case")
		log.append("airpods %s" % where)

	func set_score(stem: String) -> void:
		score = stem
		log.append("score %s" % stem)

	func caption(text: String, _seconds := 2.4) -> float:
		captions.append(text)
		return 0.0

	func freeze_frame() -> void:
		log.append("freeze")

	## The credits roll, then the post-credits as a conversation with Mme Dupont (main._post_credits).
	func roll_credits() -> void:
		credits_rolled += 1
		log.append("credits")
		GameState.flags["clock"] = Conditions.minutes("24:25")
		say(story.steps("post.credits"), "madame2")

	func show_recap() -> void:
		recap_shown = true
		ended = true
		GameState.flags["credits_done"] = true
		log.append("recap")

	func time_cut(preset: String, _fade := 0.6) -> void:
		GameState.flags["time"] = preset
		times.append(preset)

	func zone_id() -> String:
		return ""

	func restage(id: String) -> void:
		restaged.append(id)

	func place_at(who: String, point: String) -> void:
		log.append("place %s at %s" % [who, point])
		if who == "mano":
			var p := WorldData.point(point)
			if not p.is_empty():
				pos = p.pos

	func camera_shot(name: String, _cut := true) -> void:
		shots.append(name)

	## The phone as main.phone_cmd changes the flags (charge, flood, finder); nothing waits on it here.
	func phone_cmd(action: String, who := "", text := "") -> float:
		phone_log.append([action, who, text])
		log.append("phone %s %s" % [action, who])
		match action:
			"charge":
				GameState.flags["phone_charged"] = true
			"flood":
				Chat.deliver(who)
			"finder":
				GameState.flags["finder_place"] = who
				GameState.flags["finder_time"] = text
		return 0.0

	var sits: Array = []          # the sit-downs begun (`$ sit`): Mano stands up at once here
	var songs: Array = []         # `$ song` previews

	func begin_sit(id: String) -> void:
		sits.append(id)
		log.append("sit %s" % id)
		var ms: Array = GameState.flags.get("moments", [])
		if not id in ms:
			ms = ms.duplicate()
			ms.append(id)
			GameState.flags["moments"] = ms

	func is_sitting() -> bool:
		return false

	func preview_song(stem: String, _seconds := 10.0) -> void:
		songs.append(stem)
		Chat.heard(stem)

	func set_lamps(group: String, level: float, seconds := 0.0) -> void:
		world_env.set_lamps(group, level, seconds)

	func player_pos() -> Vector3:
		return pos

	func target_of(kind: String, id: String, label: String) -> Dictionary:
		var p = null
		match kind:
			"npc":
				# where the chapter stages them first (Chapters.stage_of), as main.gd places them
				var st := Chapters.stage_of(id)
				var n: Dictionary = markers.get("npcs", {}).get(id, {})
				if st.has("point") and not WorldData.point(String(st.point)).is_empty():
					p = WorldData.point(String(st.point)).pos
				elif not n.is_empty():
					p = load("res://tests/support.gd").v3(n.pos)
				else:
					for d in CastDefs.npc_defs():
						if d.id == id:
							p = d.pos
			"spot":
				var ws: Dictionary = WorldData.spots()
				if ws.has(id):
					p = ws[id].pos
				elif markers.get("spots", {}).has(id):
					p = load("res://tests/support.gd").v3(markers.spots[id].pos)
			"point":
				var pt := WorldData.point(id)
				if not pt.is_empty():
					p = pt.pos
			"anchor":
				if markers.get("anchors", {}).has(id):
					p = load("res://tests/support.gd").v3(markers.anchors[id].pos)
		if p == null:
			return {}
		return {"pos": p, "label": label, "kind": kind, "id": id}

	## Plays a conversation to its end, then what waited for its end (`$ say`, `$ chapter`), as main.gd does.
	func play(steps: Array) -> void:
		dialogue.say(steps)
		story.run_after()
