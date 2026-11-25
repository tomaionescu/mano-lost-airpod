extends Node
## Joaquin's kebab orders (chapter 4, V2-26, docs/DESIGN.md §3.10): Mano is "the memory". Three rounds from data/kebab.json:
## a ticket comes up with a friend's name in their colour and their order (base, sauce, extra) for about 2.5 s, turns
## over, and Mano rebuilds the asked parts from the menu (round one: the three of them, every part; round two: the
## steps, sauce and extra); in round three the cook reads all eight tickets back with a sauce each, some of them wrong,
## and Mano says right or wrong. Nothing fails: every wrong order goes into flags.kebab_wrong and comes back as a joke
## on the steps (chapter 5); a wrong sauce of the cook's that Mano let through also goes into flags.kebab_misread (the
## jokes that name that sauce). After two tickets wrong in a row, Cristina (the witness) pencils a line under the right
## word on the next one. A paper ticket and the menu in Mano's marker, the chosen word circled in red pen; about 90 s.
## Ends with _done.call(true) (the story autotest calls that at once).

const DATA := "res://data/kebab.json"
const RESULT_T := 1.0          # a rebuilt ticket shows what was right for this long
const INTRO_T := 1.9
const HELP_AFTER := 2          # tickets wrong in a row before Cristina helps

var game
var _done: Callable
var data := {}
var rounds: Array = []
var _r := 0                    # round
var _k := 0                    # ticket in the round
var phase := "intro"           # intro, show, build, readback, result, over
var _t := 0.0
var _field := 0                # the field being rebuilt (index into the round's fields)
var _sel := 0                  # the option circled
var _picked := {}              # field -> option picked
var _rb_cook := ""             # the sauce the cook reads back (readback round)
var _rb_answer := -1           # 0 right, 1 wrong
var score := 0
var total := 0
var wrong := {}                # friend id -> true
var misread := {}              # friend id -> true: the cook's wrong sauce went into the bag (readback)
var wrong_streak := 0
var helped := 0                # tickets Cristina helped with (autotests read it)
var _help := false
var log_lines: Array = []

var _layer: CanvasLayer
var _root: Control
var _title: Label
var _intro: Label
var _ticket: PaperSheet
var _t_name: Label
var _t_lines: Label
var _t_bar: ColorRect
var _menu_head: Label
var _menu: HBoxContainer
var _keys: HBoxContainer
var _pencil: Label
var _progress: Label
var _loop: PenStyle
var _no_box := StyleBoxEmpty.new()


func setup(g, _opts: Dictionary, done: Callable) -> void:
	game = g
	_done = done
	data = _read(DATA)
	rounds = data.get("rounds", [])
	Sfx.music("", -60.0, 0.5, 1.5)
	_build_ui()
	_start_round()


static func _read(path: String) -> Dictionary:
	if not FileAccess.file_exists(path):
		return {}
	var j = JSON.parse_string(FileAccess.get_file_as_string(path))
	return j if j is Dictionary else {}


func order_of(id: String) -> Dictionary:
	return data.get("orders", {}).get(id, {})


func options(field: String) -> Array:
	return data.get({"base": "bases", "sauce": "sauces", "extra": "extras"}[field], [])


func _round() -> Dictionary:
	return rounds[_r] if _r < rounds.size() else {}


func _who() -> String:
	var w: Array = _round().get("who", [])
	return String(w[_k]) if _k < w.size() else ""


func _fields() -> Array:
	return _round().get("fields", ["sauce"])


