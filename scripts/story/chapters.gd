class_name Chapters
extends RefCounted
## The chapters (V2-20): data/chapters.json read once, the to-do lists, the main to-do and where it is, the story
## clock, the chapter's music and its triggers. Everything here is a function of GameState.flags and the data, so
## the headless tests (tests/test_quest.gd) walk the same rules the game plays by.
## A to-do: {id, main, kind, text, when, done, target | targets + fallback, label}. The main to-do is the first
## one with main: true whose `when` holds and whose `done` does not; a chapter with none left shows the next
## chapter's (its card has not played yet).

const FILE := "res://data/chapters.json"
const KINDS := ["talk", "go", "fetch", "play", "find"]

static var data := {}
static var _by_n := {}
static var _last_main := ""


static func load_data(force := false) -> void:
	if not data.is_empty() and not force:
		return
	data = {}
	_by_n = {}
	if not FileAccess.file_exists(FILE):
		push_error("Chapters: %s is missing" % FILE)
		return
	var j := JSON.new()
	if j.parse(FileAccess.get_file_as_string(FILE)) != OK or not j.data is Dictionary:
		push_error("Chapters: %s does not parse: %s (line %d)" % [FILE, j.get_error_message(), j.get_error_line()])
		return
	data = j.data
	for c in data.get("chapters", []):
		_by_n[int(c.get("n", 0))] = c


static func all() -> Array:
	load_data()
	return data.get("chapters", [])


static func numbers() -> Array:
	load_data()
	var ns: Array = _by_n.keys()
	ns.sort()
	return ns


static func first() -> int:
	load_data()
	return int(data.get("first", 1))


static func has(n: int) -> bool:
	load_data()
	return _by_n.has(n)


static func get_chapter(n: int) -> Dictionary:
	load_data()
	return _by_n.get(n, {})


static func current() -> int:
	return int(GameState.flags.get("chapter", first()))


static func info() -> Dictionary:
	return get_chapter(current())


## The chapter's start cue has not played through yet: its `started` condition (chapters.json; chapter 3:
## the finder has been read) does not hold. The save is written under the card, before the start cue plays, and
## not again until that scene ends; a quit in between (chapter 3's phone scene with Karim) left a Continue in a
## chapter whose first scene never happened, so main.continue_game plays it again then.
static func start_pending() -> bool:
	var c := info()
	var started := String(c.get("started", ""))
	return started != "" and String(c.get("start_cue", "")) != "" and not Conditions.eval(started)


# ------------------------------------------------------------------ to-dos
static func todos(n: int) -> Array:
	return get_chapter(n).get("todos", [])


static func is_active(t: Dictionary) -> bool:
	return Conditions.eval(String(t.get("when", "true"))) and not Conditions.eval(String(t.get("done", "false")))


## The main to-do now: the current chapter's, or the next chapter's while the card is still to come. {} at the end.
static func main_todo() -> Dictionary:
	var ends := String(info().get("ends_with", ""))
	for n in numbers():
		if n < current():
			continue
		# a later chapter's to-dos only once this one has ended (its card still to come): otherwise chapter 3's opening
		# scene shows chapter 4's "Cristina and Joaquin, 21:00." before it
		if n > current() and ends != "" and not bool(GameState.flags.get(ends, false)):
			break
		for t in todos(n):
			if bool(t.get("main", false)) and is_active(t):
				return t
	return {}


## The optional to-dos showing now (at most two: the rest wait their turn): this chapter's, then the earlier
## chapters' ones marked "carry" (a loose end that stays open, like the promise Mano forgot), while they hold.
static func optional_todos() -> Array:
	var out: Array = []
	var pool: Array = []
	for n in numbers():
		if n < current():
			for t in todos(n):
				if bool(t.get("carry", false)):
					pool.append(t)
	pool = todos(current()) + pool
	for t in pool:
		if not bool(t.get("main", false)) and is_active(t) and not t in out:
			out.append(t)
			if out.size() == 2:
				break
	return out


## Every optional to-do active now, before the cap of two (the walker checks the cap holds by design).
static func active_optional_count() -> int:
	var k := 0
	for n in numbers():
		if n > current():
			continue
		for t in todos(n):
			if not bool(t.get("main", false)) and (n == current() or bool(t.get("carry", false))) and is_active(t):
				k += 1
	return k


