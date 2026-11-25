extends RefCounted
## The dialogue and story data validator (V2-19): res://dialogue/*.dlg, data/chapters.json, world.json, flags.json.
## Errors: parse errors, duplicate cues, missing jump/say/minigame/start cues, unknown speakers or expressions,
## undeclared flags, conditions that do not parse, commands or arguments not in StoryCommands.SPEC, a minigame
## with no script or not at the end of its cue, references (npc:, spot:, point:, anchor:) that do not resolve,
## `$ time` outside its chapter's presets, cards over 90 characters, emoji anywhere. Warnings: cards over 80
## characters (line_check measures the real font), mixed indentation, generic slang in new lines.
## Voices and staging: the narrator (`nar`) speaks only stage sounds ("*plink*"; everything else is Mano's `think`); bark
## triggers play think-only cues; staging, the follower, the phone and shots are checked against world.json and
## the cast; staged_only characters are only referred to where their chapter stages them; c1 and c2 have at least
## MIN_CHAPTER_CARDS cards each.
## The phone and the sit-downs: dialogue/chat.json (threads, senders, times in order, at most 160 characters, no emoji, replies with a
## silent option and declared flags, the batches `$ phone flood` names), data/songs.json, the world.json sits
## (seat, cams a and b, cue, song, journal line) and finder places, `$ phone` arguments per action, `$ sit` and
## `$ song`, the staging keys sit and leave, a trigger's `bring`, and at least 70 cards in c3.
## The finale: `$ photo`, `$ airpods`, `$ score`, `$ caption`; chapters 0, 4 and 5 (an `opening` of wake or cold_open, a
## `group_shot` in world.json shots); data/kebab.json (every friend's order on the menus, the cook's misreadings);
## the seven "Want one?" offers of chapter 5 (one cue per friend, giving them the AirPod); at least 70 cards in c4
## and 50 in c5 (a shorter chapter by design: docs/DESIGN.md §3.4).
## Collectibles and campus life: the twelve ducks (3/3/2/2/2 by chapter, each with a place and a whisperer's hint, two night ones that
## glow), Ishita's ten photo spots (and every tour stop on one), the overheard loops (8 to 12, two staged NPCs each,
## 3 to 6 lines between just those two, lines only), the look-ats (kinds, readables with an insert, at least 80 in
## all, reported per room, about 25 with a night variant), the side stories' cues and data/journal.json.
## Writes the [slot] lines (waiting for a friend's words) to tools/out/slots.txt.

const Support := preload("res://tests/support.gd")
const EXPRESSIONS := ["smile", "grin", "shock", "annoyed", "sad", "smirk", "tired", "neutral"]
const EXTRA_SPEAKERS := ["mano", "think", "nar", "crowd"]
const MAX_CHARS := 90
const WARN_CHARS := 80
## Lines avoid generic slang; the lines carried over from v1 are exempt (their voices depend on them).
const SLANG := ["bro", "classic mano", "lol", "lmao", "bestie", "fam", "no cap", "slay", "vibes"]
const SLOTS_OUT := "res://tools/out/slots.txt"
const SLOTS_CHAT_OUT := "res://tools/out/slots_chat.txt"
const MIN_CHAPTER_CARDS := {"c1": 70, "c2": 70, "c3": 70, "c4": 70, "c5": 50}   # the fewest cards a chapter may have
const FRIENDS := ["toma", "anisha", "ian", "silvia", "ishita", "cristina", "joaquin"]   # the seven Mano can offer the AirPod to
const CHAT_MAX := 160

var t
var _markers := {}
var _cast := {}
var _v1_texts := {}


func run(report) -> void:
	t = report
	DialogueData.load_all(true)
	Chapters.load_data(true)
	WorldData.load_data(true)
	var m = Support.read_json(Support.MARKERS)
	_markers = m if m is Dictionary else {}
	t.ok(not _markers.is_empty(), "tests/fixtures/markers.json loads (scenes/dev/marker_list.tscn writes it)")
	for d in CastDefs.npc_defs():
		_cast[d.id] = d
	var v1 = Support.read_json("res://tests/fixtures/v1_cards.json")
	if v1 is Array:
		for c in v1:
			_v1_texts[String(c.text)] = true
	for e in DialogueData.errors:
		t.fail("dialogue: " + String(e))
	for w in DialogueData.warnings:
		t.warn(String(w))
	t.ok(DialogueData.cues.size() > 0, "the dialogue folder has cues")
	_check_lines()
	_check_conditions()
	_check_commands()
	_check_jumps()
	_check_tails()
	_check_chapters()
	_check_world()
	_check_chat()
	_check_sits()
	_check_kebab()
	_check_offers()
	_check_stage5()
	_report_counts()


# ------------------------------------------------------------------ lines
func _check_lines() -> void:
	var slots: Array = []
	for pair in DialogueData.nodes("line"):
		var cue: String = pair[0]
		var n: Dictionary = pair[1]
		var who := String(n.who)
		t.ok(who in EXTRA_SPEAKERS or _cast.has(who), "%s: speaker '%s' is in CastDefs (or mano, think, nar, crowd)" % [n.src, who])
		if String(n.expr) != "":
			t.ok(String(n.expr) in EXPRESSIONS, "%s: expression [#%s] is one of %s" % [n.src, n.expr, EXPRESSIONS])
		var text := String(n.text)
		if who == "nar":
			t.ok(DialogueData.is_stage_sound(text), "%s: the narrator speaks only stage sounds (*...*); a thought is `think`: %s" % [n.src, text])
		t.ok(text.length() <= MAX_CHARS, "%s: card under %d characters (%d)" % [n.src, MAX_CHARS, text.length()])
		if text.length() > WARN_CHARS:
			t.warn("%s: %d characters (line_check decides): %s" % [n.src, text.length(), text])
		t.ok(not _has_emoji(text), "%s: no emoji: %s" % [n.src, text])
		if not _v1_texts.has(text):
			var low := " " + text.to_lower() + " "
			for w in SLANG:
				var re := RegEx.create_from_string("[^a-z]" + w + "[^a-z]")
				if re.search(low):
					t.warn("%s: generic slang '%s' in a new line: %s" % [n.src, w, text])
		if bool(n.slot):
			slots.append("%s  %s  %s: %s" % [cue, n.src, who, text])
		for r in n.ask:
			t.ok(not _has_emoji(String(r.label)), "%s: no emoji in the response '%s'" % [r.src, r.label])
			if bool(r.slot):
				slots.append("%s  %s  (response) %s" % [cue, r.src, r.label])
	var f := FileAccess.open(ProjectSettings.globalize_path(SLOTS_OUT), FileAccess.WRITE)
	if f:
		f.store_string("# [slot] lines: written in a friend's own voice (tests/validate_dialogue.gd)\n" + "\n".join(slots) + "\n")
		f.close()
	t.info("%d [slot] lines -> %s" % [slots.size(), SLOTS_OUT])


static func _has_emoji(s: String) -> bool:
	for i in s.length():
		var c := s.unicode_at(i)
		if (c >= 0x1F000 and c <= 0x1FAFF) or (c >= 0x2600 and c <= 0x27BF) or c == 0xFE0F or c == 0x200D \
				or (c >= 0x1F1E6 and c <= 0x1F1FF) or (c >= 0x2B00 and c <= 0x2BFF):
			return true
	return false


