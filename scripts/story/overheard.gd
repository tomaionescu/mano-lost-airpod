class_name Overheard
extends Node
## Overheard talk (V2-31, docs/DESIGN.md §4.7): two people talking near Mano, in small grey italics at
## the bottom left of the screen. It never takes the controls: Mano walks on while it plays. A loop
## (data/world.json "overheard": {a, b, cue, radius, when}) starts when Mano is in play within `radius` (6 m) of the
## pair, with a line of sight to one of them, both on campus and nobody talking to Mano; it plays its cue
## (dialogue/overheard.dlg, through Story.bark_cue: lines only) one line after the other, the speaker's lips moving
## and the other one looking at them. Walking off past 1.5 × the radius fades it out. A loop heard to its end goes
## into flags.overheard and comes back only after REPEAT seconds; a new loop waits GAP seconds after the last one.

const POLL := 0.3
const GAP := 14.0        # seconds between two loops
const REPEAT := 240.0    # a loop heard to its end plays again after this long, if Mano is still around
const LINE_BASE := 2.0   # a line shows 2 s + 0.055 s per character
const LINE_PER_CHAR := 0.055
const FADE := 0.25
const SIZE := 23         # 27 px at 1080p: small, under the subtitles' size
const WIDTH := 560.0

var game
var label: RichTextLabel
var _poll := 0.0
var _gap := 4.0
var _cur := {}           # {id, lines: [[who, text]], i, t, hold, a: NPC, b: NPC}
var _last_end := {}      # id -> seconds since start when it last ended
var _clock := 0.0
var _alpha := 0.0
## What played, for the autotests: [{id, line, mode, frozen}] (the last 40).
var log: Array = []
## autotest=overheard: only this loop may start ("" for any).
var only := ""


func setup(g) -> void:
	game = g
	label = RichTextLabel.new()
	label.fit_content = true
	label.scroll_active = false
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.custom_minimum_size = Vector2(WIDTH, 0)
	label.size = Vector2(WIDTH, 0)
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	label.add_theme_font_override("normal_font", UITheme.print_italic)
	label.add_theme_font_override("italics_font", UITheme.print_italic)
	label.add_theme_font_override("bold_font", UITheme.print_700)
	label.add_theme_color_override("default_color", Color("#cfcac0"))
	UITheme.over_scene(label, 5, 0.4)
	label.modulate.a = 0.0
	label.visible = false
	game.hud.root.add_child(label)


func playing() -> String:
	return String(_cur.get("id", ""))


func line_text() -> String:
	if _cur.is_empty() or int(_cur.i) >= _cur.lines.size():
		return ""
	return String(_cur.lines[_cur.i][1])


func _process(dt: float) -> void:
	if game == null or game.player == null:
		return
	_clock += dt
	var on: bool = game.mode == "play"
	# one text stream at a time: while Mano's own thought (a bark) shows, the loop waits faded out and none starts
	var hush: bool = game.dialogue.is_barking()
	if not _cur.is_empty():
		if not on or game.dialogue.running or _too_far():
			_stop(false)
		elif not hush:
			_advance(dt)
	elif on and not hush:
		_gap -= dt
		_poll -= dt
		if _poll <= 0.0 and _gap <= 0.0:
			_poll = POLL
			_try_start()
	_alpha = move_toward(_alpha, 1.0 if not _cur.is_empty() and on and not hush else 0.0, dt / FADE)
	label.modulate.a = _alpha
	label.visible = _alpha > 0.0
	if label.visible:
		var area: Vector2 = game.hud.root.size
		label.position = Vector2(56.0, roundf(area.y - 196.0 - label.size.y))   # over the one-off key hint notes


## The pair of a loop, as NPC nodes (named cast or level crowd markers), or [].
func pair_of(e: Dictionary) -> Array:
	var a = _npc(String(e.get("a", "")))
	var b = _npc(String(e.get("b", "")))
	return [a, b] if a != null and b != null else []


func _npc(id: String):
	if game.npcs.has(id):
		return game.npcs[id]
	for c in game.crowd:
		if String(c.id) == id:
			return c
	return null


func _try_start() -> void:
	var me: Vector3 = game.player.global_position
	var heard: Array = GameState.flags.get("overheard", [])
	var best := ""
	var best_d := INF
	var sec := WorldData.section("overheard")
	for id in sec:
		var e: Dictionary = sec[id]
		if only != "" and id != only:
			continue
		if String(e.get("when", "")) != "" and not Conditions.eval(String(e.when)):
			continue
		if _last_end.has(id) and _clock - float(_last_end[id]) < (REPEAT if id in heard else 60.0):
			continue
		var p := pair_of(e)
		if p.is_empty() or not p[0].visible or not p[1].visible or p[0].following or p[1].following:
			continue
		var mid: Vector3 = (p[0].global_position + p[1].global_position) * 0.5
		var d := me.distance_to(mid)
		if d > float(e.get("radius", 6.0)) or absf(me.y - mid.y) > 2.5:
			continue
		if not (_sees(p[0]) or _sees(p[1])):
			continue
		# a loop not heard yet comes first
		var score := d + (100.0 if id in heard else 0.0)
		if score < best_d:
			best_d = score
			best = String(id)
	if best != "":
		_begin(best, sec[best])


