extends RefCounted
## The headless quest walker (V2-20, V2-36): plays the story from data with no level, the way autotest=story does
## on screen. From chapter 1's start it plays the opening cue, then, each step, the main triggers due and then the
## main to-do's target (talk.<npc> or use.<spot>), answering every question and winning every minigame, until an
## ending. At every step: at most one main and two optional to-dos are active, never three `fetch` to-dos in a
## row, and the main to-do always has a target that resolves. A second, coverage pass takes every answer of every
## question once (the last first), loses each minigame once before winning it, and drops in on every talk.* and
## use.* cue along the way; it must reach the ending too. Reports the share of cards each pass showed.
## The four side stories play to their ends headless (_check_side): "Back in 5 min", "Is the sun still
## yellow?" (and too late, after the twist), "Segmentation fault" with the coffee and with the horn (and its two
## outcomes in chapter 4), and the duck whisperer at 0, 5 and 12 ducks.
## The walk starts at chapter 0 (the cold open) and ends on the recap after chapter 5's credits and
## post-credits; every friend's "Want one?" reply is reachable (_check_offers).

const Support := preload("res://tests/support.gd")
const GUARD := 300

var t


func run(report) -> void:
	t = report
	var main_pass := _walk(false)
	t.ok(main_pass.ended, "the critical path reaches the ending (%d steps)" % main_pass.steps)
	t.ok(main_pass.chapters == [1, 2, 3, 4, 5], "chapters begun on the way: %s (chapter 0, the cold open, starts the game)" % [main_pass.chapters])
	var f: Dictionary = main_pass.flags
	for k in ["cold_open_seen", "c1_done", "c2_done", "lf_twist", "camera", "ishita_met", "joaquin_met", "karim", "phone_dead", "phone_charging", "promise",
			"phone_charged", "promise_known", "cristina_note", "karim_cristina", "cristina_texted", "summit_done", "toma_beat", "c3_done",
			"met_cristina", "kebab_done", "pocket_empty", "found", "cristina_beat", "anisha_sos", "smuggled", "mouli_night", "anisha_beat",
			"c4_done", "toast_done", "group_photo", "c5_done", "credits_done"]:
		t.ok(bool(f.get(k, false)), "the critical path sets %s" % k)
	t.ok(String(f.get("foot_partner", "")) == "ian", "choice 0 everywhere: the pastry war's pain au chocolat makes Ian the babyfoot partner (got '%s')" % f.get("foot_partner", ""))
	t.ok(main_pass.found_chapter == 4, "the AirPod is found in chapter 4, not before (the twist): found first set in chapter %d" % main_pass.found_chapter)
	t.ok(String(f.get("given_to", "")) == "toma", "choice 0 and the to-do's target: the other AirPod goes to Toma (got '%s')" % f.get("given_to", ""))
	t.ok(main_pass.log.has("credits") and main_pass.log.has("recap") and main_pass.log.find("credits") < main_pass.log.find("recap"),
		"chapter 5 ends on the credits, then the post-credits, then the recap")
	t.ok(main_pass.log.has("photo group") and main_pass.log.has("airpods case") and main_pass.log.has("score ending"),
		"the finale: the group photo, the AirPods in the case for Anisha, the playlist song as the score (%s)" % [main_pass.log.filter(func(l): return String(l).begins_with("photo") or String(l).begins_with("airpods") or String(l).begins_with("score"))])
	t.ok(main_pass.minigames.has("kebab") and main_pass.minigames.has("findmy") and main_pass.minigames.has("soleil") and main_pass.minigames.count("moulinette") == 2,
		"chapter 4's minigames on the critical path: kebab, findmy, soleil and the night moulinette (%s)" % [main_pass.minigames])
	t.ok(main_pass.captions.has("Six hours earlier."), "the cold open ends on \"Six hours earlier.\" (%s)" % [main_pass.captions])
	# chapter 3 (V2-25): the tour shows three places and leaves Ishita a favourite; the playlist pick persists; the flood
	# and Cristina's message landed; the finder's place is the cafeteria
	t.ok(int(f.get("tour_count", 0)) == 3 and String(f.get("ishita_fav", "")) != "" and not bool(f.get("touring", true)),
		"Ishita's tour: three places, a favourite ('%s'), over" % f.get("ishita_fav", ""))
	t.ok(String(f.get("playlist", "")) in Chat.songs.get("playlist", []), "the playlist pick persists: '%s'" % f.get("playlist", ""))
	t.ok("flood" in f.get("chat_batches", []) and "cristina" in f.get("chat_batches", []) and "memory" in f.get("chat_batches", []),
		"the flood, Cristina's message and Joaquin's 21:00 landed (%s)" % [f.get("chat_batches", [])])
	t.ok(main_pass.log.has("phone finder cafe") and main_pass.log.has("phone finder under") and main_pass.log.find("phone finder cafe") < main_pass.log.find("phone finder under")
		and String(f.get("finder_place", "")) == "under" and String(f.get("finder_time", "")) == "20:31",
		"the finder app: the cafeteria, 19:12 (chapter 3), then the Under, 20:31 (chapter 4)")
	t.ok("sit_planter" in main_pass.sits, "choice 0 at the sunset sits Mano on the planter wall (%s)" % [main_pass.sits])
	t.ok(main_pass.songs.size() >= 1, "the playlist pick previews a song (%s)" % [main_pass.songs])
	for tr in ["pastry_war", "ishita_passage", "ishita_sm14", "joaquin_under", "sunset", "ishita_tour", "kebab_wait", "under_search", "sm14_acu", "steps_arrive"]:
		t.ok(tr in main_pass.triggers, "the critical path plays the main trigger %s (%s)" % [tr, main_pass.triggers])
	var stops: Array = main_pass.triggers.filter(func(x): return String(x).begins_with("tour_"))
	t.ok(stops.size() == 3, "the tour plays three of its six stops (%s)" % [stops])
	t.ok(not main_pass.log.has("bridge to the ending (no chapter 4)") and not main_pass.log.has("bridge to the ending (no chapter 6)"),
		"every chapter the story names is in the data: no bridge to the ending on the way")
	t.info("triggers on the critical path: %s" % [main_pass.triggers])
	t.info("critical path: %s" % " > ".join(main_pass.todos))
	t.info("critical path showed %d cards, %d choices, minigames %s" % [main_pass.cards, main_pass.choices, main_pass.minigames])
	var cover := _walk(true)
	t.ok(cover.ended, "the coverage pass reaches the ending too (%d steps)" % cover.steps)
	var all := {}
	for c in DialogueData.cards():
		if String(c.cue).begins_with("archive.") or String(c.cue) == "bridge.end":
			continue
		all["%s|%s" % [c.who, c.text]] = c
	var seen := {}
	for key in cover.seen:
		seen[key] = true
	var missing: Array = []
	var hit := 0
	for key in all:
		var c: Dictionary = all[key]
		if _was_seen(seen, String(c.who), String(c.text)):
			hit += 1
		else:
			missing.append(key)
	t.info("coverage pass: %d/%d cards shown (%d%%)" % [hit, all.size(), roundi(100.0 * hit / maxf(all.size(), 1))])
	for m in missing.slice(0, 30):
		t.info("  not shown: %s" % m)
	# a slow player (30 game minutes of walking between steps, as main._tick_clock ticks, under clock_cap): the clock
	# never goes back, and the pinned beats keep their times (the twist under 18:48, the sunset at 18:55)
	var slow := _walk(false, true)
	t.ok(slow.ended, "a slow player reaches the ending too (%d steps)" % slow.steps)
	t.ok(not slow.went_back, "a slow player's clock never goes back (%s)" % [slow.clocks])
	t.ok(slow.twist_clock == Conditions.minutes("18:48"), "a slow player's twist is at 18:48 (got %s)" % Conditions.clock_text(slow.twist_clock))
	t.ok(slow.sunset_clock == Conditions.minutes("18:55"), "a slow player's sunset is at 18:55 (got %s)" % Conditions.clock_text(slow.sunset_clock))
	t.ok(slow.c3_clock == Conditions.minutes("20:40"), "a slow player's chapter 3 ends at 20:40 (got %s)" % Conditions.clock_text(slow.c3_clock))
	t.ok(slow.flood_clock == Conditions.minutes("19:12"), "a slow player reads the flood at 19:12 (got %s)" % Conditions.clock_text(slow.flood_clock))
	t.ok(slow.found_clock > 0 and slow.found_clock <= Conditions.minutes("21:47"), "a slow player finds the AirPod by 21:47 (got %s)" % Conditions.clock_text(slow.found_clock))
	t.ok(slow.c4_clock == Conditions.minutes("23:40") or slow.c4_clock == Conditions.minutes("23:38"), "a slow player reaches the steps at 23:38-23:40, before chapter 5's 23:41 (got %s)" % Conditions.clock_text(slow.c4_clock))
	_check_bridge()
	_check_ch3_orders()
	_check_offers()
	_check_side()
	GameState.reset_flags()