# ------------------------------------------------------------------ conditions and flags
func _cond(expr: String, where: String) -> void:
	if expr.strip_edges() == "":
		return
	var err := Conditions.error_of(expr)
	t.ok(err == "", "%s: condition '%s' parses (%s)" % [where, expr, err])
	for id in Conditions.identifiers(expr):
		t.ok(GameState.is_declared(String(id)), "%s: flag '%s' (in '%s') is declared in data/flags.json" % [where, id, expr])


func _check_conditions() -> void:
	for pair in DialogueData.nodes("branch"):
		_cond(String(pair[1].cond), String(pair[1].src))
	for pair in DialogueData.nodes("line"):
		_cond(String(pair[1].cond), String(pair[1].src))
	for pair in DialogueData.nodes("response"):
		_cond(String(pair[1].cond), String(pair[1].src))
	for pair in DialogueData.nodes("line"):
		for key in _interp_keys(String(pair[1].text)):
			if key.begins_with("word."):
				t.ok(WorldData.words.has(key.substr(5)), "%s: {{%s}} is in data/words.json" % [pair[1].src, key])
			elif key.begins_with("song."):
				t.ok(GameState.is_declared(key.substr(5)), "%s: {{%s}} names a declared flag (a data/songs.json stem)" % [pair[1].src, key])
			else:
				t.ok(GameState.is_declared(key), "%s: {{%s}} is a declared flag" % [pair[1].src, key])


static func _interp_keys(text: String) -> Array:
	var out: Array = []
	var re := RegEx.create_from_string("\\{\\{\\s*([a-z0-9_.]+)\\s*\\}\\}")
	for m in re.search_all(text):
		out.append(m.get_string(1))
	return out


# ------------------------------------------------------------------ commands
func _check_commands() -> void:
	for pair in DialogueData.nodes("cmd"):
		var cue: String = pair[0]
		var n: Dictionary = pair[1]
		var name := String(n.name)
		var where := "%s ($ %s)" % [n.src, n.raw]
		if not t.ok(StoryCommands.SPEC.has(name), "%s: '%s' is a command (StoryCommands.SPEC)" % [where, name]):
			continue
		t.ok(StoryCommands.is_built(name), "%s: '%s' is built (stage %d)" % [where, name, StoryCommands.SPEC[name].stage])
		var spec: Dictionary = StoryCommands.SPEC[name]
		var args: Array = n.args
		var specs: Array = spec.args
		var required := 0
		for a in specs:
			required += 1 if a[2] else 0
		if name == "set" and args.is_empty():
			t.ok(not n.kw.is_empty(), "%s: set needs a flag" % where)
			for k in n.kw:
				_check_flag_value(String(k), n.kw[k], where)
			continue
		t.ok(args.size() >= required and args.size() <= specs.size(), "%s: %d to %d arguments (got %d)" % [where, required, specs.size(), args.size()])
		for i in mini(args.size(), specs.size()):
			_check_arg(String(specs[i][1]), args[i], where, cue)
		var allowed: Array = spec.kw
		for k in n.kw:
			t.ok(k in allowed or "*opt" in allowed, "%s: key '%s' is allowed (%s)" % [where, k, allowed])
		if name == "set" and args.size() >= 1:
			_check_flag_value(String(args[0]), args[1] if args.size() > 1 else true, where)
		if name == "add" and args.size() >= 1:
			var d = GameState.flag_default(String(args[0]))
			t.ok(d is int or d is float, "%s: '%s' is a number flag" % [where, args[0]])
		if name == "minigame":
			for k in ["win", "lose"]:
				if n.kw.has(k):
					t.ok(DialogueData.cues.has(String(n.kw[k])), "%s: %s cue '%s' exists" % [where, k, n.kw[k]])
			if n.kw.has("with"):
				t.ok(_cast.has(String(n.kw.with)), "%s: with=%s is in CastDefs" % [where, n.kw.with])
			for k in ["sit_at", "stand_at"]:
				if n.kw.has(k):
					t.ok(_markers.get("anchors", {}).has(String(n.kw[k])), "%s: %s=%s is an ANCHOR_ in the level" % [where, k, n.kw[k]])
		if name == "say" and n.kw.has("with"):
			t.ok(_cast.has(String(n.kw.with)), "%s: with=%s is in CastDefs" % [where, n.kw.with])
		if name == "time":
			_check_time_in_chapter(cue, String(args[0]) if not args.is_empty() else "", where)
		if name == "phone" and not args.is_empty():
			_check_phone(args, where)


func _check_flag_value(flag: String, value, where: String) -> void:
	if not t.ok(GameState.is_declared(flag), "%s: flag '%s' is declared in data/flags.json" % [where, flag]):
		return
	var d = GameState.flag_default(flag)
	var same := typeof(d) == typeof(value) or ((d is int or d is float) and (value is int or value is float))
	t.ok(same, "%s: '%s' takes a %s like its default (got %s)" % [where, flag, type_string(typeof(d)), type_string(typeof(value))])


func _check_arg(kind: String, v, where: String, _cue: String) -> void:
	match kind:
		"flag":
			t.ok(GameState.is_declared(String(v)), "%s: flag '%s' is declared" % [where, v])
		"number":
			t.ok(v is int or v is float, "%s: '%s' is a number" % [where, v])
		"hhmm":
			t.ok(Conditions.minutes(String(v)) >= 0, "%s: '%s' is HH:MM" % [where, v])
		"cue":
			t.ok(DialogueData.cues.has(String(v)), "%s: cue '%s' exists" % [where, v])
		"minigame":
			t.ok(ResourceLoader.exists("res://scripts/minigames/%s.gd" % v), "%s: minigame '%s' has a script" % [where, v])
		"npc":
			t.ok(_cast.has(String(v)), "%s: '%s' is in CastDefs" % [where, v])
		"preset":
			t.ok(WorldEnv.TIMES.has(String(v)), "%s: '%s' is a WorldEnv.TIMES preset" % [where, v])
		"doodle":
			t.ok(String(v) in Doodles.IDS, "%s: doodle '%s' is in Doodles.IDS" % [where, v])
		"hint":
			t.ok(HUD.HINTS.has(String(v)), "%s: hint '%s' is in HUD.HINTS" % [where, v])
		"stem":
			var found := false
			for ext in ["ogg", "wav", "mp3"]:
				for p in ["res://assets/audio/sfx/%s.%s" % [v, ext], "res://assets/audio/sfx/%s_1.%s" % [v, ext], "res://assets/audio/music/%s.%s" % [v, ext]]:
					found = found or ResourceLoader.exists(p)
			t.ok(found, "%s: sound '%s' is on disk" % [where, v])
		"text":
			t.ok(not _has_emoji(String(v)), "%s: no emoji" % where)
		"who":
			t.ok(String(v) == "mano" or _cast.has(String(v)), "%s: '%s' is mano or in CastDefs" % [where, v])
		"point":
			t.ok(WorldData.section("points").has(String(v)), "%s: point '%s' is in data/world.json" % [where, v])
		"where":
			t.ok(String(v) in ["hide", "home"] or WorldData.section("points").has(String(v)), "%s: '%s' is hide, home or a world.json point" % [where, v])
		"phone":
			t.ok(String(v) in StoryCommands.PHONE_ACTIONS, "%s: phone action '%s' is one of %s" % [where, v, StoryCommands.PHONE_ACTIONS])
		"phone_arg":
			pass   # checked with its action (_check_phone)
		"sit":
			t.ok(WorldData.section("sits").has(String(v)), "%s: sit '%s' is in data/world.json sits" % [where, v])
		"song":
			t.ok(Chat.song_known(String(v)) and ResourceLoader.exists("res://assets/audio/music/%s.ogg" % v), "%s: song '%s' is in data/songs.json and on disk" % [where, v])
		"shot":
			t.ok(String(v) == "clear" or WorldData.section("shots").has(String(v)), "%s: shot '%s' is clear or in world.json shots" % [where, v])
		"photo":
			t.ok(String(v) in ["group", "film"], "%s: photo '%s' is group or film" % [where, v])
		"airpods":
			t.ok(String(v) in ["case", "ear"], "%s: airpods '%s' is case or ear" % [where, v])
		"score":
			var st := String(v)
			if st.begins_with("@"):
				t.ok(GameState.is_declared(st.substr(1)) and GameState.flag_default(st.substr(1)) is String, "%s: score '%s' names a declared string flag" % [where, v])
			else:
				t.ok(Chat.song_known(st) and ResourceLoader.exists("res://assets/audio/music/%s.ogg" % st), "%s: score '%s' is a song on disk" % [where, v])