func _sees(n) -> bool:
	var from: Vector3 = game.player.rig.head_position() if game.player.rig else game.player.global_position + Vector3.UP * 1.6
	var to: Vector3 = n.rig.head_position() if n.rig else n.global_position + Vector3.UP * 1.5
	var q := PhysicsRayQueryParameters3D.create(from, to, 1)
	return game.get_world_3d().direct_space_state.intersect_ray(q).is_empty()


func _begin(id: String, e: Dictionary) -> void:
	var p := pair_of(e)
	var raw: Array = game.story.bark_cue(String(e.get("cue", "over." + id)))
	if raw.is_empty():
		_last_end[id] = _clock
		return
	# `crowd` lines go to the crowd member of the pair (both crowd: one line each in turn)
	var a_id := String(e.get("a", ""))
	var b_id := String(e.get("b", ""))
	var lines: Array = []
	var turn := 0
	for l in raw:
		var who := String(l[0])
		if who == "crowd":
			if p[0].crowd and p[1].crowd:
				who = a_id if turn % 2 == 0 else b_id
				turn += 1
			else:
				who = a_id if p[0].crowd else b_id
		lines.append([who, String(l[1])])
	_cur = {"id": id, "lines": lines, "i": -1, "t": 0.0, "hold": 0.0, "a": p[0], "b": p[1], "radius": float(e.get("radius", 6.0))}
	print("[overheard] %s starts (%d lines), Mano %.1f m away" % [id, lines.size(), game.player.global_position.distance_to((p[0].global_position + p[1].global_position) * 0.5)])
	_next_line()


func _next_line() -> void:
	_cur.i = int(_cur.i) + 1
	_quiet()
	if int(_cur.i) >= _cur.lines.size():
		_stop(true)
		return
	var l: Array = _cur.lines[_cur.i]
	var who := String(l[0])
	var text := String(l[1])
	_cur.t = 0.0
	_cur.hold = LINE_BASE + LINE_PER_CHAR * text.length()
	var speaker = _cur.a if _speaker_id(_cur.a) == who else _cur.b
	var other = _cur.b if speaker == _cur.a else _cur.a
	if speaker.rig:
		speaker.rig.talking = true
		if other.rig:
			other.rig.look_at_point = speaker.rig.head_position()
			speaker.rig.look_at_point = other.rig.head_position()
	var info: Dictionary = game._speaker_info(who) if not speaker.crowd else {"name": "Student", "color": Color("#c9d1d9")}
	label.clear()
	label.push_font(UITheme.print_700, SIZE)
	label.push_color(Color(info.get("color", Color.WHITE)).lerp(Color("#bdb8ae"), 0.45))
	label.add_text(String(info.get("name", "")) + ": ")
	label.pop()
	label.pop()
	label.push_font(UITheme.print_italic, SIZE)
	label.add_text(text)
	label.pop()
	log.append({"id": _cur.id, "line": text, "mode": game.mode, "frozen": game.player.frozen})
	if log.size() > 40:
		log = log.slice(log.size() - 40)
	if OS.is_debug_build():
		print("[overheard] %s: %s" % [who, text])


func _speaker_id(n) -> String:
	return String(n.id)


func _advance(dt: float) -> void:
	_cur.t = float(_cur.t) + dt
	if float(_cur.t) >= float(_cur.hold):
		_next_line()


func _too_far() -> bool:
	var mid: Vector3 = (_cur.a.global_position + _cur.b.global_position) * 0.5
	return game.player.global_position.distance_to(mid) > float(_cur.radius) * 1.5


func _quiet() -> void:
	for n in [_cur.get("a"), _cur.get("b")]:
		if n != null and is_instance_valid(n) and n.rig:
			n.rig.talking = false
			n.rig.look_at_point = null


func _stop(heard: bool) -> void:
	if _cur.is_empty():
		return
	var id := String(_cur.id)
	_quiet()
	_last_end[id] = _clock
	if heard:
		var h: Array = GameState.flags.get("overheard", []).duplicate()
		if not id in h:
			h.append(id)
			GameState.flags["overheard"] = h
		print("[overheard] %s heard to the end" % id)
	else:
		print("[overheard] %s faded out at line %d" % [id, int(_cur.i) + 1])
	_cur = {}
	_gap = GAP