## A data card was shown: the same speaker (any crowd model for `crowd`) and the same text, a {{…}} filled in.
static func _was_seen(seen: Dictionary, who: String, text: String) -> bool:
	var re: RegEx = null
	if text.contains("{{"):
		re = RegEx.create_from_string("^" + RegEx.create_from_string("\\{\\{[^}]*\\}\\}").sub(_escape(text), ".+", true) + "$")
	for key in seen:
		var k := String(key)
		var w := k.get_slice("|", 0)
		if w != who and not (who == "crowd" and w.begins_with("crowd")):
			continue
		var tx := k.substr(w.length() + 1)
		if tx == text or (re != null and re.search(tx)):
			return true
	return false


static func _escape(s: String) -> String:
	var out := ""
	for ch in s:
		out += ("\\" + ch) if ch in ".^$*+?()[]|\\" else ch
	return out


## One walk from a new game. `cover`: every answer once, every minigame lost once, every cue visited.
func _walk(cover: bool, slow := false) -> Dictionary:
	GameState.reset_flags()
	GameState.flags["chapter"] = Chapters.first()
	GameState.flags["clock"] = Conditions.minutes(String(Chapters.get_chapter(Chapters.first()).get("clock", "17:42")))
	Chapters.reset_tracking()
	var game = Support.FakeGame.new()
	var taken := {}       # "<line text>|<label>" -> true
	var lost := {}        # minigame name -> lost once
	game.dialogue.choose = func(step: Dictionary) -> int:
		if not cover:
			return 0
		var ask: Array = step.ask
		for i in range(ask.size() - 1, -1, -1):
			var k := "%s|%s" % [step.t, ask[i][0]]
			if not taken.has(k):
				taken[k] = true
				return i
		return 0
	var visits: Array = []
	if cover:
		for id in DialogueData.cues:
			if String(id).begins_with("talk.") or String(id).begins_with("use."):
				visits.append(String(id))
		visits.sort()
	# the opening: chapter 1's start cue with Toma
	game.play(game.story.intro())
	var todos: Array = []
	var kinds: Array = []
	var stuck := 0
	var last_sig := ""
	var steps := 0
	var clocks: Array = []
	var went_back := false
	var twist_clock := -1
	var sunset_clock := -1
	var c3_clock := -1
	var flood_clock := -1
	var found_chapter := -1
	var found_clock := -1
	var iters := 0
	while steps < GUARD and not game.ended and iters < 40000:
		iters += 1
		steps += 1
		Chapters.track()
		if found_chapter < 0 and bool(GameState.flags.get("found", false)):
			found_chapter = Chapters.current()
			found_clock = Chapters.clock()
		if slow:
			var now := Chapters.clock()
			if twist_clock < 0 and bool(GameState.flags.get("lf_twist", false)):
				twist_clock = now
			if sunset_clock < 0 and bool(GameState.flags.get("c2_done", false)):
				sunset_clock = now
			if c3_clock < 0 and bool(GameState.flags.get("c3_done", false)):
				c3_clock = now
			if flood_clock < 0 and "flood" in GameState.flags.get("chat_batches", []):
				flood_clock = now
			if not clocks.is_empty() and now < int(clocks.back()):
				went_back = true
			# play time passes only between scenes: one that follows another at once (the wake-up after chapter 1's
			# card, a minigame's result) gets none
			if game.pending.is_empty() and game.minigames.is_empty():
				GameState.flags["clock"] = mini(now + 30, maxi(Chapters.clock_cap(), now))
			clocks.append(Chapters.clock())
		# what the last conversation started comes first, as on screen
		if not game.pending.is_empty():
			var p: Array = game.pending.pop_front()
			game.play(p[0])
			continue
		if not game.minigames.is_empty():
			var mg: Array = game.minigames.pop_front()
			var win := true
			if cover and not lost.has(mg[0]):
				lost[mg[0]] = true
				win = false
			(mg[2] as Callable).call(win)
			game.story.run_after()
			continue
		_check_todos(game)
		# the main triggers due, wherever Mano is: the walker goes there, as autotest=story does
		var due: Array = Chapters.pending_triggers(null, true)
		if not due.is_empty():
			Chapters.mark_fired(due[0])
			game.log.append("trigger %s" % due[0].get("id", ""))
			game.play(game.story.steps(String(due[0].get("cue", ""))))
			continue
		if cover and not visits.is_empty():
			steps -= 1   # a drop-in visit is not a step of the story
			var cue: String = visits.pop_front()
			if not _offered(cue):
				continue
			var ctx := {"crowd": "crowd3"} if cue == "talk.crowd" else {}
			game.play(game.story.steps(cue, ctx))
			continue
		var td := Chapters.main_todo()
		if not t.ok(not td.is_empty(), "%s: a main to-do while the story is not over (flags %s)" % ["coverage" if cover else "critical", _flag_summary()]):
			break
		var id := String(td.get("id", ""))
		if todos.is_empty() or todos.back() != id:
			todos.append(id)
			if cover:   # everyone and everything again at each new step of the story: their lines change with it
				for cue in DialogueData.cues:
					if String(cue).begins_with("talk.") or String(cue).begins_with("use."):
						visits.append(String(cue))
			kinds.append(String(td.get("kind", "")))
			if kinds.size() >= 3:
				var k3 := kinds.slice(kinds.size() - 3)
				t.ok(k3 != ["fetch", "fetch", "fetch"], "never three fetch to-dos in a row (%s)" % [todos.slice(todos.size() - 3)])
		var tg := Chapters.target(game)
		if not t.ok(not tg.is_empty(), "to-do %s has a target that resolves" % id):
			break
		game.pos = tg.pos
		var sig := "%s|%s" % [id, _flag_summary()]
		stuck = stuck + 1 if sig == last_sig else 0
		last_sig = sig
		if not t.ok(stuck < 8, "the walk moves on (stuck on %s)" % id):
			break
		if String(tg.kind) == "npc":
			game.play(game.story.talk(String(tg.id)))
		elif String(tg.kind) == "spot":
			game.play(game.story.use(String(tg.id)))
		else:
			t.fail("to-do %s points at %s:%s, which Mano cannot talk to or use" % [id, tg.kind, tg.id])
			break
	var seen: Array = []
	for s in game.dialogue.shown:
		seen.append("%s|%s" % [s[0], s[1]])
	var mgs: Array = []
	for l in game.log:
		if String(l).begins_with("minigame"):
			mgs.append(String(l).get_slice(" ", 1))
	var trs: Array = []
	for l in game.log:
		if String(l).begins_with("trigger "):
			trs.append(String(l).substr(8))
	return {"ended": game.ended, "steps": steps, "chapters": game.chapters_begun, "todos": todos, "seen": seen,
		"cards": game.dialogue.shown.size(), "choices": game.dialogue.choices.size(), "minigames": mgs,
		"flags": GameState.flags.duplicate(true), "triggers": trs, "log": game.log.duplicate(),
		"clocks": clocks.map(func(c): return Conditions.clock_text(int(c))), "went_back": went_back, "twist_clock": twist_clock,
		"sunset_clock": _card_clock(game, 3, sunset_clock), "c3_clock": _card_clock(game, 4, c3_clock), "flood_clock": flood_clock, "sits": game.sits.duplicate(),
		"songs": game.songs.duplicate(), "found_chapter": found_chapter, "found_clock": found_clock, "c4_clock": _card_clock(game, 5, -1),
		"captions": game.captions.duplicate()}