## `$ phone <action> [arg] ["text"]`: what each action takes.
func _check_phone(args: Array, where: String) -> void:
	var action := String(args[0])
	var arg := String(args[1]) if args.size() > 1 else ""
	match action:
		"preview":
			t.ok(args.size() == 3 and _cast.has(arg), "%s: phone preview takes a cast id and \"text\"" % where)
		"flood":
			t.ok(arg in Chat.batches(), "%s: phone flood names a dialogue/chat.json batch (%s)" % [where, Chat.batches()])
		"open":
			t.ok(arg in Phone.APPS or Chat.threads().has(arg), "%s: phone open names an app %s or a chat thread" % [where, Phone.APPS])
		"finder":
			t.ok(WorldData.section("finder_places").has(arg) and args.size() == 3 and Conditions.minutes(String(args[2])) >= 0,
				"%s: phone finder takes a world.json finder_places id and \"HH:MM\"" % where)
		_:
			t.ok(args.size() == 1, "%s: phone %s takes nothing more" % [where, action])


func _check_time_in_chapter(cue: String, preset: String, where: String) -> void:
	var m := RegEx.create_from_string("^c(\\d+)\\.").search(cue)
	if not t.ok(m != null, "%s: `$ time` only inside a chapter cue (c<n>.*)" % where):
		return
	var times: Array = Chapters.get_chapter(int(m.get_string(1))).get("times", [])
	t.ok(preset in times, "%s: '%s' is in chapter %s's times %s" % [where, preset, m.get_string(1), times])


# ------------------------------------------------------------------ jumps and tails
func _check_jumps() -> void:
	for pair in DialogueData.nodes("jump"):
		var n: Dictionary = pair[1]
		if String(n.mode) != "end":
			t.ok(DialogueData.cues.has(String(n.target)), "%s: jump target '%s' exists" % [n.src, n.target])


## A minigame ends its cue: nothing may follow it in its block or in any block around it.
func _check_tails() -> void:
	for id in DialogueData.cues:
		_tail_walk(DialogueData.cues[id].body, true, id)


func _tail_walk(body: Array, tail: bool, cue: String) -> void:
	for i in body.size():
		var n: Dictionary = body[i]
		var last := tail and i == body.size() - 1
		match String(n.t):
			"cmd":
				if String(n.name) == "minigame":
					t.ok(last, "%s: a minigame must end its cue (nothing after it plays)" % n.src)
			"line":
				for r in n.ask:
					_tail_walk(r.body, last, cue)
			"if":
				for b in n.branches:
					_tail_walk(b.body, last, cue)
				if n["else"] != null:
					_tail_walk(n["else"], last, cue)


# ------------------------------------------------------------------ chapters.json
func _resolves(ref: String) -> bool:
	if ref == "none" or ref == "":
		return true
	var kind := ref.get_slice(":", 0)
	var id := ref.get_slice(":", 1)
	match kind:
		"npc":
			return _cast.has(id)
		"spot":
			return _markers.get("spots", {}).has(id) or WorldData.section("spots").has(id)
		"point":
			return WorldData.section("points").has(id)
		"anchor":
			return _markers.get("anchors", {}).has(id)
	return false


