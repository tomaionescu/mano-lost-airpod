extends Node
## Anisha's code is failing the moulinette: point at the buggy line, three rounds against the clock, in an i3-style
## tiled terminal (square corners, no traffic lights: the lab machines run NixOS with i3, docs/DESIGN.md §3.10).
## The night variant (chapter 4, opts.night, V2-26): Anisha's last exercise at 23:05; its middle round is the coding style (a `goto`, a cast on malloc,
## five arguments); a miss costs 4 s (6 by day); after 12 s on a round Anisha gives a hint; when a run times out it
## starts again, and after two failed runs Anisha takes the keyboard. The night always ends OK.

const SNIPS := [
	{"file": "my_strlen.c", "bug": [5], "why": "Off-by-one: it returns the length + 1.", "code": [
		"int my_strlen(const char *s)", "{", "    int i = 0;", "    while (s[i] != '\\0')", "        i++;", "    return i + 1;", "}"]},
	{"file": "swap.c", "bug": [0], "why": "It swaps copies, not the caller's ints. It needs pointers.", "code": [
		"void swap(int a, int b)", "{", "    int tmp = a;", "    a = b;", "    b = tmp;", "}"]},
	{"file": "my_strdup.c", "bug": [2], "why": "No room for the '\\0'. It needs strlen(s) + 1.", "code": [
		"char *my_strdup(const char *s)", "{", "    char *d = malloc(strlen(s));", "    if (d == NULL)", "        return NULL;", "    strcpy(d, s);", "    return d;", "}"]},
	{"file": "sum.c", "bug": [3], "why": "i <= n reads one element past the end of the array.", "code": [
		"int sum(const int *arr, int n)", "{", "    int total = 0;", "    for (int i = 0; i <= n; i++)", "        total += arr[i];", "    return total;", "}"]},
	{"file": "greet.c", "bug": [4], "why": "It returns a pointer to a local array. Dangling as soon as the function returns.", "code": [
		"char *greet(void)", "{", "    char buf[32];", "    strcpy(buf, \"salut\");", "    return buf;", "}"]},
	{"file": "free_list.c", "bug": [4, 5], "why": "Use after free: l->next is read after free(l).", "code": [
		"void free_list(struct node *l)", "{", "    while (l != NULL)", "    {", "        free(l);", "        l = l->next;", "    }", "}"]},
	{"file": "is_even.c", "bug": [2], "why": "= is an assignment. It should be ==. (It does not even compile.)", "code": [
		"int is_even(int n)", "{", "    if (n % 2 = 0)", "        return 1;", "    return 0;", "}"]},
	{"file": "my_putstr.c", "bug": [3], "why": "The loop never advances: s is never incremented, so it prints forever.", "code": [
		"void my_putstr(const char *s)", "{", "    while (*s != '\\0')", "        write(1, s, 1);", "}"]},
]
## The coding-style round of the night variant (EPITA's coding style).
const STYLE := [
	{"file": "my_strndup.c", "bug": [2], "why": "Coding style: no cast on malloc's return.", "hint": "The cast. Look at the cast.", "code": [
		"char *my_strndup(const char *s, int n)", "{", "    char *d = (char *)malloc(n + 1);", "    if (d == NULL)", "        return NULL;", "    d[n] = '\\0';", "    return my_strncpy(d, s, n);", "}"]},
	{"file": "parse.c", "bug": [4], "why": "Coding style: goto is forbidden. Even at 23:05.", "hint": "One word in there is illegal. Literally.", "code": [
		"int parse(const char *s)", "{", "    if (s == NULL)", "        return -1;", "    goto end;", "    return count(s);", "end:", "    return 0;", "}"]},
	{"file": "draw.c", "bug": [0], "why": "Coding style: four arguments at most. That's five.", "hint": "Count the arguments.", "code": [
		"void draw(int x, int y, int w, int h, int c)", "{", "    for (int i = 0; i < h; i++)", "        line(x, y + i, w, c);", "}"]},
]
## Hints for the bug rounds of the night (Anisha, after 12 s on a round).
const HINTS := {"my_strlen.c": "What does it return? Exactly?", "swap.c": "Whose ints is it swapping?",
	"my_strdup.c": "Room for the end of the string?", "sum.c": "Count the loop. One too many?", "greet.c": "Where does buf live?",
	"free_list.c": "Free, then read it?", "is_even.c": "One equals sign is not a question.", "my_putstr.c": "Does s ever move?"}
