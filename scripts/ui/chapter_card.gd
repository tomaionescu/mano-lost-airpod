class_name ChapterCard
extends Control
## The chapter card (docs/DESIGN.md §5.5, docs/ART_DIRECTION.md): a fresh page of Mano's Seyès notebook over the
## black. The date writes itself top-right and gets ruled under in red, the time goes on in marker, the place in
## pen (and a chapter's number, circled, with its name); the page holds, then slides away like a turned page
## into the scene coming up behind it. About 3.6 s in all. HUD.title_card() makes one.

signal gone

const DATE_T := 0.9       # the date writes on
const RULE_T := 0.2       # the red ruler line under it
const TIME_T := 0.7       # the time, in marker
const HOLD := 1.4
const OUT_T := 0.45
const DATE_SIZE := 37     # Mynerve, 44 px at 1080p
const TIME_SIZE := 107    # Shantell 800, 128 px at 1080p
const PLACE_SIZE := 37
const CHAPTER_SIZE := 40

var time_text := "17:42"
var place := "Amphi 4"
var date := "jeudi 15 octobre"
## "2 Lost & Found": the leading number is circled in pen, the name follows in marker. Empty: no chapter line.
var chapter := ""
var hold := HOLD

var _page: PaperSheet
var _ink: Control
var _date: Label
var _rule := 0.0
var _circle: PenStyle = null
var _chapter_num: Label = null


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_preset(Control.PRESET_FULL_RECT)
	var vp := get_parent_area_size()
	if vp.x < 10.0:
		vp = Vector2(1600, 900)
	# a big page seen close up: the ruling scales with the screen so the card reads the same on any window
	_page = PaperSheet.new()
	var ps := Vector2(minf(vp.x - 120.0, vp.y * 1.62), vp.y - 70.0)
	_page.size = ps
	_page.position = (vp - ps) * 0.5 + Vector2(0, 6)
	_page.pivot_offset = ps * 0.5
	_page.rotation_degrees = -0.7
	_page.row = roundf(ps.y / 15.5)
	_page.first_line = _page.row * 1.6
	_page.margin_x = roundf(ps.x * 0.12)
	_page.seed_value = hash(time_text + place) & 0xFFF
	_page.lift = 1.6
	add_child(_page)
	var row := _page.row
	var right := ps.x - row * 1.6
	_date = _line(date, DATE_SIZE, UITheme.pen, UITheme.INK_BLUE, Vector2(right, _page.line_y(1)), true)
	var top_line := 4
	if chapter != "":
		var num := chapter.get_slice(" ", 0)
		var name := chapter.substr(num.length()).strip_edges()
		_chapter_num = _line(num, CHAPTER_SIZE, UITheme.marker, UITheme.INK_RED, Vector2(_page.margin_x + row * 0.9, _page.line_y(3)), false)
		_circle = Ink.paper_loop(5, Vector2(10, 2))
		_circle.color = UITheme.INK_RED
		_circle.progress = 0.0
		_chapter_num.add_theme_stylebox_override("normal", _circle)
		_line(name, CHAPTER_SIZE, UITheme.marker, UITheme.INK_BLACK, Vector2(_page.margin_x + row * 2.2, _page.line_y(3)), false)
		top_line = 5
	_line(time_text, TIME_SIZE, UITheme.marker_title, UITheme.INK_BLACK, Vector2(_page.margin_x + row * 0.9, _page.line_y(top_line + 2)), false)
	_line(place, PLACE_SIZE, UITheme.pen, UITheme.INK_BLUE, Vector2(_page.margin_x + row * 1.0, _page.line_y(top_line + 4)), false)
	_ink = Control.new()
	_ink.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_ink.size = ps
	_ink.draw.connect(_draw_ink)
	_page.add_child(_ink)
	_play.call_deferred()


