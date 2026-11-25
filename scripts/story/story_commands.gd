class_name StoryCommands
extends RefCounted
## The `$ name args key=value` commands a .dlg file may run (docs/ARCHITECTURE.md). SPEC lists each one: its
## positional arguments ([name, type, required]), the keys it takes, its stage (a group number: is_built() runs the
## commands up to BUILT_STAGE) and what it does; the validator (tests/validate_dialogue.gd) reads SPEC, so a new
## command is one SPEC entry plus one `_c_<name>` function here. Argument types: flag (declared in data/flags.json),
## value, text, word, number, hhmm, cue, minigame, npc, preset (WorldEnv.TIMES), doodle (Doodles.IDS), stem (a
## sound), hint (HUD.HINTS), group (a lamp group), id, who, point, where, shot, phone_arg (checked per phone action),
## sit (a world.json sit), song (a data/songs.json track), photo (group or film), airpods (case or ear) and score (a
## song or "@flag").

const SPEC := {
	"set": {"args": [["flag", "flag", true], ["value", "value", false]], "kw": ["*flag"], "stage": 1,
		"doc": "set a declared flag: `$ set toma` (true), `$ set choco = \"pac\"`, `$ set coffee = false`"},
	"add": {"args": [["flag", "flag", true], ["n", "number", true]], "kw": [], "stage": 1,
		"doc": "add to a number flag: `$ add coins -2`"},
	"clue": {"args": [["text", "text", true]], "kw": [], "stage": 1,
		"doc": "a journal clue, the 'Noted' toast and the journal and map hints (v1 Story.clue)"},
	"toast": {"args": [["text", "text", true], ["doodle", "doodle", false]], "kw": [], "stage": 1,
		"doc": "a sticky-note toast; the doodle is a Doodles id, never a character"},
	"sfx": {"args": [["stem", "stem", true], ["db", "number", false]], "kw": [], "stage": 1, "doc": "Sfx.play"},
	"coin": {"args": [["id", "id", true]], "kw": [], "stage": 1,
		"doc": "a one-off coin: got_<id>, coins +1, the coin sound and '+1 €' (nothing the second time)"},
	"minigame": {"args": [["name", "minigame", true]], "kw": ["sit_at", "stand_at", "win", "lose", "with", "*opt"], "stage": 1,
		"doc": "game.start_minigame(); its result plays `win` or `lose` as a conversation `with` an npc. Ends the cue"},
	"say": {"args": [["cue", "cue", true]], "kw": ["with"], "stage": 1,
		"doc": "when this dialogue ends, play the cue (as a conversation `with` an npc)"},
	"chapter": {"args": [["n", "number", true]], "kw": [], "stage": 1,
		"doc": "when this dialogue ends, main.begin_chapter(n); without chapter n in the data, bridge.end plays"},
	"clock": {"args": [["at", "hhmm", true]], "kw": [], "stage": 1, "doc": "the story clock (flags.clock) to HH:MM"},
	"time": {"args": [["preset", "preset", true]], "kw": ["fade"], "stage": 1,
		"doc": "WorldEnv.apply_time under a fade to black (fade=0.6 s); only a preset of the chapter's `times`"},
	"lamps": {"args": [["group", "group", true], ["level", "number", true], ["seconds", "number", false]], "kw": [], "stage": 1,
		"doc": "WorldEnv.set_lamps: one lamp group to a level (the street lamps at 18:55)"},
	"hint": {"args": [["id", "hint", true]], "kw": [], "stage": 1, "doc": "a one-off key hint (HUD.hint)"},
	"banner": {"args": [["title", "text", true], ["sub", "text", false]], "kw": [], "stage": 1, "doc": "HUD.show_banner"},
	"give_airpod": {"args": [], "kw": [], "stage": 1, "doc": "the second AirPod in Mano's ear (v1's ending)"},
	"drop_airpod": {"args": [["where", "id", false]], "kw": [], "stage": 1, "doc": "it falls out again, filmed from the floor (v1's gag); `grate`: down a drain grate at his feet (the post-credits)"},
	"ending": {"args": [], "kw": [], "stage": 1, "doc": "the 'à suivre…' page (main.show_ending)"},
	"wait": {"args": [["seconds", "number", true]], "kw": [], "stage": 1, "doc": "a pause in a cutscene"},
	# stage 2 (V2-21 staging and the follower, the phone's lock screen, a framed shot)
	"place": {"args": [["who", "who", true], ["point", "point", true]], "kw": [], "stage": 2,
		"doc": "Mano (`mano`) or a character straight to a data/world.json point, now (under a cut)"},
	"stage": {"args": [["npc", "npc", true], ["where", "where", true]], "kw": ["now", "walk"], "stage": 2,
		"doc": "a character to a world.json point, `hide` or `home` (flags.stage_over) at the end of this dialogue, or at once with now=true; walk=true walks there (through the point's `via`); the chapter's own staging takes over at the next card"},
	"follow": {"args": [["npc", "npc", true]], "kw": [], "stage": 2, "doc": "a character walks behind Mano (flags.following)"},
	"unfollow": {"args": [["npc", "npc", true]], "kw": [], "stage": 2, "doc": "stops following, and stays where they are until staged"},
	"phone": {"args": [["action", "phone", true], ["arg", "phone_arg", false], ["text", "text", false]], "kw": [], "stage": 2,
		"doc": "Mano's phone: `show`, `preview <who> \"text\"` (a buzz), `die` (17:43), `hide` (stage 2); `charge` (100 %, the lock screen), `flood <batch>` (a dialogue/chat.json batch lands: buzzes and previews), `open <app or thread>` (the phone in his hand: messages, find, music, home, or a chat thread; the conversation waits until he puts it away), `finder <place> \"HH:MM\"` (the finder app's last-seen place, a data/world.json finder_places id, and its pin on the map) (stage 3). The conversation waits on it a moment"},
	"shot": {"args": [["name", "shot", true]], "kw": ["cut"], "stage": 2,
		"doc": "a framed camera from data/world.json \"shots\" ({from, look, fov}), with the letterbox; `clear` hands the camera back"},
	# stage 3 (V2-14 sit-downs, the playlist's previews)
	"sit": {"args": [["id", "sit", true]], "kw": [], "stage": 3,
		"doc": "when this dialogue ends, Mano sits down at a data/world.json sit (main.begin_sit); whatever else waited for the end (`$ chapter`) waits until he stands up"},
	"song": {"args": [["stem", "song", true], ["seconds", "number", false]], "kw": [], "stage": 3,
		"doc": "a track from data/songs.json previewed for `seconds` (10) from the phone, the conversation waiting on it; the place's music comes back after"},
	# stage 4 (V2-26, V2-27: the cold open, the finale, the credits)
	"photo": {"args": [["kind", "photo", true]], "kw": [], "stage": 4,
		"doc": "a photo on Ishita's disposable camera: `film` keeps the frame on screen as a print (user://film/, flags.film_shots), `group` frames everyone on the steps (world.json shot steps_group), counts down and keeps that one (the last exposure). The conversation waits on it"},
	"airpods": {"args": [["where", "airpods", true]], "kw": [], "stage": 4,
		"doc": "`case`: both AirPods out of his ears and into the case (flags.airpods_case; the finder says so); `ear`: back in"},
	"credits": {"args": [], "kw": [], "stage": 4,
		"doc": "the credits roll (main.roll_credits): the camera rises over the courtyard, the names and the film prints; then post.credits with Mme Dupont. Ends the cue"},
	"recap": {"args": [], "kw": [], "stage": 4, "doc": "the last page: \"à suivre…\" and the recap of the night (main.show_recap)"},
	"caption": {"args": [["text", "text", true], ["seconds", "number", false]], "kw": [], "stage": 4,
		"doc": "to black, and a line written on in Mano's pen in the middle of it for `seconds` (2.4): \"Six hours earlier.\". The conversation waits on it"},
	"freeze": {"args": [], "kw": [], "stage": 4,
		"doc": "the picture stops: a still of the frame on screen holds over the scene (the cold open) until a caption or the end of the cue"},
	"score": {"args": [["stem", "score", true]], "kw": [], "stage": 4,
		"doc": "a track as the score from now on (a data/songs.json stem, or \"@flag\" for the one a flag holds: @playlist): the places' music does not take over again until the credits are over"},
	# stage 5 (V2-31: the side story "The duck whisperer")
	"duck_hint": {"args": [], "kw": [], "stage": 5,
		"doc": "the duck whisperer says where the first duck still out there is (data/world.json ducks `hint`, from this chapter or an earlier one), or that none is out right now"},
}
## The commands this build runs (the others are in SPEC for the validator and the docs).
const BUILT_STAGE := 5
## `$ phone` actions this build has.
const PHONE_ACTIONS := ["show", "preview", "die", "hide", "charge", "flood", "open", "finder"]