## The story clock just before chapter n's card (the last beat of chapter n - 1 sets it, and the card moves it on
## in the same step), or `fallback`.
static func _card_clock(game, n: int, fallback: int) -> int:
	for c in game.card_clocks:
		if int(c[0]) == n:
			return int(c[1])
	return fallback


## A use.<spot> cue the coverage pass may drop in on now: a data/world.json spot (or a level spot with a
## world.json spot_when) only while its `when` holds, as the game offers it.
static func _offered(cue: String) -> bool:
	if not cue.begins_with("use."):
		return true
	var id := cue.substr(4)
	var ws: Dictionary = WorldData.section("spots")
	if ws.has(id):
		return Conditions.eval(String(ws[id].get("when", "")))
	return Conditions.eval(WorldData.spot_when(id))


## At most one main and two optional to-dos active (this chapter's and the ones carried from earlier chapters).
func _check_todos(_game) -> void:
	# several main to-dos may hold at once (the first one wins): what shows is one
	var opts := Chapters.active_optional_count()
	t.ok(opts <= 2, "at most two optional to-dos at once (chapter %d: %d)" % [Chapters.current(), opts])
	t.ok(Chapters.optional_todos().size() <= 2, "the journal lists at most two optional to-dos")
	# a later chapter's main to-do shows only once this chapter has ended (its card still to come), never mid-chapter
	var td := Chapters.main_todo()
	if not td.is_empty() and not td in Chapters.todos(Chapters.current()):
		t.ok(bool(GameState.flags.get(String(Chapters.info().get("ends_with", "")), false)),
			"chapter %d shows the next chapter's to-do '%s' only after it has ended" % [Chapters.current(), td.get("id", "")])


