class_name ObjectiveStrip
extends Control
## The objective on a strip torn from Mano's Seyès notebook, top-left (docs/DESIGN.md §5.5, docs/ART_DIRECTION.md).
## It shows only when the objective changes, or while the journal key is held: a change strikes the old
## line through in red, writes the new one on in Mano's pen and underlines it, holds it 6 s, then the strip
## lifts away. The HUD calls tick() every frame with whether it may show.

const PAPER_SHADER := preload("res://scripts/fx/paper.gdshader")
const SIZE := 30            # Mynerve, 36 px at 1080p
const ROW := 40.0           # Seyès violet line spacing (8 mm), 48 px at 1080p
const FIRST := 34.0         # the first violet line below the strip's top edge: the text sits on it
const MARGIN := 24.0        # the red margin line
const TEXT_X := 33.0        # where Mano starts writing
const PAD_R := 24.0         # paper left after the longest line, before the torn end
const PAD_B := 15.0         # paper under the last line, for the descenders
const MAX_W := 467.0        # 560 px at 1080p
const HOLD := 6.0           # seconds a new objective stays up
const CPS := 25.0           # the pen writes about 25 characters a second
const IN_T := 0.22          # the strip is laid down...
const OUT_T := 0.15         # ...and lifted away a little faster (exits run at about 0.65 of the entry)
const STRIKE_T := 0.22
const UNDER_T := 0.18
const TILT := -0.7          # degrees

var current := ""           # the objective now (what holding the journal key shows)
var _old := ""              # the line to strike through when the pending change plays
var _pending := false       # a change waits until the HUD is visible again
var _peek := false
var _state := ""            # "", "in", "strike", "write", "under", "hold", "peek", "out"
var _t := 0.0
var _alpha := 0.0
var _lift := 0.0
var _strike := 0.0
var _under := 0.0
var _chars := 0.0
var _new_chars := 0
var _rows: Array = []       # {"label", "text", "w", "y", "old"}
var _paper := PackedVector2Array()
var _fringe := PackedVector2Array()
var _ink: Control
var _home := Vector2.ZERO


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	var m := ShaderMaterial.new()
	m.shader = PAPER_SHADER
	m.set_shader_parameter("row", ROW)
	m.set_shader_parameter("first_line", FIRST)
	m.set_shader_parameter("margin_x", MARGIN)
	material = m
	rotation_degrees = TILT
	# the red pen marks go over the handwriting, so they are drawn by a child laid above the labels
	_ink = Control.new()
	_ink.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_ink.draw.connect(_draw_ink)
	add_child(_ink)
	modulate.a = 0.0
	visible = false


## Where the strip rests (its top-left corner) in the HUD.
func set_home(p: Vector2) -> void:
	_home = p
	position = p


## A new objective. `animate` plays the change (struck through, rewritten) the next time the HUD is visible;
## without it the text just changes quietly.
func set_objective(text: String, animate := true) -> void:
	if text == current:
		return
	if animate:
		if not _pending:
			_old = current
		_pending = true
	current = text
	if not animate and _state in ["hold", "peek"]:
		_layout("", current, true)


## The objective replaced outright (a save loaded, a chapter started from the title): nothing is struck through or
## written on and no change is left pending; a strip that is up shows the new text whole.
func reset(text: String) -> void:
	current = text
	_old = ""
	_pending = false
	if _state == "":
		return
	if current == "":
		_next_state("out")
		return
	_layout("", current, true)
	if _state in ["in", "strike", "write", "under"]:
		_next_state("hold")


## Shows the current objective while `on` (the journal key held down).
func peek(on: bool) -> void:
	if on == _peek:
		return
	_peek = on
	if on:
		if _state in ["", "out"] and current != "":
			_layout("", current, true)
			_state = "peek"
			_t = 0.0
		elif _state == "hold":
			_state = "peek"
	elif _state == "peek":
		_state = "hold"
		_t = HOLD - 1.4   # lingers a moment after the key comes up


## Shows the current objective for `seconds` (after loading a save).
func show_for(seconds: float) -> void:
	if current == "" or _pending:
		return
	if _state in ["", "out"]:
		_layout("", current, true)
		_state = "hold"
	if _state == "hold":
		_t = maxf(0.0, HOLD - seconds)