var story   # Story (the facade): story.game is main.gd or a test's stand-in


func _init(s) -> void:
	story = s


static func is_built(name: String) -> bool:
	return SPEC.has(name) and int(SPEC[name].stage) <= BUILT_STAGE


func run(node: Dictionary, _ctx := {}) -> void:
	var name := String(node.get("name", ""))
	if not is_built(name):
		push_error("StoryCommands: '%s' is not a command this build runs (%s)" % [name, node.get("src", "")])
		return
	call("_c_" + name, node.get("args", []), node.get("kw", {}))


func _game():
	return story.game


# ------------------------------------------------------------------ flags
func _c_set(args: Array, kw: Dictionary) -> void:
	if args.is_empty():
		for k in kw:
			story.setf(String(k), kw[k])
		return
	story.setf(String(args[0]), args[1] if args.size() > 1 else true)


func _c_add(args: Array, _kw: Dictionary) -> void:
	var k := String(args[0])
	var v = GameState.flags.get(k, GameState.flag_default(k))
	story.setf(k, (v if v is float else int(v)) + args[1])


func _c_clue(args: Array, _kw: Dictionary) -> void:
	story.clue(DialogueData.format(String(args[0])))


func _c_coin(args: Array, _kw: Dictionary) -> void:
	var k := "got_" + String(args[0])
	if GameState.flags.get(k, false):
		return
	story.setf(k, true)
	story.setf("coins", int(GameState.flags.get("coins", 0)) + 1)
	Sfx.play("coin")
	_game().toast("+1 €", "coin")