func _check_chapters() -> void:
	var chs := Chapters.all()
	t.ok(not chs.is_empty(), "data/chapters.json has chapters")
	t.ok(Chapters.has(Chapters.first()), "the first chapter (%d) exists" % Chapters.first())
	t.ok(DialogueData.cues.has("bridge.end"), "bridge.end exists (a chapter not built yet plays it)")
	var todo_ids := {}
	for c in chs:
		var n := int(c.get("n", 0))
		var w := "chapters.json chapter %d" % n
		var card: Dictionary = c.get("card", {})
		t.ok(card.has("time") and card.has("place") and card.has("chapter"), "%s: a card with time, place and chapter" % w)
		t.ok(Conditions.minutes(String(c.get("clock", ""))) >= 0, "%s: clock '%s' is HH:MM" % [w, c.get("clock", "")])
		if c.has("clock_end"):
			t.ok(Conditions.minutes(String(c.clock_end)) > Conditions.minutes(String(c.get("clock", "0:00"))), "%s: clock_end after clock" % w)
		# clock holds: the walk never ticks the clock past the time a pinned beat sets (Chapters.clock_cap)
		var last_hold := Conditions.minutes(String(c.get("clock", "0:00")))
		for h in c.get("clock_holds", []):
			if not t.ok(h is Dictionary and h.has("while") and h.has("until"), "%s: a clock hold is {while, until}" % w):
				continue
			_cond(String(h.while), "%s clock hold" % w)
			var m := Conditions.minutes(String(h.until))
			t.ok(m > last_hold and (not c.has("clock_end") or m <= Conditions.minutes(String(c.clock_end))),
				"%s: clock hold %s is after the clock and the hold before it, not after clock_end" % [w, h.until])
			last_hold = m
		var times: Array = c.get("times", [])
		for p in times:
			t.ok(WorldEnv.TIMES.has(String(p)), "%s: preset '%s' exists" % [w, p])
		t.ok(String(c.get("time", "")) in times, "%s: its starting time is one of its times" % w)
		var cue := String(c.get("start_cue", ""))
		if cue != "":
			t.ok(DialogueData.cues.has(cue), "%s: start_cue '%s' exists" % [w, cue])
		if c.has("opening"):
			t.ok(String(c.opening) in ["wake", "cold_open"], "%s: opening '%s' is wake or cold_open" % [w, c.opening])
		if c.has("group_shot"):
			t.ok(WorldData.section("shots").has(String(c.group_shot)), "%s: group_shot '%s' is in world.json shots" % [w, c.group_shot])
		if c.has("started"):
			# the condition that holds once the start cue has played (a Continue before that plays it again)
			t.ok(cue != "", "%s: `started` goes with a start_cue" % w)
			_cond(String(c.started), "%s started" % w)
		if c.has("start_with") and String(c.start_with) != "":
			t.ok(_cast.has(String(c.start_with)), "%s: start_with '%s' is in CastDefs" % [w, c.start_with])
		if c.has("start_at"):
			t.ok(_resolves(String(c.start_at)), "%s: start_at '%s' resolves" % [w, c.start_at])
		if c.has("card_at"):
			t.ok(_resolves(String(c.card_at)) and String(c.card_at).begins_with("point:"), "%s: card_at '%s' is a world.json point" % [w, c.card_at])
		for k in c.get("start_flags", {}):
			t.ok(GameState.is_declared(String(k)), "%s: start flag '%s' is declared" % [w, k])
		if c.has("ends_with"):
			t.ok(GameState.is_declared(String(c.ends_with)), "%s: ends_with '%s' is declared" % [w, c.ends_with])
		for id in c.get("stage", {}):
			t.ok(_cast.has(String(id)), "%s: staged '%s' is in CastDefs" % [w, id])
			var entries = c.stage[id]
			for st in (entries if entries is Array else [entries]):
				if not t.ok(st is Dictionary, "%s: %s's staging entries are objects" % [w, id]):
					continue
				if st.has("point"):
					t.ok(_resolves("point:" + String(st.point)), "%s: %s's point '%s' is in world.json" % [w, id, st.point])
				for k in st:
					t.ok(k in ["point", "yaw", "when", "clip", "chat", "follow", "hide", "walk", "sit", "leave", "awake"], "%s: %s's staging key '%s' is known" % [w, id, k])
				_cond(String(st.get("when", "")), "%s stage %s" % [w, id])
		var trig_ids := {}
		for tr in c.get("triggers", []):
			var tw := "%s trigger %s" % [w, tr.get("id", "?")]
			t.ok(not trig_ids.has(String(tr.get("id", ""))), "%s: a unique id" % tw)
			trig_ids[String(tr.get("id", ""))] = true
			t.ok(DialogueData.cues.has(String(tr.get("cue", ""))), "%s: cue '%s' exists" % [tw, tr.get("cue", "")])
			_cond(String(tr.get("when", "")), tw)
			if tr.has("near"):
				t.ok(_resolves(String(tr.near)), "%s: near '%s' resolves" % [tw, tr.near])
				_check_staged_ref(c, String(tr.near), tw)
			if tr.has("zone"):
				t.ok(_markers.get("zones", {}).has(String(tr.zone)), "%s: zone '%s' is a ZONE_ in the level" % [tw, tr.zone])
			if tr.has("with"):
				t.ok(_cast.has(String(tr.with)), "%s: with=%s is in CastDefs" % [tw, tr.with])
				_check_staged_ref(c, "npc:" + String(tr.with), tw)
			if bool(tr.get("bark", false)):
				t.ok(DialogueData.is_think_only(String(tr.get("cue", ""))), "%s: a bark trigger plays a think-only cue (%s)" % [tw, tr.get("cue", "")])
				t.ok(not bool(tr.get("main", false)), "%s: a bark trigger is not on the critical path" % tw)
			if tr.has("place"):
				# a staged scene: everyone to a world.json point before the first shot (main.play_trigger)
				t.ok(tr.place is Dictionary and not tr.place.is_empty(), "%s: place is {who: point}" % tw)
				if tr.place is Dictionary:
					for who in tr.place:
						t.ok(String(who) == "mano" or _cast.has(String(who)), "%s: place '%s' is mano or in CastDefs" % [tw, who])
						t.ok(_resolves("point:" + String(tr.place[who])), "%s: %s's mark '%s' is in world.json" % [tw, who, tr.place[who]])
						if String(who) != "mano":
							_check_staged_ref(c, "npc:" + String(who), tw)
					if tr.has("with"):
						t.ok(tr.place.has("mano") and tr.place.has(String(tr.with)), "%s: a placed conversation sets both Mano's and %s's marks" % [tw, tr.with])
			if tr.has("bring"):
				# the follower joins Mano where it fires (main._bring): a cast id, staged in this chapter, the conversation's
				t.ok(_cast.has(String(tr.bring)), "%s: bring '%s' is in CastDefs" % [tw, tr.bring])
				t.ok(String(tr.get("with", "")) == String(tr.bring), "%s: bring is the one the conversation is with" % tw)
				_check_staged_ref(c, "npc:" + String(tr.bring), tw)
			t.ok(tr.has("near") or tr.has("zone"), "%s: fires somewhere (near or zone)" % tw)
		for td in c.get("todos", []):
			var id := String(td.get("id", ""))
			var tw := "%s to-do %s" % [w, id]
			t.ok(id != "" and not todo_ids.has(id), "%s: a unique id" % tw)
			todo_ids[id] = true
			t.ok(String(td.get("kind", "")) in Chapters.KINDS, "%s: kind '%s' is one of %s" % [tw, td.get("kind", ""), Chapters.KINDS])
			t.ok(String(td.get("text", "")) != "", "%s: has text" % tw)
			t.ok(not _has_emoji(String(td.get("text", ""))), "%s: no emoji" % tw)
			_cond(String(td.get("when", "")), tw)
			_cond(String(td.get("done", "")), tw)
			for key in _interp_keys(String(td.get("text", ""))):
				t.ok(key.begins_with("word.") or GameState.is_declared(key), "%s: {{%s}} is declared" % [tw, key])
			if td.has("targets"):
				for e in td.targets:
					t.ok(_resolves(String(e.get("ref", ""))), "%s: target '%s' resolves" % [tw, e.get("ref", "")])
					_cond(String(e.get("unless", "")), tw)
				if td.has("fallback"):
					t.ok(_resolves(String(td.fallback.get("ref", ""))), "%s: fallback '%s' resolves" % [tw, td.fallback.get("ref", "")])
			else:
				t.ok(_resolves(String(td.get("target", "none"))), "%s: target '%s' resolves" % [tw, td.get("target", "none")])
				_check_staged_ref(c, String(td.get("target", "none")), tw)
	for key in Chapters.data.get("music", {}):
		var e = Chapters.data.music[key]
		var stems: Array = []
		if e is String:
			stems.append(e)
		elif e is Array:
			for pair in e:
				_cond(String(pair[0]), "chapters.json music %s" % key)
				stems.append(String(pair[1]))
		for st in stems:
			t.ok(ResourceLoader.exists("res://assets/audio/music/%s.ogg" % st) or ResourceLoader.exists("res://assets/audio/music/%s.mp3" % st),
				"chapters.json music %s: track '%s' is on disk" % [key, st])


## A staged_only character (the new friends) is only there where the chapter stages them.
func _check_staged_ref(c: Dictionary, ref: String, where: String) -> void:
	if not ref.begins_with("npc:"):
		return
	var id := ref.substr(4)
	if _cast.has(id) and bool(_cast[id].get("staged_only", false)):
		t.ok(c.get("stage", {}).has(id), "%s: %s is staged_only, and chapter %s stages them" % [where, id, c.get("n", "?")])