func tick(dt: float, can_show: bool) -> void:
	var calm: bool = GameState.settings.get("reduce_motion", false)
	if not can_show:
		# hidden by a conversation or a menu: fade fast and freeze; a change waits for the next look
		_alpha = move_toward(_alpha, 0.0, dt / 0.12)
		_apply()
		if _state in ["hold", "peek"] and _alpha <= 0.0:
			_state = ""
		return
	if _pending and _state in ["", "hold", "peek", "out"]:
		_begin_change(calm)
	if _state == "":
		_alpha = 0.0
		_apply()
		return
	_t += dt
	match _state:
		"in":
			var k := 1.0 if calm else clampf(_t / IN_T, 0.0, 1.0)
			var e := 1.0 - pow(1.0 - k, 4.0)
			_alpha = e
			_lift = -10.0 * (1.0 - e)
			if k >= 1.0:
				_next_state("strike" if _has_old() else "write")
		"strike":
			_alpha = 1.0
			_strike = 1.0 if calm else clampf(_t / STRIKE_T, 0.0, 1.0)
			_ink.queue_redraw()
			if _strike >= 1.0:
				_next_state("write")
		"write":
			_alpha = 1.0
			_chars = float(_new_chars) if calm else _chars + dt * CPS
			_show_chars(int(_chars))
			if _chars >= _new_chars:
				_next_state("under")
		"under":
			_under = 1.0 if calm else clampf(_t / UNDER_T, 0.0, 1.0)
			_ink.queue_redraw()
			if _under >= 1.0:
				_next_state("hold")
		"hold":
			_alpha = move_toward(_alpha, 1.0, dt / 0.15)
			_lift = move_toward(_lift, 0.0, dt * 60.0)
			if _peek:
				_state = "peek"
			elif _t >= HOLD:
				_next_state("out")
		"peek":
			_alpha = move_toward(_alpha, 1.0, dt / 0.15)
			_lift = move_toward(_lift, 0.0, dt * 60.0)
		"out":
			var k := 1.0 if calm else clampf(_t / OUT_T, 0.0, 1.0)
			_alpha = 1.0 - k * k
			_lift = -6.0 * k
			if k >= 1.0:
				_state = ""
				_alpha = 0.0
	_apply()


func _apply() -> void:
	modulate.a = _alpha
	visible = _alpha > 0.002
	position = _home + Vector2(0, _lift)


func _next_state(s: String) -> void:
	_state = s
	_t = 0.0


func _has_old() -> bool:
	for r: Dictionary in _rows:
		if r.old:
			return true
	return false


func _begin_change(calm: bool) -> void:
	_pending = false
	var old := _old if _old != current else ""
	_old = ""
	if current == "":
		return
	var was_up := _alpha > 0.5 and _state in ["hold", "peek"]
	if was_up:
		old = _rows_text()   # strike what is on the strip now
	_layout(old, current, false)
	_strike = 0.0
	_under = 0.0
	_chars = 0.0
	_show_chars(0)
	if was_up:
		_next_state("strike" if _has_old() else "write")
	else:
		_next_state("in")
		_lift = -10.0
	Sfx.ui("objective", -6.0)


func _rows_text() -> String:
	var parts: Array = []
	for r: Dictionary in _rows:
		if not r.old:
			parts.append(r.text)
	return " ".join(parts)


## Lays the strip out: the struck line(s) first, then the new one, each on a violet line; `written` shows the
## new text whole (no write-on).
func _layout(old: String, text: String, written: bool) -> void:
	for r: Dictionary in _rows:
		(r.label as Label).queue_free()
	_rows.clear()
	var font: Font = UITheme.pen
	var asc := font.get_ascent(SIZE)
	var y := FIRST
	var widest := 120.0
	_new_chars = 0
	for part: Array in [[old, true], [text, false]]:
		for row: String in _wrap(part[0]):
			var l := UITheme.label(row, SIZE, UITheme.pen, Color(UITheme.INK_BLUE, 0.72) if part[1] else UITheme.INK_BLUE)
			l.visible_characters_behavior = TextServer.VC_CHARS_AFTER_SHAPING
			l.position = Vector2(TEXT_X, y - asc)
			l.mouse_filter = Control.MOUSE_FILTER_IGNORE
			add_child(l)
			var w := font.get_string_size(row, HORIZONTAL_ALIGNMENT_LEFT, -1, SIZE).x
			widest = maxf(widest, w)
			_rows.append({"label": l, "text": row, "w": w, "y": y, "old": part[1]})
			if not part[1]:
				_new_chars += row.length()
			y += ROW
	move_child(_ink, -1)
	size = Vector2(TEXT_X + widest + PAD_R, y - ROW + PAD_B)
	_ink.size = size
	_tear(hash(text) & 0xFFFF)
	if written:
		_strike = 1.0
		_under = 1.0
		_show_chars(_new_chars)
	queue_redraw()
	_ink.queue_redraw()


func _wrap(text: String) -> Array:
	var rows: Array = []
	if text == "":
		return rows
	var para := TextParagraph.new()
	para.add_string(text, UITheme.pen, SIZE)
	para.width = MAX_W - TEXT_X - PAD_R
	para.break_flags = TextServer.BREAK_MANDATORY | TextServer.BREAK_WORD_BOUND
	for i in para.get_line_count():
		var r := para.get_line_range(i)
		var s := text.substr(r.x, r.y - r.x).strip_edges()
		if s != "":
			rows.append(s)
	return rows