## The done to-dos of this chapter, in the order they were done, for the journal (struck through).
static func done_todos() -> Array:
	var ids: Array = GameState.flags.get("todos_done", [])
	var out: Array = []
	for id in ids:
		for n in numbers():
			for t in todos(n):
				if t.get("id", "") == id and not t in out:
					out.append(t)
	return out


## Called when the flags change: once the main to-do moves on, the one it replaces goes into flags.todos_done if
## its `done` holds (only to-dos that were shown get struck through in the journal).
static func track() -> void:
	var id := String(main_todo().get("id", ""))
	if id == _last_main:
		return
	if _last_main != "":
		var prev := find_todo(_last_main)
		var done: Array = GameState.flags.get("todos_done", [])
		if not prev.is_empty() and Conditions.eval(String(prev.get("done", "false"))) and not _last_main in done:
			done.append(_last_main)
			GameState.flags["todos_done"] = done
	_last_main = id


## Forget the last main to-do (a new game, a loaded save).
static func reset_tracking() -> void:
	_last_main = String(main_todo().get("id", ""))


static func find_todo(id: String) -> Dictionary:
	for n in numbers():
		for t in todos(n):
			if String(t.get("id", "")) == id:
				return t
	return {}


static func text_of(t: Dictionary) -> String:
	return DialogueData.format(String(t.get("text", "")))


## The objective strip's text: the main to-do, filled in ("you have 1"), or "".
static func objective_text() -> String:
	var t := main_todo()
	return text_of(t) if not t.is_empty() else ""


## Where the main to-do is, for the waypoint and the map: {pos, label} (game.target_of) or {}.
static func target(game) -> Dictionary:
	var t := main_todo()
	if t.is_empty():
		return {}
	if t.has("targets"):
		var best := {}
		for e in t.targets:
			var unless := String(e.get("unless", ""))
			if unless != "" and Conditions.eval(unless):
				continue
			var r := resolve(String(e.get("ref", "none")), String(e.get("label", t.get("label", ""))), game)
			if r.is_empty():
				continue
			if best.is_empty() or game.player_pos().distance_to(r.pos) < game.player_pos().distance_to(best.pos):
				best = r
		if not best.is_empty():
			return best
		var fb = t.get("fallback", {})
		if fb is Dictionary and not fb.is_empty():
			return resolve(String(fb.get("ref", "none")), String(fb.get("label", t.get("label", ""))), game)
		return {}
	return resolve(String(t.get("target", "none")), String(t.get("label", "")), game)


## "npc:karim" -> game.target_of("npc", "karim", label); point: and anchor: come from world.json and the level.
static func resolve(ref: String, label: String, game) -> Dictionary:
	if ref == "none" or ref == "":
		return {}
	var kind := ref.get_slice(":", 0)
	var id := ref.get_slice(":", 1)
	return game.target_of(kind, id, label)


# ------------------------------------------------------------------ staging (V2-21)
## Where a character is now: a `$ stage` override (flags.stage_over: "hide", "home" or a world.json point id) wins;
## then the chapter's "stage" entry (one entry, or a list whose first entry with a true `when` counts):
## {point, yaw, when, clip, chat, follow, hide}. {} means no staging: the character's own place, and their
## world.json npc_when (a staged_only character is then off stage). {"none": true}: staged, but no entry holds.
static func stage_of(id: String) -> Dictionary:
	var over = GameState.flags.get("stage_over", {})
	if over is Dictionary and over.has(id):
		var w := String(over[id])
		if w == "hide":
			return {"hide": true, "key": "over:hide"}
		if w == "home":
			return {"home": true, "key": "over:home"}
		if w.begins_with("walk:"):
			return {"point": w.substr(5), "walk": true, "key": "over:" + w}
		return {"point": w, "key": "over:" + w}
	var e = info().get("stage", {}).get(id, null)
	if e == null:
		return {}
	var list: Array = e if e is Array else [e]
	for i in list.size():
		var st: Dictionary = list[i]
		if Conditions.eval(String(st.get("when", "true"))):
			var out := st.duplicate()
			out["key"] = "ch%d:%s:%d" % [current(), id, i]
			return out
	return {"none": true, "key": "ch%d:%s:none" % [current(), id]}