# ------------------------------------------------------------------ world.json
func _check_world() -> void:
	for id in WorldData.section("spot_when"):
		t.ok(_markers.get("spots", {}).has(id) or WorldData.section("spots").has(id), "world.json spot_when: spot '%s' exists" % id)
		_cond(String(WorldData.section("spot_when")[id]), "world.json spot_when %s" % id)
	for id in WorldData.section("npc_when"):
		t.ok(_cast.has(String(id)), "world.json npc_when: '%s' is in CastDefs" % id)
		_cond(String(WorldData.section("npc_when")[id]), "world.json npc_when %s" % id)
	for id in WorldData.section("spots"):
		var sp: Dictionary = WorldData.section("spots")[id]
		_cond(String(sp.get("when", "")), "world.json spot %s" % id)
		t.ok(DialogueData.cues.has("use." + String(id)), "world.json spot '%s' has a use.%s cue" % [id, id])
		if sp.get("note") is Dictionary:
			t.ok(String(sp.note.get("text", "")) != "" and not _has_emoji(String(sp.note.text)), "world.json spot %s: its note has text, no emoji" % id)
	for id in WorldData.section("points"):
		var p = WorldData.section("points")[id]
		t.ok(p is Dictionary and p.get("pos") is Array and p.pos.size() == 3, "world.json point %s has pos [x, y, z]" % id)
		if p is Dictionary and p.has("via"):
			for v in p.via:
				t.ok(v is Array and v.size() == 3, "world.json point %s: every via is [x, y, z]" % id)
	for id in WorldData.section("shots"):
		var sh = WorldData.section("shots")[id]
		if sh is Dictionary and String(sh.get("on", "")) != "":
			# a shot relative to Mano (the cold open's close shots), as a sit camera
			t.ok(String(sh.on) == "mano" and sh.get("rel") is Array and sh.rel.size() == 3, "world.json shot %s: on mano, rel [deg, metres, height]" % id)
		else:
			t.ok(sh is Dictionary and sh.get("from") is Array and sh.get("look") is Array, "world.json shot %s has from and look" % id)
	for id in WorldData.section("lights"):
		var l = WorldData.section("lights")[id]
		t.ok(l is Dictionary and l.get("pos") is Array and l.pos.size() == 3, "world.json light %s has pos" % id)
		if l is Dictionary:
			_cond(String(l.get("when", "")), "world.json light %s" % id)
			for p in l.get("times", []):
				t.ok(WorldEnv.TIMES.has(String(p)), "world.json light %s: preset '%s' exists" % [id, p])
	# camera-only boxes for level meshes with no collider (the Under's door leaf)
	for id in WorldData.section("cam_occluders"):
		var o = WorldData.section("cam_occluders")[id]
		t.ok(o is Dictionary and o.get("pos") is Array and o.pos.size() == 3 and o.get("size") is Array and o.size.size() == 3,
			"world.json cam_occluder %s has pos and size [x, y, z]" % id)
		if o is Dictionary and o.get("size") is Array and o.size.size() == 3:
			t.ok(float(o.size[0]) > 0.0 and float(o.size[1]) > 0.0 and float(o.size[2]) > 0.0 and float(o.size[1]) <= 6.0,
				"world.json cam_occluder %s: a positive size, no taller than a storey and a half" % id)
	for sec in ["zone_names", "zone_titles", "zone_banners"]:
		for id in WorldData.section(sec):
			t.ok(_markers.get("zones", {}).has(id), "world.json %s: zone '%s' is a ZONE_ in the level" % [sec, id])
	# every spot and npc the story talks about can be reached
	for id in _markers.get("spots", {}):
		t.ok(DialogueData.cues.has("use." + String(id)), "level spot '%s' has a use.%s cue" % [id, id])


# ------------------------------------------------------------------ the phone's messages
func _check_chat() -> void:
	Chat.load_data(true)
	t.ok(not Chat.data.is_empty(), "dialogue/chat.json loads")
	var batches := Chat.batches()
	t.ok(not batches.is_empty(), "chat.json has batches")
	var threads := Chat.threads()
	var last_at := {}
	var per_batch := {}
	for i in Chat.messages().size():
		var m: Dictionary = Chat.messages()[i]
		var w := "chat.json message %d (%s)" % [i, String(m.get("text", "")).left(30)]
		t.ok(threads.has(String(m.get("thread", ""))), "%s: thread '%s' exists" % [w, m.get("thread", "")])
		t.ok(String(m.get("batch", "")) in batches, "%s: batch '%s' is one of %s" % [w, m.get("batch", ""), batches])
		per_batch[String(m.get("batch", ""))] = per_batch.get(String(m.get("batch", "")), 0) + 1
		if m.has("from_name"):
			t.ok(String(m.from_name) != "" and not m.has("from"), "%s: a classmate has from_name only" % w)
		else:
			t.ok(_cast.has(String(m.get("from", ""))) or String(m.get("from", "")) == "mano", "%s: from '%s' is in CastDefs" % [w, m.get("from", "")])
		var at := Conditions.minutes(String(m.get("at", "")))
		t.ok(at >= 0, "%s: at '%s' is HH:MM" % [w, m.get("at", "")])
		var th := String(m.get("thread", ""))
		t.ok(at >= int(last_at.get(th, 0)), "%s: times in order in thread %s" % [w, th])
		last_at[th] = at
		var text := String(m.get("text", ""))
		t.ok(text != "" or m.has("photo"), "%s: has text" % w)
		t.ok(text.length() <= CHAT_MAX, "%s: at most %d characters (%d)" % [w, CHAT_MAX, text.length()])
		t.ok(not _has_emoji(text), "%s: no emoji" % w)
		for key in _interp_keys(text):
			t.ok(key.begins_with("word.") and WorldData.words.has(key.substr(5)), "%s: {{%s}} is in data/words.json" % [w, key])
	for tid in threads:
		var th: Dictionary = threads[tid]
		t.ok(not _has_emoji(String(th.get("title", ""))), "chat.json thread %s: no emoji in its title" % tid)
		if th.has("with"):
			t.ok(_cast.has(String(th.with)), "chat.json thread %s: with '%s' is in CastDefs" % [tid, th.with])
		for mem in th.get("members", []):
			t.ok(_cast.has(String(mem)) or String(mem) == "mano", "chat.json thread %s: member '%s' is in CastDefs" % [tid, mem])
	var flood := int(per_batch.get("flood", 0))
	t.ok(flood >= 35 and flood <= 50, "chat.json: the flood is about 40 messages (%d)" % flood)
	for r in Chat.replies():
		var w := "chat.json reply %s" % r.get("id", "?")
		t.ok(threads.has(String(r.get("thread", ""))), "%s: thread exists" % w)
		t.ok(String(r.get("after", "")) in batches, "%s: after '%s' is a batch" % [w, r.get("after", "")])
		t.ok(GameState.is_declared(String(r.get("flag", ""))) and GameState.flag_default(String(r.get("flag", ""))) is String,
			"%s: flag '%s' is a declared string flag" % [w, r.get("flag", "")])
		var silent := false
		for o in r.get("options", []):
			var tone := String(o.get("tone", ""))
			silent = silent or tone == "silent"
			if tone != "silent":
				t.ok(String(o.get("text", "")).length() <= CHAT_MAX and not _has_emoji(String(o.get("text", ""))), "%s: option %s at most %d characters, no emoji" % [w, tone, CHAT_MAX])
			for re in o.get("reactions", []):
				t.ok(_cast.has(String(re.get("from", ""))), "%s: reaction from '%s' is in CastDefs" % [w, re.get("from", "")])
				t.ok(String(re.get("text", "")).length() <= CHAT_MAX and not _has_emoji(String(re.get("text", ""))), "%s: reaction at most %d characters, no emoji" % [w, CHAT_MAX])
		t.ok(silent, "%s: saying nothing is an option" % w)
	# every batch is delivered by some `$ phone flood` (the preview batch rides along with the flood)
	var flooded := {}
	for pair in DialogueData.nodes("cmd"):
		var n: Dictionary = pair[1]
		if String(n.name) == "phone" and n.args.size() > 1 and String(n.args[0]) == "flood":
			flooded[String(n.args[1])] = true
	for b in batches:
		var idx := batches.find(b)
		var later := false
		for k in range(idx, batches.size()):
			later = later or flooded.has(String(batches[k]))
		t.ok(later, "chat.json batch '%s' is delivered by a `$ phone flood` (of it or a later batch)" % b)
	for stem in Chat.songs.get("songs", {}):
		t.ok(ResourceLoader.exists("res://assets/audio/music/%s.ogg" % stem), "data/songs.json: '%s' is on disk" % stem)
	for stem in Chat.songs.get("playlist", []):
		t.ok(Chat.song_known(String(stem)), "data/songs.json playlist: '%s' is a song" % stem)
	t.info("chat: %d messages (%s), %d threads, %d replies" % [Chat.messages().size(), per_batch, threads.size(), Chat.replies().size()])
	# the friends' messages marked `slot` (written in that friend's own voice), next to the [slot] lines
	var slots: Array = []
	for m in Chat.messages():
		if bool(m.get("slot", false)):
			slots.append("%s  %s %s  %s: %s" % [m.get("batch", ""), m.get("thread", ""), m.get("at", ""), m.get("from", m.get("from_name", "")), m.get("text", "")])
	var f := FileAccess.open(ProjectSettings.globalize_path(SLOTS_CHAT_OUT), FileAccess.WRITE)
	if f:
		f.store_string("# chat messages marked slot: written in a friend's own voice (dialogue/chat.json)\n" + "\n".join(slots) + "\n")
		f.close()
	t.info("%d chat messages marked slot -> %s" % [slots.size(), SLOTS_CHAT_OUT])