# ------------------------------------------------------------------ the page
func _build_ui() -> void:
	_layer = CanvasLayer.new()
	_layer.layer = 15
	add_child(_layer)
	_root = Control.new()
	_root.set_anchors_preset(Control.PRESET_FULL_RECT)
	_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_root.theme = UITheme.theme
	_layer.add_child(_root)
	# the counter at night: a warm dark room, one lamp over it
	var room := ColorRect.new()
	room.color = Color("#160f0b")
	room.set_anchors_preset(Control.PRESET_FULL_RECT)
	room.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_root.add_child(room)
	var lamp := TextureRect.new()
	lamp.texture = Menus._radial_tex(Color(1.0, 0.72, 0.42, 0.26), Color(0, 0, 0, 0), Vector2(0.5, 0.35))
	lamp.set_anchors_preset(Control.PRESET_FULL_RECT)
	lamp.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	lamp.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_root.add_child(lamp)
	_title = UITheme.over_scene(UITheme.label("Joaquin's orders", 52, UITheme.marker_title, UITheme.FILM_WHITE), 6, 0.5) as Label
	_title.set_anchors_preset(Control.PRESET_CENTER_TOP)
	_title.grow_horizontal = Control.GROW_DIRECTION_BOTH
	_title.offset_top = 40
	_root.add_child(_title)
	_intro = UITheme.over_scene(UITheme.label("", 32, UITheme.pen, UITheme.FILM_WHITE), 6, 0.5) as Label
	_intro.set_anchors_preset(Control.PRESET_CENTER_TOP)
	_intro.grow_horizontal = Control.GROW_DIRECTION_BOTH
	_intro.offset_top = 112
	_root.add_child(_intro)
	# the ticket: a slip torn off a pad, the friend's name in their colour, the order in pen
	_ticket = PaperSheet.new()
	_ticket.ruling = PaperSheet.Ruling.PLAIN
	_ticket.margin_x = -1.0
	_ticket.edges = [PaperSheet.Edge.TORN, PaperSheet.Edge.CUT, PaperSheet.Edge.CUT, PaperSheet.Edge.CUT]
	_ticket.seed_value = 42
	_ticket.size = Vector2(430, 300)   # wide enough for "andalouse  (algérienne)"
	_ticket.pivot_offset = _ticket.size * 0.5
	_ticket.rotation_degrees = -2.0
	Menus._pin(_ticket, Vector2(0.5, 0.5), Vector2(-620, -170), _ticket.size)
	_root.add_child(_ticket)
	_t_name = UITheme.label("", 44, UITheme.marker_title, UITheme.INK_BLACK)
	_t_name.position = Vector2(28, 26)
	_ticket.add_child(_t_name)
	_t_lines = UITheme.label("", 34, UITheme.pen, UITheme.INK_BLUE)
	_t_lines.position = Vector2(30, 96)
	_t_lines.add_theme_constant_override("line_spacing", 6)
	_ticket.add_child(_t_lines)
	_t_bar = ColorRect.new()
	_t_bar.color = Color(UITheme.MARKER_RED, 0.8)
	_t_bar.position = Vector2(28, 262)
	_t_bar.size = Vector2(374, 4)
	_ticket.add_child(_t_bar)
	# the menu: the part being rebuilt, its words in marker, one circled
	_menu_head = UITheme.over_scene(UITheme.label("", 34, UITheme.marker, UITheme.FILM_WHITE), 6, 0.5) as Label
	Menus._pin(_menu_head, Vector2(0.5, 0.5), Vector2(-120, -170), Vector2(700, 50))
	_root.add_child(_menu_head)
	_menu = HBoxContainer.new()
	_menu.add_theme_constant_override("separation", 6)
	_menu.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_root.add_child(_menu)
	_loop = PenStyle.make(PenStyle.Kind.LOOP, UITheme.MARKER_RED, 2.6, 7)
	for sb: StyleBox in [_loop, _no_box]:
		sb.content_margin_left = 14
		sb.content_margin_right = 14
		sb.content_margin_top = 6
		sb.content_margin_bottom = 8
	_progress = UITheme.over_scene(UITheme.label("", 24, UITheme.pen, UITheme.MUTED), 5, 0.45) as Label
	_progress.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	_progress.grow_horizontal = Control.GROW_DIRECTION_BOTH
	_progress.offset_top = -120
	_progress.offset_bottom = -90
	_root.add_child(_progress)
	_keys = HBoxContainer.new()
	_keys.add_theme_constant_override("separation", 10)
	_keys.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_keys.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	_keys.grow_horizontal = Control.GROW_DIRECTION_BOTH
	_keys.grow_vertical = Control.GROW_DIRECTION_BEGIN
	_keys.offset_bottom = -44
	for k in [UITheme.action_key("move_left"), UITheme.action_key("move_right")]:
		_keys.add_child(UITheme.key_cap(k, 18))
	_keys.add_child(UITheme.over_scene(UITheme.label("choose    ", 24, UITheme.print_500, UITheme.FILM_WHITE), 5, 0.45))
	_keys.add_child(UITheme.key_cap(UITheme.action_key("confirm"), 18))
	_keys.add_child(UITheme.over_scene(UITheme.label("pick", 24, UITheme.print_500, UITheme.FILM_WHITE), 5, 0.45))
	_keys.visible = false
	_root.add_child(_keys)
	# Cristina's help, said in pencil under the menu (the line under the word alone was easy to miss)
	_pencil = UITheme.over_scene(UITheme.label("", 28, UITheme.pen, Color("#d9d4c7")), 5, 0.45) as Label
	Menus._pin(_pencil, Vector2(0.5, 0.5), Vector2(-120, -10), Vector2(700, 40))
	_root.add_child(_pencil)
	_root.modulate.a = 0.0
	_root.create_tween().tween_property(_root, "modulate:a", 1.0, 0.35)