## A one-line label in the page's units, its baseline on `at.y`; `right_align` ends it at `at.x`.
func _line(text: String, size: int, font: Font, color: Color, at: Vector2, right_align: bool) -> Label:
	var l := UITheme.label(text, size, font, color)
	l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var w := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, size).x
	l.position = Vector2(at.x - (w if right_align else 0.0), at.y - font.get_ascent(size))
	l.modulate.a = 0.0
	_page.add_child(l)
	return l


## The timeline: the page comes up (0.25 s), the date writes (0.9 s) and is ruled in red (0.2 s), the
## time writes in marker (0.7 s) with the place close behind it, the page holds and then turns away: it starts
## leaving at about 3.2 s, as main._opening() fades the wake-up in behind it, and is gone at about 3.6 s.
func _play() -> void:
	var calm := Ink.calm()
	var labels: Array[Label] = []
	for c in _page.get_children():
		if c is Label:
			labels.append(c)
	# the page comes up from just below, then everything is written on in order
	_page.modulate.a = 0.0
	var tw := create_tween()
	tw.tween_property(_page, "modulate:a", 1.0, 0.18)
	if not calm:
		_page.position.y += 40.0
		tw.parallel().tween_property(_page, "position:y", _page.position.y - 40.0, 0.3).set_trans(Tween.TRANS_QUART).set_ease(Tween.EASE_OUT)
	Sfx.ui("journal_open", -10.0)
	var t := 0.25
	var written := t
	for l in labels:
		l.modulate.a = 1.0
		if l == _date:
			Ink.write_on(l, DATE_T, t)
			t += DATE_T
			_tween_rule(t - 0.05, calm)
			t += RULE_T * 0.5
		elif l == _chapter_num and _circle:
			Ink.write_on(l, 0.2, t)
			t += 0.25
			if calm:
				_circle.progress = 1.0
			else:
				get_tree().create_timer(t, false).timeout.connect(func(): Ink.draw_on(self, _circle, 0.2))
			t += 0.15
		elif l.text == time_text:
			Ink.write_on(l, TIME_T, t)
			t += TIME_T - 0.1   # the place starts as the last digit dries
		else:
			var secs := clampf(l.text.length() / Ink.CPS, 0.2, 0.9)
			Ink.write_on(l, secs, t)
			t += secs + 0.05
		written = t
	var leave := maxf(written + 0.6, 0.25 + DATE_T + TIME_T + hold - 0.1)
	get_tree().create_timer(leave, false).timeout.connect(_leave)


func _tween_rule(delay: float, calm: bool) -> void:
	if calm:
		_rule = 1.0
		_ink.queue_redraw()
		return
	var tw := create_tween()
	tw.tween_interval(delay)
	tw.tween_method(func(v: float):
		_rule = v
		_ink.queue_redraw(), 0.0, 1.0, RULE_T).set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)


## The red line ruled under the date.
func _draw_ink() -> void:
	if _date == null or _rule <= 0.0:
		return
	var f: Font = UITheme.pen
	var w := f.get_string_size(date, HORIZONTAL_ALIGNMENT_LEFT, -1, DATE_SIZE).x
	var y := _date.position.y + f.get_ascent(DATE_SIZE) + 9.0
	Ink.ruler_line(_ink, Vector2(_date.position.x - 8.0, y), Vector2(_date.position.x + w + 10.0, y - 0.6), Color(UITheme.INK_RED, 0.92), 2.2, _rule)


## The page is turned away to the left, showing the scene behind it.
func _leave() -> void:
	var tw := create_tween().set_parallel()
	if Ink.calm():
		tw.tween_property(_page, "modulate:a", 0.0, 0.15)
	else:
		tw.tween_property(_page, "position:x", _page.position.x - _page.size.x * 1.15, OUT_T).set_trans(Tween.TRANS_QUART).set_ease(Tween.EASE_IN)
		tw.tween_property(_page, "rotation_degrees", -7.0, OUT_T).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_IN)
	Sfx.ui("journal_close", -12.0)
	tw.chain().tween_callback(func():
		gone.emit()
		queue_free())