## The characters this chapter stages (its "stage" keys) and those a `$ stage` moved.
static func staged_ids() -> Array:
	var out: Array = info().get("stage", {}).keys()
	var over = GameState.flags.get("stage_over", {})
	if over is Dictionary:
		for k in over:
			if not k in out:
				out.append(k)
	return out


## On campus now? `staged_only` characters only where staged (or following Mano); everyone else unless staged
## "hide", by their world.json npc_when otherwise.
static func on_stage(id: String, staged_only: bool) -> bool:
	if id in GameState.flags.get("following", []):
		return true
	var st := stage_of(id)
	if st.get("hide", false):
		return false
	if staged_only:
		return st.has("point") or bool(st.get("follow", false))
	if st.has("point"):
		return true
	var w := WorldData.npc_when(id)
	return w == "" or Conditions.eval(w)


# ------------------------------------------------------------------ clock
static func clock() -> int:
	return int(GameState.flags.get("clock", 1062))


static func clock_text() -> String:
	return Conditions.clock_text(clock())


## Game minutes per real minute of play (the clock moves on slowly between the story's own `$ clock` steps).
static func clock_rate() -> float:
	load_data()
	return float(data.get("clock_rate", 0.0))


## The latest time the clock may tick to in this chapter (it never runs past the next chapter's card).
static func clock_end() -> int:
	var e := String(info().get("clock_end", ""))
	return Conditions.minutes(e) if e != "" else 99999


## The latest time the clock may tick to now: clock_end, or earlier while one of the chapter's `clock_holds`
## ({"while": condition, "until": "HH:MM"}, the first that holds) does. Each hold is the time the story's next
## `$ clock` sets, so walking about never runs the clock past a beat that is pinned to a time (a player who walks
## the coffee errands would otherwise be at 18:52 when the twist sets 18:48).
static func clock_cap() -> int:
	var cap := clock_end()
	for h in info().get("clock_holds", []):
		if h is Dictionary and Conditions.eval(String(h.get("while", "true"))):
			var m := Conditions.minutes(String(h.get("until", "")))
			return mini(cap, m) if m >= 0 else cap
	return cap


# ------------------------------------------------------------------ music
## The track for a preset and a zone: [stem, dB]. "zone:<id>" entries win; a list entry is [[condition, stem], ...].
static func music_for(time: String, zone: String) -> Array:
	load_data()
	var m: Dictionary = data.get("music", {})
	var e = m.get("zone:" + zone, m.get(time, "explore"))
	var stem := "explore"
	if e is String:
		stem = e
	elif e is Array:
		for pair in e:
			if pair is Array and pair.size() == 2 and Conditions.eval(String(pair[0])):
				stem = String(pair[1])
				break
	return [stem, float(data.get("music_db", {}).get(stem, -10.0))]


# ------------------------------------------------------------------ triggers
## The chapter's triggers that should play now: not fired yet (when "once"), `when` true, Mano near the point or
## in the zone, and `after` seconds into the chapter. `main_only` keeps the critical-path ones (the story autotest
## and the walker visit those before the next target).
static func pending_triggers(game, main_only := false, seconds_in := INF) -> Array:
	var out: Array = []
	var fired: Array = GameState.flags.get("triggers_fired", [])
	for tr in info().get("triggers", []):
		if main_only and not bool(tr.get("main", false)):
			continue
		if bool(tr.get("once", true)) and String(tr.get("id", "")) in fired:
			continue
		if not Conditions.eval(String(tr.get("when", "true"))):
			continue
		if seconds_in < float(tr.get("after", 0.0)):
			continue
		if game != null and not _in_reach(tr, game):
			continue
		out.append(tr)
	return out


static func _in_reach(tr: Dictionary, game) -> bool:
	if tr.has("zone") and String(game.zone_id()) != String(tr.zone):
		return false
	if tr.has("near"):
		var r := resolve(String(tr.near), "", game)
		if r.is_empty() or game.player_pos().distance_to(r.pos) > float(tr.get("radius", 5.0)):
			return false
	return true


static func mark_fired(tr: Dictionary) -> void:
	var fired: Array = GameState.flags.get("triggers_fired", [])
	if not String(tr.get("id", "")) in fired:
		fired.append(String(tr.get("id", "")))
	GameState.flags["triggers_fired"] = fired