## A chapter the data does not have plays bridge.end, which ends the game.
func _check_bridge() -> void:
	GameState.reset_flags()
	var game = Support.FakeGame.new()
	game.begin_chapter(99)
	t.ok(game.pending.size() == 1, "a chapter the data does not have plays bridge.end")
	if game.pending.size() == 1:
		game.play(game.pending[0][0])
	t.ok(game.ended, "bridge.end reaches the ending page")


## Chapter 3 in the orders a player can take. A save written under the card, before Karim's phone scene
## has played through, is `start_pending` (a Continue plays c3.phone again), and Karim with the phone still dead
## gives it back; the playlist before the pastry summit leaves the summit at 19:55, before the cafeteria closes at
## 20:00; "Leave them to it" brings the next talk straight back to the counter.
func _check_ch3_orders() -> void:
	GameState.reset_flags()
	var sf: Dictionary = Chapters.get_chapter(3).get("start_flags", {})
	for k in sf:
		GameState.flags[k] = GameState._copy(sf[k])
	GameState.coerce_flags()
	GameState.flags["chapter"] = 3
	GameState.flags["clock"] = Conditions.minutes(String(Chapters.get_chapter(3).get("clock", "19:10")))
	Chapters.reset_tracking()
	t.ok(Chapters.start_pending(), "chapter 3 under its card, before Karim's phone scene: start_pending (a Continue plays c3.phone again)")
	_check_todos(null)   # no to-do of chapter 4 ("Cristina and Joaquin, 21:00") under chapter 3's card
	t.ok(Chapters.main_todo().is_empty() or Chapters.main_todo() in Chapters.todos(3),
		"under chapter 3's card the objective is chapter 3's or none (got '%s')" % Chapters.main_todo().get("id", ""))
	var game = Support.FakeGame.new()
	game.play(game.story.talk("karim"))
	var shown: Array = game.dialogue.shown.map(func(x): return String(x[1]))
	t.ok(shown.has("Mano! Your phone. One hundred per cent.") and bool(GameState.flags.get("phone_charged", false)),
		"talk.karim with the phone not given back yet plays c3.phone (first lines %s)" % [shown.slice(0, 2)])
	t.ok(not Chapters.start_pending(), "after c3.phone the chapter has started (finder '%s')" % GameState.flags.get("finder_place", ""))
	game.play(game.story.use("cristina_note_cafe"))
	game.play(game.story.talk("karim"))
	t.ok(bool(GameState.flags.get("cristina_texted", false)), "the note and Karim: Cristina has written")
	var picks: Array = []
	game.dialogue.choose = func(step: Dictionary) -> int:
		var labels: Array = step.ask.map(func(a): return String(a[0]))
		for want in picks:
			var i := labels.find(want)
			if i >= 0:
				return i
		return 0
	# the playlist first
	picks.assign(["\"Evening\", Kevin MacLeod", "This one"])   # in place: the lambda holds this array
	var before := Chapters.clock()
	game.play(game.story.talk("toma"))
	t.ok(String(GameState.flags.get("playlist", "")) != "", "the playlist before the summit: picked '%s'" % GameState.flags.get("playlist", ""))
	t.ok(Chapters.clock() >= before and Chapters.clock() <= Conditions.minutes("19:55"),
		"the playlist before the summit leaves the clock before 19:55 (%s)" % Chapters.clock_text())
	# the summit: left to it once, then the last pastry
	picks.assign(["Leave them to it"])
	game.play(game.story.talk("ian"))
	t.ok(bool(GameState.flags.get("summit_heard", false)) and not bool(GameState.flags.get("summit_done", false)), "\"Leave them to it\" sets summit_heard")
	var n0: int = game.dialogue.shown.size()
	picks.assign(["Buy the last pastry"])
	game.play(game.story.talk("ian"))
	var again: Array = game.dialogue.shown.slice(n0).map(func(x): return String(x[1]))
	t.ok(not again.has("Mano. Tell Silvia the pastry war is over.") and again.has("The counter. One pastry left. The last one of the day."),
		"the next talk goes straight back to the counter (%s)" % [again.slice(0, 3)])
	t.ok(bool(GameState.flags.get("summit_done", false)) and Chapters.clock() == Conditions.minutes("19:55"),
		"the summit after the playlist is at 19:55, before the cafeteria closes at 20:00 (%s)" % Chapters.clock_text())
	GameState.reset_flags()