# ------------------------------------------------------------------ sit-downs
func _check_sits() -> void:
	var sec := WorldData.section("sits")
	t.ok(sec.size() == 6, "world.json has the six sit-downs of DESIGN_V2 §4.1 (%d)" % sec.size())
	for id in sec:
		var e: Dictionary = sec[id]
		var w := "world.json sit %s" % id
		var s := WorldData.sit(String(id))
		t.ok(not s.is_empty(), "%s: has pos" % w)
		t.ok(e.get("cams", {}).has("a") and e.get("cams", {}).has("b"), "%s: has cams a and b" % w)
		t.ok(DialogueData.cues.has(String(s.get("cue", ""))) and DialogueData.is_think_only(String(s.get("cue", ""))), "%s: its cue %s is Mano's thought only" % [w, s.get("cue", "")])
		var music := String(e.get("music", ""))
		if music.begins_with("@"):
			t.ok(GameState.is_declared(music.substr(1)), "%s: music flag '%s' is declared" % [w, music])
		else:
			t.ok(Chat.song_known(music) and ResourceLoader.exists("res://assets/audio/music/%s.ogg" % music), "%s: music '%s' is a song on disk" % [w, music])
		t.ok(String(e.get("journal", "")) != "" and not _has_emoji(String(e.get("journal", ""))), "%s: a journal line, no emoji" % w)
		t.ok(Chapters.has(int(e.get("chapter", 0))) or int(e.get("chapter", 0)) in [4, 5], "%s: chapter %s" % [w, e.get("chapter", "")])
		_cond(String(e.get("when", "")), w)
		var clock: Array = e.get("clock", [])
		if not clock.is_empty():
			t.ok(clock.size() == 2 and Conditions.minutes(String(clock[0])) >= 0 and Conditions.minutes(String(clock[1])) > Conditions.minutes(String(clock[0])), "%s: clock window [from, to]" % w)
		t.ok(String(e.get("offer", "spot")) in ["spot", "story"], "%s: offer is spot or story" % w)
	# every sit offered only by the story has a `$ sit` that plays it
	var played := {}
	for pair in DialogueData.nodes("cmd"):
		var n: Dictionary = pair[1]
		if String(n.name) == "sit" and not n.args.is_empty():
			played[String(n.args[0])] = true
	for id in sec:
		if String(sec[id].get("offer", "spot")) == "story":
			t.ok(played.has(String(id)), "world.json sit %s (offered by the story) is played by a `$ sit`" % id)
	for id in WorldData.section("finder_places"):
		var fp = WorldData.section("finder_places")[id]
		t.ok(fp is Dictionary and fp.get("pos") is Array and fp.pos.size() == 3, "world.json finder_places %s has pos" % id)


# ------------------------------------------------------------------ the kebab orders and the finale
func _check_kebab() -> void:
	var d = Support.read_json("res://data/kebab.json")
	if not t.ok(d is Dictionary, "data/kebab.json loads"):
		return
	var menus := {"base": d.get("bases", []), "sauce": d.get("sauces", []), "extra": d.get("extras", [])}
	for k in menus:
		t.ok(not menus[k].is_empty(), "kebab.json: the %s menu has words" % k)
		for word in menus[k]:
			t.ok(not _has_emoji(String(word)), "kebab.json: no emoji in '%s'" % word)
	var orders: Dictionary = d.get("orders", {})
	for id in orders:
		t.ok(_cast.has(String(id)) or String(id) == "mano", "kebab.json order '%s' is Mano or in CastDefs" % id)
		for k in menus:
			t.ok(String(orders[id].get(k, "")) in menus[k], "kebab.json %s's %s '%s' is on the menu" % [id, k, orders[id].get(k, "")])
	var everyone := {}
	for r in d.get("rounds", []):
		var rw := "kebab.json round %s" % r.get("id", "?")
		t.ok(not r.get("who", []).is_empty(), "%s: has tickets" % rw)
		for id in r.get("who", []):
			t.ok(orders.has(String(id)), "%s: %s has an order" % [rw, id])
			everyone[String(id)] = true
		for f in r.get("fields", []):
			t.ok(menus.has(String(f)), "%s: field '%s' is base, sauce or extra" % [rw, f])
		for id in r.get("cook", {}):
			t.ok(String(r.cook[id]) in menus.sauce and String(r.cook[id]) != String(orders.get(id, {}).get("sauce", "")),
				"%s: the cook misreads %s's sauce as another sauce on the menu" % [rw, id])
		t.ok(float(r.get("show", 0.0)) >= 1.0, "%s: a ticket shows for at least a second" % rw)
	t.ok(everyone.size() == 8, "kebab.json: the eight friends' orders are on the rail (%d)" % everyone.size())