func _set_menu(words: Array, hint := -1) -> void:
	for c in _menu.get_children():
		_menu.remove_child(c)
		c.queue_free()
	_pencil.text = "Cristina underlined one. She was watching." if hint >= 0 else ""
	for i in words.size():
		var b := Button.new()
		b.text = String(words[i])
		b.focus_mode = Control.FOCUS_NONE
		b.add_theme_font_override("font", UITheme.marker_calm)
		b.add_theme_font_size_override("font_size", 32)
		b.add_theme_color_override("font_color", UITheme.FILM_WHITE)
		b.add_theme_color_override("font_hover_color", UITheme.FILM_WHITE)
		b.add_theme_constant_override("outline_size", 6)
		b.add_theme_color_override("font_outline_color", Color(UITheme.INK_SHADOW, 0.85))
		b.mouse_entered.connect(func(): _mark(i))
		b.pressed.connect(func():
			_mark(i)
			_pick())
		if i == hint:
			# Cristina, the witness: a pencil line under the right word
			b.draw.connect(func(): b.draw_line(Vector2(14, b.size.y - 4), Vector2(b.size.x - 14, b.size.y - 5), Color("#d9d4c7"), 3.2, true))
		_menu.add_child(b)
	# centred under its heading, at the right of the ticket
	var w := _menu.get_combined_minimum_size()
	Menus._pin(_menu, Vector2(0.5, 0.5), Vector2(-120, -100), Vector2(maxf(w.x, 10.0), w.y))
	_mark(clampi(_sel, 0, words.size() - 1))


func _mark(i: int) -> void:
	_sel = i
	for j in _menu.get_child_count():
		var b := _menu.get_child(j) as Button
		var st: StyleBox = _loop if j == i else _no_box
		for s in ["normal", "hover", "pressed", "hover_pressed", "focus"]:
			b.add_theme_stylebox_override(s, st)
	_loop.progress = 0.0
	create_tween().tween_property(_loop, "progress", 1.0, 0.14)


# ------------------------------------------------------------------ flow
func _start_round() -> void:
	if _r >= rounds.size():
		_finish()
		return
	_k = 0
	phase = "intro"
	_t = 0.0
	_intro.text = String(_round().get("intro", ""))
	_ticket.visible = false
	_menu_head.text = ""
	_set_menu([])
	_progress.text = "Round %d of %d" % [_r + 1, rounds.size()]
	_keys.visible = false