const ROUND_TIME := 30.0
const HINT_AT := 12.0          # night: Anisha's hint after this long on a round
const MISS_DAY := 6.0
const MISS_NIGHT := 4.0

var game
var _done: Callable
var _rounds: Array = []
var _r := 0
var _sel := 0
var _time := ROUND_TIME
var _ok := 0.0
var _flash := 0.0
var _wrong := -1
var _over := false
var night := false
var runs_failed := 0           # night: runs that timed out (two, and Anisha takes the keyboard)
var anisha_typing := false
var _round_time := ROUND_TIME
var _on_round := 0.0           # seconds on this round (the hint)
var _hinted := false
var _auto := -1.0

var _layer: CanvasLayer
var _title: Label
var _status: Label
var _lines: VBoxContainer
var _foot: Label
var _bar: ColorRect
var _bar_bg: ColorRect


func setup(g, opts: Dictionary, done: Callable) -> void:
	game = g
	_done = done
	night = str(opts.get("night", false)).to_lower() == "true"   # `night=true` in a .dlg arrives as a bool
	_round_time = float(opts.get("round_time", ROUND_TIME))
	_time = _round_time
	var pool := SNIPS.duplicate()
	pool.shuffle()
	_rounds = pool.slice(0, 3)
	if night:
		var style := STYLE.duplicate()
		style.shuffle()
		_rounds = [pool[0], style[0], pool[1]]
	# over-the-shoulder view of Mano at the PC
	var a: Dictionary = game.binder.anchors.get(opts.get("sit_at", "pcSeat"), {})
	if not a.is_empty():
		var ex: Dictionary = a.extras
		var from: Vector3 = _vec(ex.get("cam_from"), a.pos + Vector3(0.95, 1.75, 1.8))
		var look: Vector3 = _vec(ex.get("cam_look"), a.pos + Vector3(0, 1.05, -0.2))
		game.camera_rig.set_shot(from, look, 34.0, from.distance_to(look))
	_build_ui()
	_render()


static func _vec(v, fallback: Vector3) -> Vector3:
	if v is Array and v.size() == 3:
		return Vector3(v[0], v[1], v[2])
	return fallback


func _build_ui() -> void:
	_layer = CanvasLayer.new()
	_layer.layer = 15
	add_child(_layer)
	var root := Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.theme = UITheme.theme
	_layer.add_child(root)
	var win := PanelContainer.new()
	# an i3-style tiled terminal, by day too: square corners, the focused window's blue border, no traffic lights
	var sb := UITheme.box(Color("#0d1117f2"), 0, Color("#285577"), 0)
	sb.set_border_width_all(2)
	sb.content_margin_left = 0
	sb.content_margin_right = 0
	sb.content_margin_top = 0
	sb.content_margin_bottom = 0
	sb.shadow_color = Color(0, 0, 0, 0.5)
	sb.shadow_size = 30
	win.add_theme_stylebox_override("panel", sb)
	win.anchor_left = 0.5
	win.anchor_right = 0.5
	win.anchor_top = 0.5
	win.anchor_bottom = 0.5
	win.offset_left = -430
	win.offset_right = 430
	win.offset_top = -270
	win.offset_bottom = 270
	root.add_child(win)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 0)
	win.add_child(v)
	var bar := PanelContainer.new()
	bar.add_theme_stylebox_override("panel", UITheme.box(Color("#285577"), 0, Color(0, 0, 0, 0), 10))
	var bh := HBoxContainer.new()
	bh.add_theme_constant_override("separation", 8)
	_title = UITheme.label("", 15, UITheme.mono, Color("#ffffff"))
	_title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_title.horizontal_alignment = HORIZONTAL_ALIGNMENT_LEFT
	bh.add_child(_title)
	bar.add_child(bh)
	v.add_child(bar)
	var body := MarginContainer.new()
	for side in ["left", "right", "top", "bottom"]:
		body.add_theme_constant_override("margin_" + side, 22)
	var bv := VBoxContainer.new()
	bv.add_theme_constant_override("separation", 10)
	_status = UITheme.label("", 18, UITheme.mono, Color("#f85149"))
	bv.add_child(_status)
	_lines = VBoxContainer.new()
	_lines.add_theme_constant_override("separation", 2)
	_lines.custom_minimum_size = Vector2(0, 300)
	bv.add_child(_lines)
	_foot = UITheme.label("", 15, UITheme.mono, Color("#8b949e"))
	_foot.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	bv.add_child(_foot)
	_bar_bg = ColorRect.new()
	_bar_bg.color = Color(1, 1, 1, 0.08)
	_bar_bg.custom_minimum_size = Vector2(0, 6)
	_bar = ColorRect.new()
	_bar.color = Color("#2ea043")
	_bar.size = Vector2(800, 6)
	_bar_bg.add_child(_bar)
	bv.add_child(_bar_bg)
	body.add_child(bv)
	v.add_child(body)
	root.modulate.a = 0.0
	root.create_tween().tween_property(root, "modulate:a", 1.0, 0.35)