## Chapter 5's "Want one?": one cue per friend, reached from their talk cue, giving them the other AirPod.
func _check_offers() -> void:
	for id in FRIENDS:
		var cue: String = "c5.offer_" + id
		if not t.ok(DialogueData.cues.has(cue), "%s exists (\"Want one?\" to %s)" % [cue, id]):
			continue
		var gives := false
		for pair in DialogueData.nodes("cmd"):
			if String(pair[0]) == cue and String(pair[1].name) == "set":
				var n: Dictionary = pair[1]
				if (n.args.size() > 1 and String(n.args[0]) == "given_to" and String(n.args[1]) == id) or String(n.kw.get("given_to", "")) == id:
					gives = true
		t.ok(gives, "%s sets given_to = \"%s\"" % [cue, id])
		var talk: String = "talk." + id
		var reached := false
		for pair in DialogueData.nodes("jump"):
			if String(pair[0]) == talk and String(pair[1].target) == cue:
				reached = true
		t.ok(reached, "%s jumps to %s in chapter 5" % [talk, cue])


# ------------------------------------------------------------------ collectibles, life, look-ats
const DUCKS_BY_CHAPTER := {1: 3, 2: 3, 3: 2, 4: 2, 5: 2}   # docs/DESIGN.md §3.8
const LOOK_KINDS := ["look", "read", "listen", "grab", "use"]
const MIN_LOOKATS := 80
const MIN_NIGHT := 25


func _check_stage5() -> void:
	# the twelve ducks
	var ducks := WorldData.section("ducks")
	t.ok(ducks.size() == 12, "world.json has twelve ducks (%d)" % ducks.size())
	var by := {}
	var glow := 0
	for id in ducks:
		var e: Dictionary = ducks[id]
		var w := "world.json duck %s" % id
		by[int(e.get("chapter", 0))] = by.get(int(e.get("chapter", 0)), 0) + 1
		t.ok(e.get("pos") is Array or _markers.get("ducks", {}).has(id), "%s: a pos, or a DUCK_ marker in the level" % w)
		var hint := String(e.get("hint", ""))
		t.ok(hint != "" and hint.length() <= MAX_CHARS and not _has_emoji(hint), "%s: the whisperer's hint, under %d characters, no emoji" % [w, MAX_CHARS])
		if bool(e.get("glow", false)):
			glow += 1
			t.ok(int(e.get("chapter", 0)) >= 4, "%s: a glowing duck is a night one (chapter 4 or 5)" % w)
	for n in DUCKS_BY_CHAPTER:
		t.ok(int(by.get(n, 0)) == int(DUCKS_BY_CHAPTER[n]), "chapter %d has %d ducks (%d)" % [n, DUCKS_BY_CHAPTER[n], by.get(n, 0)])
	t.ok(glow == 2, "the two night ducks glow (%d)" % glow)
	for id in _markers.get("ducks", {}):
		t.ok(ducks.has(id), "the level's DUCK_%s has a chapter in world.json ducks" % id)
	# Ishita's film: ten photo spots, then the group photo
	var photos := WorldData.section("photos")
	t.ok(photos.size() == Film.EXPOSURES, "world.json has %d photo spots for Ishita's %d exposures (%d)" % [Film.EXPOSURES, Film.EXPOSURES, photos.size()])
	t.ok(WorldData.section("shots").has("steps_group"), "the group photo, the eleventh exposure, has its shot (steps_group)")
	for id in photos:
		var e: Dictionary = photos[id]
		var w := "world.json photo %s" % id
		t.ok(e.get("pos") is Array and e.pos.size() == 3, "%s: pos [x, y, z]" % w)
		if e.has("look"):
			t.ok(e.look is Array and e.look.size() == 3 and float(e.get("tol", 35)) > 0.0, "%s: look [x, y, z] and a tolerance" % w)
		t.ok(float(e.get("range", 0)) > 0.0 and int(e.get("chapter", 0)) >= 1 and int(e.get("chapter", 0)) <= 5, "%s: a range and a chapter" % w)
		_cond(String(e.get("when", "")), w)
		for k in ["label", "think"]:
			var txt := String(e.get(k, ""))
			t.ok(txt != "" and txt.length() <= MAX_CHARS and not _has_emoji(txt), "%s: a %s, under %d characters, no emoji" % [w, k, MAX_CHARS])
	# every stop of Ishita's tour is on a photo spot, so its `$ photo film` puts that place on the film
	for c in Chapters.all():
		for tr in c.get("triggers", []):
			if String(tr.get("id", "")).begins_with("tour_"):
				var ref := String(tr.get("near", ""))
				var at := _ref_pos(ref)
				var hit := false
				for id in photos:
					if at != Vector3.INF and WorldData.vec(photos[id].pos).distance_to(at) + float(tr.get("radius", 3.0)) * 0.5 <= float(photos[id].get("range", 0)):
						hit = true
				t.ok(hit, "tour stop %s (%s) is on a photo spot" % [tr.id, ref])
	# overheard talk: 8 to 12 loops, two staged NPCs each, lines only, between those two
	var over := WorldData.section("overheard")
	t.ok(over.size() >= 8 and over.size() <= 12, "world.json has 8 to 12 overheard loops (%d)" % over.size())
	for id in over:
		var e: Dictionary = over[id]
		var w := "world.json overheard %s" % id
		var a := String(e.get("a", ""))
		var b := String(e.get("b", ""))
		var crowd := false
		for who in [a, b]:
			var known: bool = _cast.has(who) or (who.begins_with("crowd") and _markers.get("npcs", {}).has(who))
			t.ok(known, "%s: '%s' is in the cast or a crowd marker in the level" % [w, who])
			crowd = crowd or who.begins_with("crowd")
		t.ok(a != b, "%s: two people" % w)
		_cond(String(e.get("when", "")), w)
		var cue := String(e.get("cue", ""))
		if not t.ok(DialogueData.cues.has(cue), "%s: cue %s exists" % [w, cue]):
			continue
		var cards := DialogueData.cards().filter(func(c): return String(c.cue) == cue)
		t.ok(cards.size() >= 3 and cards.size() <= 9, "%s: 3 to 6 lines a play (%d cards with the variants)" % [w, cards.size()])
		for c in cards:
			t.ok(String(c.who) in [a, b] or (crowd and String(c.who) == "crowd"), "%s: %s speaks, one of the pair (%s, %s)" % [w, c.who, a, b])
		var extra := DialogueData.nodes("cmd").filter(func(pair): return String(pair[0]) == cue).size() \
			+ DialogueData.nodes("response").filter(func(pair): return String(pair[0]) == cue).size()
		t.ok(extra == 0, "%s: lines only (no commands, no choices)" % w)
		# a staged_only friend (Ishita, Joaquin, Cristina) is on campus only where a chapter stages them
		for who in [a, b]:
			if _cast.has(who) and bool(_cast[who].get("staged_only", false)):
				var chs := _chapters_of(String(e.get("when", "")))
				var staged := false
				for n in chs:
					if Chapters.get_chapter(n).get("stage", {}).has(who):
						staged = true
				t.ok(staged, "%s: %s is staged in a chapter the loop plays in %s" % [w, who, chs])
	# look-ats: kinds, readables, per room, night variants
	var spots := {}
	for id in _markers.get("spots", {}):
		spots[id] = {"pos": Support.v3(_markers.spots[id].pos), "kind": "look"}
	var wsp := WorldData.section("spots")
	for id in wsp:
		var e: Dictionary = wsp[id]
		var w := "world.json spot %s" % id
		spots[id] = {"pos": WorldData.vec(e.get("pos", [0, 0, 0])), "kind": String(e.get("kind", "look"))}
		t.ok(String(e.get("kind", "look")) in LOOK_KINDS, "%s: kind '%s' is one of %s" % [w, e.get("kind", "look"), LOOK_KINDS])
		if e.has("insert"):
			t.ok(String(e.get("kind", "")) == "read" and e.insert is Dictionary and e.insert.get("look") is Array and e.insert.look.size() == 3,
				"%s: a readable's insert has look [x, y, z]" % w)
	var per_room := {}
	for id in spots:
		var z := _zone_of(spots[id].pos)
		per_room[z] = per_room.get(z, 0) + 1
	t.info("look-ats: %d in all; per room %s" % [spots.size(), per_room])
	t.ok(spots.size() >= MIN_LOOKATS, "at least %d look-ats (%d)" % [MIN_LOOKATS, spots.size()])
	for z in _markers.get("zones", {}):
		t.ok(int(per_room.get(z, 0)) >= (4 if z == "passage" else 6), "room %s has at least %d look-ats (%d)" % [z, 4 if z == "passage" else 6, per_room.get(z, 0)])
	var night := 0
	var reads := 0
	for id in spots:
		if _cue_uses(DialogueData.cues.get("use." + String(id), {}).get("body", []), "night()"):
			night += 1
		if String(spots[id].kind) == "read" and wsp.get(id, {}).has("insert"):
			reads += 1
	t.ok(night >= MIN_NIGHT, "at least %d look-ats have a night variant (%d)" % [MIN_NIGHT, night])
	t.ok(reads >= 10 and reads <= 15, "10 to 15 readables open an insert (%d)" % reads)
	# idle life, the side stories, the journal
	for cue in ["idle.look", "idle.phone", "idle.phone_dead", "sit.all", "talk.whisperer", "side.survivor.ask", "side.survivor.sunset",
			"side.sup.coffee", "side.sup.horn", "side.sup.passed", "side.sup.missed", "side.ducks.hint", "side.ducks.reward", "use.horn"]:
		t.ok(DialogueData.cues.has(cue), "stage 5 cue %s exists" % cue)
	for cue in ["idle.look", "idle.phone", "idle.phone_dead", "sit.all"]:
		t.ok(DialogueData.is_think_only(cue), "%s is Mano's thoughts only (a bark)" % cue)
	var j = Support.read_json("res://data/journal.json")
	if t.ok(j is Dictionary, "data/journal.json loads"):
		for id in j.get("people", {}):
			t.ok(id in FRIENDS, "journal.json people: '%s' is one of the seven friends" % id)
			for e in j.people[id]:
				_cond(String(e.get("when", "")), "journal.json people %s" % id)
				var txt := String(e.get("text", ""))
				t.ok(txt != "" and txt.length() <= 100 and not _has_emoji(txt), "journal.json people %s: a short line, no emoji" % id)
		for e in j.get("side", []):
			for k in ["seen", "done", "fail"]:
				_cond(String(e.get(k, "")), "journal.json side %s %s" % [e.get("id", "?"), k])
		t.ok(j.get("duck_tips", []).size() >= 5, "journal.json: the duck page has its tips")
		t.ok(j.get("dijkstra", []).size() >= 3 and String(j.get("margin", "")) != "", "journal.json: the first page's Dijkstra notes and margin")