func _next_ticket() -> void:
	var w: Array = _round().get("who", [])
	if _k >= w.size():
		_r += 1
		_start_round()
		return
	var id := _who()
	var info: Dictionary = game._speaker_info(id) if game else {"name": id.capitalize(), "color": UITheme.INK_BLACK}
	_ticket.visible = true
	_t_name.text = String(info.get("name", id))
	_t_name.add_theme_color_override("font_color", _paper_ink(info.get("color", UITheme.INK_BLACK)))
	_picked = {}
	_field = 0
	_help = wrong_streak >= HELP_AFTER
	Sfx.play("kebab_bell", -8.0)
	_progress.text = "Round %d of %d, ticket %d of %d" % [_r + 1, rounds.size(), _k + 1, w.size()]
	_t = 0.0
	if bool(_round().get("readback", false)):
		var o := order_of(id)
		_rb_cook = String(_round().get("cook", {}).get(id, o.get("sauce", "")))
		_rb_answer = -1
		phase = "readback"
		# the sauce line stays blank: ink on the ticket is the true order, and the cook's sauce is only his claim
		_t_lines.text = "%s\n..........\n%s" % [o.get("base", ""), o.get("extra", "")]
		_t_lines.add_theme_color_override("font_color", UITheme.INK_BLUE)
		_menu_head.text = "The cook says %s. Right?" % _rb_cook
		var hint := -1
		if _help:
			hint = 0 if _rb_cook == String(o.get("sauce", "")) else 1
		_sel = 0
		_set_menu(["right", "wrong"], hint)
		_keys.visible = true
		if id in _round().get("new", []):
			# one nobody has shown him yet: Toma's message says it, just before the cook does
			_intro.text = "Toma's message: %s, %s, %s, %s." % [_t_name.text, o.get("base", ""), o.get("sauce", ""), o.get("extra", "")]
		else:
			_intro.text = ""
		return
	phase = "show"
	var o := order_of(id)
	_t_lines.text = "%s\n%s\n%s" % [o.get("base", ""), o.get("sauce", ""), o.get("extra", "")]
	_t_lines.add_theme_color_override("font_color", UITheme.INK_BLUE)
	_menu_head.text = "Remember it."
	_set_menu([])
	_keys.visible = false


## A subtitle colour made dark enough to read on paper (the friends' paper inks, docs/DESIGN.md §5.2, roughly).
static func _paper_ink(c: Color) -> Color:
	return Color.from_hsv(c.h, minf(c.s * 1.25, 1.0), clampf(c.v * 0.55, 0.25, 0.6))


func _begin_build() -> void:
	phase = "build"
	_field = 0
	_show_build()


func _show_build() -> void:
	var fields := _fields()
	var f := String(fields[_field])
	var o := order_of(_who())
	# the ticket shows what is rebuilt so far; the rest is blank lines
	var lines: Array = []
	for part in ["base", "sauce", "extra"]:
		if part in fields:
			lines.append(String(_picked.get(part, "..........")))
		else:
			lines.append(String(o.get(part, "")))
	_t_lines.text = "\n".join(lines)
	_menu_head.text = {"base": "Which base?", "sauce": "Which sauce?", "extra": "And with it?"}[f]
	var opts := options(f)
	var hint := opts.find(String(o.get(f, ""))) if _help else -1
	_sel = 0
	_set_menu(opts, hint)
	_keys.visible = true


func _pick() -> void:
	if phase == "readback":
		_rb_answer = _sel
		var o := order_of(_who())
		var cook_right := _rb_cook == String(o.get("sauce", ""))
		var ok := (_rb_answer == 0) == cook_right
		total += 1
		score += 1 if ok else 0
		if not ok:
			wrong[_who()] = true
			if not cook_right:
				misread[_who()] = true
		_t_lines.text = "%s\n%s%s\n%s" % [o.get("base", ""), o.get("sauce", ""), "" if cook_right else "  (not " + _rb_cook + ")", o.get("extra", "")]
		_end_ticket(ok)
		return
	if phase != "build":
		return
	var fields := _fields()
	var f := String(fields[_field])
	_picked[f] = options(f)[_sel]
	Sfx.ui("ui_click", -6.0)
	_field += 1
	if _field < fields.size():
		_show_build()
		return
	# the ticket is rebuilt: what was right
	var o := order_of(_who())
	var all_ok := true
	var shown: Array = []
	for part in ["base", "sauce", "extra"]:
		if part in fields:
			total += 1
			var ok := String(_picked[part]) == String(o.get(part, ""))
			score += 1 if ok else 0
			all_ok = all_ok and ok
			shown.append(String(_picked[part]) if ok else "%s  (%s)" % [_picked[part], o.get(part, "")])
		else:
			shown.append(String(o.get(part, "")))
	if not all_ok:
		wrong[_who()] = true
	_t_lines.text = "\n".join(shown)
	_end_ticket(all_ok)