## "Want one?" (chapter 5): from the steps after the group photo, talking to each of the seven friends and taking
## choice 0 gives that friend the other AirPod (flags.given_to), shares the song and rolls the credits; "Not yet"
## gives it to nobody. All seven replies are reachable.
func _check_offers() -> void:
	var sf: Dictionary = Chapters.get_chapter(5).get("start_flags", {})
	for id in ["toma", "anisha", "ian", "silvia", "ishita", "cristina", "joaquin"]:
		GameState.reset_flags()
		for k in sf:
			GameState.flags[k] = GameState._copy(sf[k])
		GameState.coerce_flags()
		GameState.flags["chapter"] = 5
		GameState.flags["group_photo"] = true
		Chapters.reset_tracking()
		var game = Support.FakeGame.new()
		t.ok(String(Chapters.target(game).get("id", "")) == "toma" or not Chapters.target(game).is_empty(), "chapter 5's to-do points at the steps")
		game.dialogue.choose = func(_step) -> int: return 1
		game.play(game.story.talk(id))
		t.ok(String(GameState.flags.get("given_to", "")) == "", "\"Not yet\" to %s gives the AirPod to nobody" % id)
		game.dialogue.choose = func(_step) -> int: return 0
		var n0: int = game.dialogue.shown.size()
		game.play(game.story.talk(id))
		var said: Array = game.dialogue.shown.slice(n0).map(func(x): return "%s: %s" % [x[0], x[1]])
		var reply: Array = said.filter(func(x): return String(x).begins_with(id + ":"))
		t.ok(String(GameState.flags.get("given_to", "")) == id and bool(GameState.flags.get("c5_done", false)) and game.credits_rolled == 1,
			"\"Want one?\" to %s: given_to '%s', the song shared, the credits roll (%s)" % [id, GameState.flags.get("given_to", ""), reply])
		t.ok(not reply.is_empty() and said.has("mano: Want one?"), "%s answers \"Want one?\" in their own words: %s" % [id, reply])
	GameState.reset_flags()