## The chapters a `when` can hold in, from its `chapter == n`, `>= n`, `<= n` terms (all chapters when it has none).
func _chapters_of(expr: String) -> Array:
	var out: Array = []
	for c in Chapters.numbers():
		out.append(int(c))
	for m in RegEx.create_from_string("chapter\\s*(==|>=|<=|<|>)\\s*(\\d+)").search_all(expr):
		var op := m.get_string(1)
		var v := int(m.get_string(2))
		out = out.filter(func(n): return (op == "==" and n == v) or (op == ">=" and n >= v) or (op == "<=" and n <= v) or (op == "<" and n < v) or (op == ">" and n > v))
	return out


func _ref_pos(ref: String) -> Vector3:
	var kind := ref.get_slice(":", 0)
	var id := ref.get_slice(":", 1)
	if kind == "point" and WorldData.section("points").has(id):
		return WorldData.vec(WorldData.section("points")[id].pos)
	if kind == "spot":
		if WorldData.section("spots").has(id):
			return WorldData.vec(WorldData.section("spots")[id].pos)
		if _markers.get("spots", {}).has(id):
			return Support.v3(_markers.spots[id].pos)
	return Vector3.INF


## The level zone a point is in (markers.json zones, as boxes; the smallest that holds it), or "outside".
func _zone_of(p: Vector3) -> String:
	var best := "outside"
	var best_v := INF
	var zones: Dictionary = _markers.get("zones", {})
	for id in zones:
		var c := Support.v3(zones[id].pos)
		var h := Support.v3(zones[id].half)
		var d := (p - c).abs()
		if d.x <= h.x and d.y <= h.y + 0.6 and d.z <= h.z:
			var v := h.x * h.y * h.z
			if v < best_v:
				best_v = v
				best = String(id)
	return best


func _cue_uses(body: Array, word: String) -> bool:
	for n: Dictionary in body:
		match String(n.t):
			"line":
				if String(n.get("cond", "")).contains(word):
					return true
			"if":
				for b in n.branches:
					if String(b.get("cond", "")).contains(word) or _cue_uses(b.body, word):
						return true
	return false


func _report_counts() -> void:
	var per_file := {}
	var per_chapter := {}
	for c in DialogueData.cards():
		var f := String(c.src).rsplit(":", true, 1)[0].get_file()
		per_file[f] = per_file.get(f, 0) + 1
		var m := RegEx.create_from_string("^c(\\d+)\\.").search(String(c.cue))
		if m:
			per_chapter["c" + m.get_string(1)] = per_chapter.get("c" + m.get_string(1), 0) + 1
	t.info("%d cues, %d cards; by file %s; chapter cues %s" % [DialogueData.cues.size(), DialogueData.cards().size(), per_file, per_chapter])
	for ch in MIN_CHAPTER_CARDS:
		t.ok(int(per_chapter.get(ch, 0)) >= int(MIN_CHAPTER_CARDS[ch]), "%s.* cues have at least %d cards (%d)" % [ch, MIN_CHAPTER_CARDS[ch], per_chapter.get(ch, 0)])
	var by_who := {}
	for c in DialogueData.cards():
		by_who[String(c.who)] = by_who.get(String(c.who), 0) + 1
	t.info("cards by speaker: %s" % [by_who])