func _end_ticket(ok: bool) -> void:
	phase = "result"
	_t = 0.0
	if _help:
		helped += 1
	wrong_streak = 0 if ok else wrong_streak + 1
	_t_lines.add_theme_color_override("font_color", UITheme.INK_GREEN if ok else UITheme.INK_RED)
	_menu_head.text = ["Perfect.", "Joaquin nods.", "Cristina saw nothing."][randi() % 3] if ok else ["Close enough. It's going in the bag.", "That's a surprise for later.", "Joaquin writes something down."][randi() % 3]
	_set_menu([])
	_keys.visible = false
	if ok:
		Sfx.play("objective", -8.0)
	else:
		Sfx.ui("ui_back", -4.0)
	log_lines.append("%s: %s%s" % [_who(), "right" if ok else "wrong", " (Cristina helped)" if _help else ""])
	print("[kebab] round %d ticket %d %s: %s%s" % [_r + 1, _k + 1, _who(), "right" if ok else "wrong", " (Cristina's pencil line)" if _help else ""])


func _process(dt: float) -> void:
	if phase == "over":
		return
	_t += dt
	match phase:
		"intro":
			if _t >= INTRO_T:
				_intro.text = ""
				_next_ticket()
		"show":
			var show := float(_round().get("show", 2.5))
			_t_bar.size.x = 374.0 * clampf(1.0 - _t / show, 0.0, 1.0)
			if _t >= show:
				_t_bar.size.x = 0.0
				_begin_build()
		"result":
			if _t >= RESULT_T:
				_k += 1
				_next_ticket()


func _unhandled_input(event: InputEvent) -> void:
	if phase in ["build", "readback"]:
		var n := _menu.get_child_count()
		if n == 0:
			return
		if event.is_action_pressed("move_left") or event.is_action_pressed("ui_left"):
			_mark((_sel + n - 1) % n)
			Sfx.ui("ui_hover", -14.0)
		elif event.is_action_pressed("move_right") or event.is_action_pressed("ui_right"):
			_mark((_sel + 1) % n)
			Sfx.ui("ui_hover", -14.0)
		elif event.is_action_pressed("confirm"):
			_pick()
		elif event is InputEventKey and event.pressed and not event.echo and event.physical_keycode >= KEY_1 and event.physical_keycode <= KEY_9 \
				and event.physical_keycode - KEY_1 < n:
			_mark(event.physical_keycode - KEY_1)
			_pick()
		else:
			return
		get_viewport().set_input_as_handled()
	elif phase == "show" and event.is_action_pressed("confirm") and _t > 0.6:
		# remembered already: on to the rebuilding
		get_viewport().set_input_as_handled()
		_begin_build()


func _finish() -> void:
	phase = "over"
	GameState.flags["kebab_score"] = score
	GameState.flags["kebab_total"] = total
	GameState.flags["kebab_wrong"] = wrong.keys()
	GameState.flags["kebab_misread"] = misread.keys()
	_ticket.visible = false
	_menu_head.text = ""
	_set_menu([])
	_intro.text = "%d of %d right. Eight kebabs in one bag." % [score, total]
	_keys.visible = false
	print("[kebab] done: %d of %d right, wrong orders %s (the cook's sauce let through: %s), Cristina helped on %d tickets" % [score, total, wrong.keys(), misread.keys(), helped])
	var tw := create_tween()
	tw.tween_interval(1.6)
	tw.tween_callback(func(): _done.call(true))
