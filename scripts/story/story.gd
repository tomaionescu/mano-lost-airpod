class_name Story
extends RefCounted
## The story's facade (V2-19): the calls the game makes (intro, ending, talk, use, objective, target, clue, setf),
## answered from data. Every line lives in res://dialogue/*.dlg (DialogueData), the
## chapters, to-dos and clock in data/chapters.json (Chapters), positions and conditions in data/world.json
## (WorldData), flags in data/flags.json. Flags live in GameState.flags so they save with the game.
## Story is also the runner the compiled steps act on: push, jump and end_now go to game.dialogue, commands to
## StoryCommands, and `$ say` / `$ chapter` wait in `after` until the dialogue ends (main._on_dialogue_finished).

var game   # Main, or a test's stand-in with the same calls
var commands: StoryCommands
var _after: Array[Callable] = []


func _init(g) -> void:
	game = g
	commands = StoryCommands.new(self)
	DialogueData.load_all()
	Chapters.load_data()
	WorldData.load_data()


func F(key: String, def = false):
	return GameState.flags.get(key, def)


func setf(key: String, value) -> void:
	if not GameState.is_declared(key):
		push_warning("Story: flag '%s' is not declared in data/flags.json" % key)
	GameState.flags[key] = value
	GameState.flags_changed.emit()


static func cap(t: String) -> String:
	return t.substr(0, 1).to_upper() + t.substr(1)


# ------------------------------------------------------------------ cues
## A cue's steps, ready for Dialogue.say().
func steps(cue: String, ctx := {}) -> Array:
	return DialogueData.steps(cue, self, ctx)


func has_cue(cue: String) -> bool:
	return DialogueData.has_cue(cue)


## The opening's conversation: the chapter's start cue (chapter 1: the wake-up with Toma).
func intro() -> Array:
	var c: Dictionary = Chapters.get_chapter(Chapters.current())
	return steps(String(c.get("start_cue", "c1.wake")))


## v1's ending (the lost & found, the AirPod, the drop): autotest=ending plays it on its own.
func ending() -> Array:
	return steps("post.v1_ending")


func talk(id: String) -> Array:
	if id.begins_with("crowd"):
		return steps("talk.crowd", {"crowd": id})
	return steps("talk." + id) if has_cue("talk." + id) else steps("talk._default")


func use(spot: String) -> Array:
	return steps(use_cue(spot))


## The cue a spot plays: use.<spot>, or use._default.
func use_cue(spot: String) -> String:
	return "use." + spot if has_cue("use." + spot) else "use._default"


## A think-only cue (DialogueData.is_think_only) played at once without the screen: its commands run now, and its
## lines come back as [who, text] for Dialogue.bark(), shown one after the other while Mano keeps walking.
func bark_cue(cue: String, ctx := {}) -> Array:
	var r := BarkRunner.new(self)
	r.run(DialogueData.steps(cue, r, ctx))
	return r.lines


## Plays compiled steps with no screen and no waiting: Callables run, lines are collected (a look-at's barks).
class BarkRunner:
	extends RefCounted
	var story
	var lines: Array = []
	var _queue: Array = []
	var _ended := false

	func _init(s) -> void:
		story = s

	func run(steps: Array) -> void:
		_queue = steps.duplicate()
		var guard := 0
		while not _queue.is_empty() and not _ended and guard < 500:
			guard += 1
			var st = _queue.pop_front()
			if st is Callable:
				st.call()
			elif st is Array:
				lines.append([String(st[0]), String(st[1])])
			elif st is Dictionary:
				lines.append([String(st.who), String(st.t)])

	func push(s: Array) -> void:
		_queue = s + _queue

	func jump(s: Array) -> void:
		_queue = s.duplicate()

	func end_now() -> void:
		_ended = true

	func pause(_seconds: float) -> void:
		pass

	func wait_phone() -> void:
		pass

	func command(node: Dictionary, ctx := {}) -> void:
		story.command(node, ctx)


# ------------------------------------------------------------------ objectives
func objective() -> String:
	return Chapters.objective_text()


## Where the current objective is, for the waypoint and the map: {pos, label} or {}.
func target() -> Dictionary:
	return Chapters.target(game)


func clue(text: String) -> void:
	var clues: Array = F("clues", [])
	if text in clues:
		return
	clues.append(text)
	setf("clues", clues)
	game.toast("Noted", "pencil")
	# the first note in the notebook is when the notebook and the map start to matter (one-off hints)
	game.hud.hint("journal")
	game.hud.hint("map")


# ------------------------------------------------------------------ the runner the compiled steps act on
func push(s: Array) -> void:
	game.dialogue.push(s)


func jump(s: Array) -> void:
	game.dialogue.jump(s)


func end_now() -> void:
	game.dialogue.end_now()


func pause(seconds: float) -> void:
	game.dialogue.pause_for(seconds)


## The conversation waits until Mano puts his phone away (`$ phone open`).
func wait_phone() -> void:
	if game.get("phone") != null and game.dialogue.has_method("wait_until"):
		game.dialogue.wait_until(game.phone.closed)


func command(node: Dictionary, ctx := {}) -> void:
	commands.run(node, ctx)


## Runs `cb` once the current dialogue has ended (`$ say`, `$ chapter`).
func after(cb: Callable) -> void:
	_after.append(cb)


func has_after() -> bool:
	return not _after.is_empty()


## Runs what waited for the dialogue to end; true if anything did. A sit-down started by one of them (`$ sit`, V2-14)
## keeps the rest waiting until Mano stands up (main.end_sit runs them): `$ sit` then `$ chapter 3` plays the
## chapter card once he is back on his feet.
func run_after() -> bool:
	if _after.is_empty():
		return false
	# the ones waiting now; whatever they start (a conversation's own `$ chapter`) waits for that one's end
	var cbs := _after.duplicate()
	_after.clear()
	while not cbs.is_empty():
		var cb: Callable = cbs.pop_front()
		cb.call()
		if not cbs.is_empty() and game.has_method("is_sitting") and game.is_sitting():
			_after = cbs + _after
			break
	return true