## The clock only goes forward: a `$ clock` earlier than now leaves it (chapters.json clock_holds keep the walk
## from passing a pinned time, so this is a safety net; a new chapter's card sets its own clock outright).
func _c_clock(args: Array, _kw: Dictionary) -> void:
	var m := Conditions.minutes(String(args[0]))
	if m < Chapters.clock():
		push_warning("clock: %s is before the story clock %s, left at %s" % [args[0], Chapters.clock_text(), Chapters.clock_text()])
		return
	GameState.flags["clock"] = m


# ------------------------------------------------------------------ feedback
func _c_toast(args: Array, _kw: Dictionary) -> void:
	_game().toast(DialogueData.format(String(args[0])), String(args[1]) if args.size() > 1 else "")


func _c_sfx(args: Array, _kw: Dictionary) -> void:
	if args.size() > 1:
		Sfx.play(String(args[0]), float(args[1]))
	else:
		Sfx.play(String(args[0]))


func _c_hint(args: Array, _kw: Dictionary) -> void:
	_game().hud.hint(String(args[0]))


func _c_banner(args: Array, _kw: Dictionary) -> void:
	_game().hud.show_banner(DialogueData.format(String(args[0])), DialogueData.format(String(args[1])) if args.size() > 1 else "")


# ------------------------------------------------------------------ flow
## Starts the minigame and drops the rest of the queue (a minigame ends its cue: the validator checks nothing
## follows it). Its result plays `win` or `lose`.
func _c_minigame(args: Array, kw: Dictionary) -> void:
	var opts := {}
	for k in kw:
		if not k in ["win", "lose", "with"]:
			opts[k] = kw[k]
	var win := String(kw.get("win", ""))
	var lose := String(kw.get("lose", ""))
	var with_npc := String(kw.get("with", ""))
	var s = story
	s.jump([])
	_game().start_minigame(String(args[0]), opts, func(ok):
		var cue := win if ok else lose
		if cue != "":
			s.game.say(s.steps(cue), with_npc))


func _c_say(args: Array, kw: Dictionary) -> void:
	var cue := String(args[0])
	var with_npc := String(kw.get("with", ""))
	var s = story
	s.after(func(): s.game.say(s.steps(cue), with_npc))


func _c_chapter(args: Array, _kw: Dictionary) -> void:
	var n := int(args[0])
	var s = story
	s.after(func(): s.game.begin_chapter(n))


func _c_time(args: Array, kw: Dictionary) -> void:
	_game().time_cut(String(args[0]), float(kw.get("fade", 0.6)))


func _c_lamps(args: Array, _kw: Dictionary) -> void:
	_game().set_lamps(String(args[0]), float(args[1]), float(args[2]) if args.size() > 2 else 0.0)


func _c_give_airpod(_args: Array, _kw: Dictionary) -> void:
	_game().player.give_second_airpod()


func _c_drop_airpod(args: Array, _kw: Dictionary) -> void:
	_game().drop_airpod(String(args[0]) == "grate" if not args.is_empty() else false)