static func _highlight(line: String) -> String:
	var s := line.replace("[", "[lb]")
	var re := RegEx.new()
	re.compile("(\"[^\"]*\"|'[^']*')")
	s = re.sub(s, "[color=#a5d6ff]$1[/color]", true)
	var kw := RegEx.new()
	kw.compile("\\b(int|char|void|const|struct)\\b")
	s = kw.sub(s, "[color=#ff7b72]$1[/color]", true)
	var kw2 := RegEx.new()
	kw2.compile("\\b(return|while|for|if|NULL|free|malloc|strcpy|strlen|write)\\b")
	s = kw2.sub(s, "[color=#d2a8ff]$1[/color]", true)
	var num := RegEx.new()
	num.compile("\\b(\\d+)\\b")
	s = num.sub(s, "[color=#79c0ff]$1[/color]", true)
	return s


func _render() -> void:
	var s: Dictionary = _rounds[_r]
	_title.text = ("1:term  anisha@epita: ~/afs/piscine/ex05/%s" if night else "1:term  anisha@epita: ~/afs/piscine/day09/%s") % s.file
	if _ok > 0.0:
		_status.text = "MOULINETTE: OK"
		_status.add_theme_color_override("font_color", Color("#3fb950"))
		_foot.text = s.why + "\n(press E to continue)"
	else:
		var style := night and s.has("hint") and not HINTS.has(s.file)
		_status.text = "MOULINETTE: KO  -  test %d/3      %s" % [_r + 1, "find the line that breaks the coding style" if style else "find the line with the bug"]
		if night and runs_failed > 0:
			_status.text += "      run %d" % (runs_failed + 1)
		_status.add_theme_color_override("font_color", Color("#f85149"))
		_foot.text = "↑ ↓ / W S  pick a line      E / Space  submit      click works too"
		if anisha_typing:
			_foot.text = "Anisha: \"Move. My keyboard.\""
		elif night and _hinted:
			# the hint goes above the keys, which stay
			_foot.text = "Anisha: \"%s\"\n%s" % [String(s.get("hint", HINTS.get(s.file, ""))), _foot.text]
	for c in _lines.get_children():
		c.queue_free()
	var code: Array = s.code
	for i in code.size():
		var row := PanelContainer.new()
		var bg := Color(0, 0, 0, 0)
		if _ok > 0.0 and i in s.bug:
			bg = Color("#2ea04355")
		elif _flash > 0.0 and i == _wrong:
			bg = Color("#f8514955")
		elif i == _sel:
			bg = Color("#388bfd33")
		var sb := UITheme.box(bg, 6, Color("#388bfd") if i == _sel and _ok <= 0.0 else Color(0, 0, 0, 0), 4)
		sb.content_margin_left = 8
		row.add_theme_stylebox_override("panel", sb)
		var h := HBoxContainer.new()
		var n := UITheme.label(str(i + 1).lpad(2), 19, UITheme.mono, Color("#6e7681"))
		n.custom_minimum_size = Vector2(40, 0)
		h.add_child(n)
		var t := RichTextLabel.new()
		t.bbcode_enabled = true
		t.fit_content = true
		t.scroll_active = false
		t.autowrap_mode = TextServer.AUTOWRAP_OFF
		t.custom_minimum_size = Vector2(720, 0)
		t.add_theme_font_override("normal_font", UITheme.mono)
		t.add_theme_font_size_override("normal_font_size", 19)
		t.add_theme_color_override("default_color", Color("#e6edf3"))
		t.text = _highlight(code[i]) if code[i] != "" else " "
		t.mouse_filter = Control.MOUSE_FILTER_IGNORE
		h.add_child(t)
		row.add_child(h)
		row.gui_input.connect(func(ev):
			if ev is InputEventMouseButton and ev.pressed and ev.button_index == MOUSE_BUTTON_LEFT and _ok <= 0.0:
				_sel = i
				_submit())
		_lines.add_child(row)