static func _flag_summary() -> String:
	var f := GameState.flags
	return "ch%s %s%s%s%s%s%s%s c%s %s" % [f.get("chapter"), "T" if f.toma else "-", "I" if f.ines else "-", "K" if f.karim else "-",
		"S" if f.sign else "-", "M" if f.madame_met else "-", "C" if f.coffee else "-", "G" if f.coffee_given else "-", f.coins,
		"F" if f.found else "-"]


## The side stories (docs/DESIGN.md §3.9), each from the flags it needs, answering choice 0 unless said.
func _check_side() -> void:
	var game = Support.FakeGame.new()
	# "Back in 5 min"
	_side_flags(2, {"coffee_given": true})
	game.play(game.story.talk("waiting"))
	t.ok(bool(GameState.flags.get("side_waiting", false)), "Back in 5 min: served once Mme Dupont is back (side_waiting)")
	_side_flags(4, {"side_waiting": true})
	game.play(game.story.talk("waiting"))
	t.ok(bool(GameState.flags.get("waiting_bye", false)) and String(GameState.flags.get("stage_over", {}).get("waiting", "")) == "hide"
		and Chapters.stage_of("waiting").get("hide", false), "Back in 5 min: goodnight in chapter 4, then gone (waiting_bye, staged hide)")
	# "Is the sun still yellow?": asked before the twist he comes out; at the sunset he sees it
	_side_flags(2, {})
	game.play(game.story.talk("student2"))
	t.ok(bool(GameState.flags.get("survivor_out", false)), "Is the sun still yellow?: before the twist he says yes (survivor_out)")
	GameState.flags["lf_twist"] = true
	t.ok(String(Chapters.stage_of("student2").get("point", "")) == "planter_survivor", "Is the sun still yellow?: from the twist he waits at the planter wall")
	game.play(game.story.steps("c2.sunset"))
	t.ok(bool(GameState.flags.get("survivor_sun", false)), "Is the sun still yellow?: he sees the 18:55 sun at the planter wall (survivor_sun)")
	_side_flags(2, {"lf_twist": true})
	game.dialogue.choose = func(step) -> int: return 0
	game.play(game.story.talk("student2"))
	t.ok(not bool(GameState.flags.get("survivor_out", false)), "Is the sun still yellow?: after the twist it is too late (no 'Come and see')")
	# "Segmentation fault": the coffee, then the horn; the outcomes in chapter 4
	_side_flags(2, {"coffee_given": true})
	game.play(game.story.use("coffee"))
	t.ok(bool(GameState.flags.get("spare_coffee", false)), "Segmentation fault: the machine owes Mano a coffee once Mme Dupont has hers (spare_coffee)")
	GameState.flags["clock"] = Conditions.minutes("18:40")
	game.play(game.story.talk("sleeper"))
	t.ok(bool(GameState.flags.get("sup_awake", false)) and String(GameState.flags.get("sup_how", "")) == "coffee" and bool(GameState.flags.get("sup_clue", false)),
		"Segmentation fault: woken with the coffee before 19:00 (sup_awake, sup_how coffee)")
	_side_flags(2, {"sup_clue": true})
	game.play(game.story.use("horn"))
	t.ok(bool(GameState.flags.get("horn", false)), "Segmentation fault: the BDE's air horn grabbed (horn)")
	GameState.flags["clock"] = Conditions.minutes("18:45")
	game.play(game.story.talk("sleeper"))
	t.ok(bool(GameState.flags.get("sup_awake", false)) and String(GameState.flags.get("sup_how", "")) == "horn", "Segmentation fault: woken with the horn (sup_how horn)")
	game.play(game.story.talk("sleeper"))
	_side_flags(4, {"sup_awake": true, "sup_how": "horn"})
	var n0: int = game.dialogue.shown.size()
	game.play(game.story.talk("sleeper"))
	var said: Array = game.dialogue.shown.slice(n0).map(func(x): return String(x[1]))
	t.ok(bool(GameState.flags.get("sup_after", false)) and said.any(func(x): return String(x).contains("passed")), "Segmentation fault: chapter 4, he passed (%s)" % [said])
	_side_flags(4, {})
	n0 = game.dialogue.shown.size()
	game.play(game.story.talk("sleeper"))
	said = game.dialogue.shown.slice(n0).map(func(x): return String(x[1]))
	t.ok(said.has("Did I miss it?"), "Segmentation fault: asleep through it, chapter 4 asks \"Did I miss it?\" (%s)" % [said])
	_side_flags(3, {"sup_clue": true, "spare_coffee": true})
	game.play(game.story.talk("sleeper"))
	t.ok(not bool(GameState.flags.get("sup_awake", false)), "Segmentation fault: after 19:00 (chapter 3) it is too late")
	# the duck whisperer: hints from four ducks, duck zero at twelve
	_side_flags(1, {})
	game.play(game.story.talk("whisperer"))
	t.ok(bool(GameState.flags.get("whisperer_met", false)) and not bool(GameState.flags.get("duck_zero", false)), "The duck whisperer: met at 0 ducks, no hint yet")
	GameState.flags["duck_count"] = 5
	n0 = game.dialogue.shown.size()
	game.play(game.story.talk("whisperer"))
	said = game.dialogue.shown.slice(n0).map(func(x): return "%s: %s" % [x[0], x[1]])
	t.ok(int(GameState.flags.get("duck_hints", 0)) == 1 and said.size() >= 2 and String(said[-1]).begins_with("whisperer:"), "The duck whisperer: at 5 ducks, a hint (%s)" % [said])
	GameState.flags["duck_count"] = 12
	game.play(game.story.talk("whisperer"))
	t.ok(bool(GameState.flags.get("duck_zero", false)) and game.toasts.has("Duck zero"), "The duck whisperer: at 12, duck zero")
	# moments 6/6 and all twelve ducks have their lines on the steps (c5.steps reads ducks_all, duck_zero, survivor_sun)
	var sf: Dictionary = Chapters.get_chapter(5).get("start_flags", {})
	_side_flags(5, sf)
	GameState.flags["ducks_all"] = true
	GameState.flags["merch"] = true
	GameState.flags["duck_zero"] = true
	GameState.flags["survivor_sun"] = true
	n0 = game.dialogue.shown.size()
	game.play(game.story.steps("c5.steps"))
	said = game.dialogue.shown.slice(n0).map(func(x): return String(x[1]))
	t.ok(said.any(func(x): return String(x).contains("all twelve golden ducks")) and said.any(func(x): return String(x).contains("sun was orange")),
		"chapter 5's steps: the twelve ducks and the survivor's orange sun are mentioned")
	GameState.reset_flags()


func _side_flags(chapter: int, f: Dictionary) -> void:
	GameState.reset_flags()
	for k in f:
		GameState.flags[k] = GameState._copy(f[k])
	GameState.flags["chapter"] = chapter
	GameState.flags["camera"] = true
	GameState.coerce_flags()
	Chapters.reset_tracking()