func _show_chars(n: int) -> void:
	var left := n
	for r: Dictionary in _rows:
		if r.old:
			continue
		var l: Label = r.label
		var count := String(r.text).length()
		l.visible_characters = -1 if left >= count else maxi(left, 0)
		left -= count


## The torn outline: the left edge is the page's cut edge, the other three are torn; a lighter fringe of
## fibres sticks out past the torn edges.
func _tear(seed_value: int) -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = seed_value + 404
	var w := size.x
	var h := size.y
	var edges := [[Vector2(0, 0), Vector2(w, 0), Vector2(0, -1)], [Vector2(w, 0), Vector2(w, h), Vector2(1, 0)],
		[Vector2(w, h), Vector2(0, h), Vector2(0, 1)]]
	_paper = PackedVector2Array()
	_fringe = PackedVector2Array()
	for e: Array in edges:
		var a: Vector2 = e[0]
		var b: Vector2 = e[1]
		var out: Vector2 = e[2]
		var n := maxi(int(a.distance_to(b) / 3.2), 2)
		var walk := 0.0
		for i in n:
			var t := float(i) / n
			walk = clampf(walk * 0.55 + rng.randf_range(-1.0, 1.0) * 1.1, -1.4, 1.4)
			if rng.randf() < 0.07:
				walk -= 1.6   # a small bite out of the edge
			var p := a.lerp(b, t)
			_paper.append(p + out * walk)
			_fringe.append(p + out * (walk + 0.9 + rng.randf() * 1.1))
	# the bottom-left corner, then the straight cut edge closes the outline back up to the first point
	_paper.append(Vector2(0, h))
	_fringe.append(Vector2(0, h + 1.2))


func _draw() -> void:
	if _paper.size() < 3:
		return
	# UV.x = ruling, UV.y = fibre (paper.gdshader): shadows pass through, the fringe is fibre only
	var flat := _uv(_fringe.size(), Vector2(0, 0))
	draw_polygon(_shifted(_fringe, Vector2(2.6, 4.0)), PackedColorArray([Color(UITheme.INK_SHADOW, 0.13)]), flat)
	draw_polygon(_shifted(_fringe, Vector2(1.2, 1.8)), PackedColorArray([Color(UITheme.INK_SHADOW, 0.2)]), flat)
	draw_polygon(_fringe, PackedColorArray([Color(1, 1, 1, 0.96)]), _uv(_fringe.size(), Vector2(0, 1)))
	draw_polygon(_paper, PackedColorArray([UITheme.PAPER]), _uv(_paper.size(), Vector2(1, 1)))


## Red pen: the old line struck through, then the new one underlined.
func _draw_ink() -> void:
	var xh := UITheme.pen.get_ascent(SIZE) * 0.42
	var olds: Array = []
	var news: Array = []
	for r: Dictionary in _rows:
		(olds if r.old else news).append(r)
	_pen_rows(olds, _strike, func(r: Dictionary, i: int) -> PackedVector2Array:
		return _stroke(Vector2(TEXT_X - 5.0, r.y - xh), Vector2(TEXT_X + r.w + 6.0, r.y - xh * 1.15), 0.9, i))
	_pen_rows(news, _under, func(r: Dictionary, i: int) -> PackedVector2Array:
		var pts := _stroke(Vector2(TEXT_X - 3.0, r.y + 6.0), Vector2(TEXT_X + r.w + 8.0, r.y + 4.0), 0.7, i + 5)
		pts.append(pts[pts.size() - 1] + Vector2(4.0, -3.5))
		return pts)


func _pen_rows(rows: Array, progress: float, path: Callable) -> void:
	if rows.is_empty() or progress <= 0.0:
		return
	var lines: Array = []
	for i in rows.size():
		lines.append(path.call(rows[i], i))
	for pts: PackedVector2Array in Doodles._clip(lines, progress):
		_ink.draw_polyline(pts, Color(UITheme.INK_RED, 0.92), 2.1, true)


## A quick pen line from a to b with a slight wave, the same for the same row every time.
func _stroke(a: Vector2, b: Vector2, wave: float, k: int) -> PackedVector2Array:
	var pts := PackedVector2Array()
	var ph := float(k) * 1.7 + float(hash(current) & 0xFF) * 0.05
	var steps := maxi(int(a.distance_to(b) / 6.0), 4)
	for i in steps + 1:
		var t := float(i) / steps
		pts.append(a.lerp(b, t) + Vector2(0, wave * sin(t * 6.0 + ph) + 0.5 * wave * sin(t * 13.0 + ph * 2.0)))
	return pts


static func _shifted(pts: PackedVector2Array, d: Vector2) -> PackedVector2Array:
	var out := pts.duplicate()
	for i in out.size():
		out[i] += d
	return out


static func _uv(n: int, v: Vector2) -> PackedVector2Array:
	var out := PackedVector2Array()
	out.resize(n)
	out.fill(v)
	return out
