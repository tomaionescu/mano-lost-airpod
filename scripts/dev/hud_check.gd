extends Node
## Dev check (docs/DESIGN.md V2-05): the HUD in Mano's pen, run headless without the level. Every doodle draws
## inside its box; at most two toasts stay up and a repeat shows once; an objective change waits while the HUD is
## hidden, then strikes the old line, writes the new one, holds and lifts away; holding the journal key keeps
## it up; one-off hints show once per save and retire when used; a prompt starts with its verb; the waypoint is
## off by default; no HUD text gives a distance in metres.
##   Godot --headless --path . res://scenes/dev/hud_check.tscn      exit code 1 when a check fails

var _fails: Array = []
var _hud: HUD


func _ready() -> void:
	UITheme.init()
	GameState.reset_flags()
	_check("waypoint off by default", GameState.DEFAULT_SETTINGS.waypoint == false)
	for id in Doodles.IDS:
		var lines := Doodles.strokes(id, 0)
		var box := Rect2(Vector2(-4, -4), Vector2(56, 56))
		var inside := not lines.is_empty()
		for pts: PackedVector2Array in lines:
			for p in pts:
				inside = inside and box.has_point(p)
		_check("doodle %s draws inside its box" % id, inside)
		_check("doodle %s boils (frames differ)" % id, Doodles.strokes(id, 1)[0] != lines[0])
	_hud = HUD.new()
	add_child(_hud)
	await _frames(2)

	# toasts: two at most, a repeat shows once
	for t in [["Noted", "pencil"], ["Noted", "pencil"], ["+1 €", "coin"], ["Golden rubber duck 1/8", "duck"]]:
		_hud.toast(t[0], t[1])
	await _frames(2)
	_check("at most two toasts up", _live_toasts() <= 2)
	_check("the newest toast is up", _toast_texts().has("Golden rubber duck 1/8"))

	# an objective change while a conversation hides the HUD waits, then plays
	_hud.set_objective("Talk to Toma", false)
	_hud.set_hud_visible(false)
	_hud.set_objective("Ask around in SM14")
	await _wait(0.6)
	_check("a change waits while the HUD is hidden", _hud.strip._pending and not _hud.strip.visible)
	_hud.set_hud_visible(true)
	await _wait(0.1)
	_check("the change starts once the HUD is visible", _hud.strip._state in ["in", "strike", "write"])
	await _wait(2.4)
	var olds := 0
	var news := 0
	for r: Dictionary in _hud.strip._rows:
		if r.old:
			olds += 1
		else:
			news += 1
	_check("old line struck, new line written and underlined", _hud.strip._state == "hold" and olds == 1 and news == 1
		and _hud.strip._strike >= 1.0 and _hud.strip._under >= 1.0)
	_check("strip fits 560 px at 1080p", _hud.strip.size.x <= ObjectiveStrip.MAX_W + 1.0)
	await _wait(ObjectiveStrip.HOLD + 0.4)
	_check("the strip lifts away after 6 s", not _hud.strip.visible)

	# holding the journal key keeps the objective up
	_hud.peek_objective(true)
	await _wait(8.0)
	_check("peek holds the strip up", _hud.strip.visible and _hud.strip._state == "peek")
	_hud.peek_objective(false)
	await _wait(2.0)
	_check("the strip goes once the key is up", not _hud.strip.visible)

	# every torn outline is a simple polygon (the renderer cannot fill a self-crossing one)
	# (and every to-do the chapters can show, filled in)
	var texts: Array = ["Talk to Toma", "Find Karim in the Under", "Find 2 euros for a coffee (you have 1)", "Enjoy the stereo. (for now)"]
	for ch in Chapters.all():
		for td in ch.get("todos", []):
			texts.append(Chapters.text_of(td))
	for txt in texts:
		_hud.strip._layout("", txt, true)
		_check("torn outline of \"%s\" fills" % txt, not Geometry2D.triangulate_polygon(_hud.strip._paper).is_empty()
			and not Geometry2D.triangulate_polygon(_hud.strip._fringe).is_empty())

	# a long objective wraps on the ruling instead of running off the strip
	_hud.set_objective("Go to the lost & found at the Voltaire reception, then find Mme Dupont", false)
	_hud.peek_objective(true)
	await _wait(0.4)
	_check("a long objective wraps", _hud.strip._rows.size() >= 2 and _hud.strip.size.x <= ObjectiveStrip.MAX_W + 1.0)
	_hud.peek_objective(false)

	# hints: once per save, retired by use
	_hud.hint("move")
	await _wait(1.2)
	_check("the walking hint shows", _hud._hint_id == "move")
	_hud.hint_used("move")
	await _wait(1.0)
	_hud.hint("move")
	_check("a hint shows once per save", not "move" in _hud._hint_queue and "move" in GameState.flags.hints)
	_hud.hint_used("map")
	_hud.hint("map")
	_check("a hint used before it showed never shows", not "map" in _hud._hint_queue)

	# the prompt's words: a verb first, and the thing when the ring cannot point at it
	var it := Interactable.new()
	it.kind = "spot"
	it.id = "slide"
	it.label = "Read the slide"
	_check("a spot's prompt says the verb and the thing", PenPrompt.words_for(it) == "Read the slide")
	it.id = "fountain"
	it.label = "Fountain"
	_check("an unknown spot says Look", PenPrompt.words_for(it) == "Look")

	# no distances anywhere in the HUD
	var metres := RegEx.create_from_string("\\d+\\s?m\\b")
	for l in _hud.find_children("*", "Label", true, false):
		_check("no metres in \"%s\"" % (l as Label).text, metres.search((l as Label).text) == null)

	for f in _fails:
		print("[test] FAIL ", f)
	print("[test] hud_check: %d failed" % _fails.size())
	get_tree().quit(1 if not _fails.is_empty() else 0)


func _check(what: String, ok: bool) -> void:
	if not ok:
		_fails.append(what)


func _live_toasts() -> int:
	var n := 0
	for c in _hud.toasts.get_children():
		if c is StickyNote and not c.leaving:
			n += 1
	return n


func _toast_texts() -> Array:
	var out: Array = []
	for c in _hud.toasts.get_children():
		if c is StickyNote and not c.leaving:
			out.append(c.text)
	return out


func _frames(n: int) -> void:
	for i in n:
		await get_tree().process_frame


func _wait(sec: float) -> void:
	await get_tree().create_timer(sec).timeout