func _submit() -> void:
	if _ok > 0.0 or _over:
		return
	var s: Dictionary = _rounds[_r]
	if _sel in s.bug:
		_ok = 2.4
		Sfx.play("objective", -2.0)
	else:
		var miss := MISS_NIGHT if night else MISS_DAY
		_time -= miss
		_flash = 0.6
		_wrong = _sel
		Sfx.ui("ui_back", 0.0)
		game.camera_rig.add_trauma(0.25)
		game.toast("-42  (-%d s)" % int(miss), "cross")
	_render()


func _process(dt: float) -> void:
	if _over:
		return
	var s: Dictionary = _rounds[_r]
	if _ok > 0.0:
		_ok -= dt
		if _ok <= 0.0:
			_next_round()
		return
	if _flash > 0.0:
		_flash -= dt
		if _flash <= 0.0:
			_render()
	_time -= dt
	_on_round += dt
	if night and not _hinted and _on_round >= HINT_AT:
		_hinted = true
		_render()
	if anisha_typing:
		# Anisha at the keyboard: down to the line, submit, next
		_auto -= dt
		if _auto <= 0.0:
			_auto = 0.9
			if not _sel in s.bug:
				_sel = s.bug[0]
				_render()
			else:
				_submit()
	var pct := clampf(_time / _round_time, 0.0, 1.0)
	_bar.size = Vector2(_bar_bg.size.x * pct, 6)
	_bar.color = Color("#2ea043") if pct > 0.4 else (Color("#d29922") if pct > 0.2 else Color("#f85149"))
	if _time <= 0.0:
		if night:
			_run_failed()
		else:
			_finish(false)


## Night: a run timed out. It starts again from its first test; after two, Anisha takes the keyboard.
func _run_failed() -> void:
	runs_failed += 1
	Sfx.ui("ui_back", 0.0)
	game.camera_rig.add_trauma(0.2)
	_r = 0
	_sel = 0
	_time = _round_time
	_on_round = 0.0
	_hinted = false
	_wrong = -1
	if runs_failed >= 2:
		anisha_typing = true
		_auto = 1.2
		_time = 999.0
		game.toast("Anisha takes the keyboard", "cross")
		print("[moulinette] night: two runs KO, Anisha takes the keyboard")
	else:
		game.toast("KO. Run %d." % (runs_failed + 1), "cross")
		print("[moulinette] night: run %d KO, again" % runs_failed)
	_render()


func _next_round() -> void:
	_r += 1
	_sel = 0
	_time = 999.0 if anisha_typing else _round_time
	_on_round = 0.0
	_hinted = false
	_wrong = -1
	if _r >= _rounds.size():
		_finish(true)
	else:
		_render()


func _unhandled_input(event: InputEvent) -> void:
	if _over:
		return
	if _ok > 0.0:
		if _ok < 1.9 and event.is_action_pressed("confirm"):
			_ok = 0.0
			_next_round()
		return
	if anisha_typing:
		return
	var n: int = _rounds[_r].code.size()
	if event.is_action_pressed("ui_up_alt") or event.is_action_pressed("ui_up"):
		_sel = (_sel + n - 1) % n
		Sfx.ui("ui_hover", -12.0)
		_render()
	elif event.is_action_pressed("ui_down_alt") or event.is_action_pressed("ui_down"):
		_sel = (_sel + 1) % n
		Sfx.ui("ui_hover", -12.0)
		_render()
	elif event.is_action_pressed("confirm"):
		_submit()
	else:
		return
	get_viewport().set_input_as_handled()


func _finish(win: bool) -> void:
	_over = true
	if not win:
		Sfx.ui("ui_back")
	var tw := create_tween()
	tw.tween_interval(0.3)
	tw.tween_callback(func(): _done.call(win))