func _c_ending(_args: Array, _kw: Dictionary) -> void:
	_game().show_ending()


func _c_wait(args: Array, _kw: Dictionary) -> void:
	story.pause(float(args[0]))


# ------------------------------------------------------------------ staging, the phone, shots
func _c_place(args: Array, _kw: Dictionary) -> void:
	_game().place_at(String(args[0]), String(args[1]))


## The override lives in flags.stage_over (it saves); main.restage() applies it now or when the dialogue ends.
func _c_stage(args: Array, kw: Dictionary) -> void:
	var id := String(args[0])
	var over = GameState.flags.get("stage_over", {})
	if not over is Dictionary:
		over = {}
	over[id] = ("walk:" if bool(kw.get("walk", false)) else "") + String(args[1])
	GameState.flags["stage_over"] = over
	if bool(kw.get("now", false)):
		_game().restage(id)


func _c_follow(args: Array, _kw: Dictionary) -> void:
	var id := String(args[0])
	var f: Array = GameState.flags.get("following", [])
	if not id in f:
		f.append(id)
	GameState.flags["following"] = f
	_game().restage(id)


## Stops following where they stand: until a `$ stage` or the chapter's staging places them, they stay put.
func _c_unfollow(args: Array, _kw: Dictionary) -> void:
	var id := String(args[0])
	var f: Array = GameState.flags.get("following", [])
	f.erase(id)
	GameState.flags["following"] = f
	_game().restage(id)


## main.phone_cmd returns how long the conversation waits on the phone: seconds, or -1 for "until Mano puts it
## away" (`$ phone open`).
func _c_phone(args: Array, _kw: Dictionary) -> void:
	var secs: float = _game().phone_cmd(String(args[0]), String(args[1]) if args.size() > 1 else "",
		DialogueData.format(String(args[2])) if args.size() > 2 else "")
	if secs < 0.0:
		story.wait_phone()
	elif secs > 0.0:
		story.pause(secs)


# ------------------------------------------------------------------ sit-downs and songs
func _c_sit(args: Array, _kw: Dictionary) -> void:
	var id := String(args[0])
	var s = story
	s.after(func(): s.game.begin_sit(id))


## A preview from the phone: the song plays `seconds` (10), the conversation waits on it, then the place's music
## comes back (main.preview_song).
func _c_song(args: Array, _kw: Dictionary) -> void:
	var secs := float(args[1]) if args.size() > 1 else 10.0
	_game().preview_song(String(args[0]), secs)
	story.pause(secs)


func _c_shot(args: Array, kw: Dictionary) -> void:
	_game().camera_shot(String(args[0]), bool(kw.get("cut", true)))


# ------------------------------------------------------------------ the finale
## main.take_photo returns how long the conversation waits on it (the self-timer, the flash).
func _c_photo(args: Array, _kw: Dictionary) -> void:
	var secs: float = _game().take_photo(String(args[0]))
	if secs > 0.0:
		story.pause(secs)


func _c_airpods(args: Array, _kw: Dictionary) -> void:
	_game().set_airpods(String(args[0]))


## Like a minigame, the credits end the cue: the roll plays, then the post-credits as a conversation of their own.
func _c_credits(_args: Array, _kw: Dictionary) -> void:
	story.jump([])
	_game().roll_credits()


func _c_recap(_args: Array, _kw: Dictionary) -> void:
	_game().show_recap()


func _c_caption(args: Array, _kw: Dictionary) -> void:
	var secs := float(args[1]) if args.size() > 1 else 2.4
	story.pause(_game().caption(DialogueData.format(String(args[0])), secs))


func _c_freeze(_args: Array, _kw: Dictionary) -> void:
	_game().freeze_frame()
	story.pause(0.35)


func _c_score(args: Array, _kw: Dictionary) -> void:
	var stem := String(args[0])
	if stem.begins_with("@"):
		stem = String(GameState.flags.get(stem.substr(1), ""))
	_game().set_score(stem)


# ------------------------------------------------------------------ the duck whisperer
## The whisperer's next line: the hint for the first duck still out (Ducks.next_hint), pushed as their line.
func _c_duck_hint(_args: Array, _kw: Dictionary) -> void:
	var d = _game().get("ducks")
	var h: Dictionary = d.next_hint() if d != null and d.has_method("next_hint") else {}
	if h.is_empty():
		story.push([["whisperer", "None out there right now. Come back later in the night.", "smirk"]])
	else:
		story.push([["whisperer", String(h.hint), "smirk"]])
