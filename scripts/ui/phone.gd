class_name Phone
extends CanvasLayer
## Mano's phone (docs/DESIGN.md §4.7, V2-24): a generic device, no brand and no emoji, in Atkinson Next.
## The lock screen is a small card bottom-right with the time and the messages that land on it (two
## pulses of the buzz each); die() is 17:43: the battery blinks at 0 %, the screen goes black, the phone goes back
## into his pocket. charge() is chapter 3: 100 % again.
## The phone in his hand (open_app): a bigger device centre-right over a dimmed scene, with
##  - Messages: the threads of dialogue/chat.json (Chat), unread counts, a "Mark all read" row (the flood can be read
##    or skipped), each thread's bubbles, and the reply Mano can send there as tone choices, saying nothing included;
##  - Find: where the right AirPod was last seen (flags.finder_place / finder_time), which also pins it on the map;
##  - Music: the songs heard tonight (flags.songs_heard).
## Keys: up and down (W, S, the arrows, the d-pad) move and scroll, E / Enter / A opens or picks, 1-3 pick a reply,
## Esc / Backspace / B go back (and close from the home screen), the phone key (Q) puts it away at once. The story
## drives it with `$ phone ...` (StoryCommands, main.phone_cmd); `closed` lets a conversation that opened it go on.

signal closed

const SIZE := Vector2(232, 352)      # the lock-screen card at the 1600x900 base
const MARGIN := Vector2(56, 34)      # from the right edge, and above the letterbox bar
const RADIUS := 26.0
const BEZEL := Color("#2c2f37")
const BODY := Color("#0b0c10")
const SCREEN_TOP := Color("#1b2233")
const SCREEN_BOTTOM := Color("#0f1119")
const LOW := Color("#ff5a4e")
const MAX_ROWS := 3
# the phone in his hand
const OPEN_SIZE := Vector2(404, 724)
const OPEN_RIGHT := 150.0            # from the right edge of the screen
const PAD := 18.0                    # the screen's margin inside the device
const BG := Color("#0f1119")
const ROW := Color(1, 1, 1, 0.06)
const ROW_SEL := Color(1, 1, 1, 0.16)
const BUBBLE := Color("#262b38")
const BUBBLE_MINE := Color("#2f6fd6")
const DIM := Color(1, 1, 1, 0.62)
const ACCENT := Color("#5aa0ff")
const BADGE := Color("#e5484d")
const T_TITLE := 24
const T_BODY := 19
const T_NAME := 17
const T_SMALL := 15
const APPS := ["home", "messages", "find", "music"]
const SCROLL_STEP := 72.0
## Apps and threads `$ phone open` may name (the validator checks them).

var hud: HUD
var state := "hidden"            # hidden, lock, dying, dead, open
var battery := 1                 # per cent
var charged := false             # back from the BDE strip (flags.phone_charged)
var app := ""                    # home, messages, thread, find, music (while open)
var thread_id := ""
var _root: Control
var _card: Control
var _time: Label
var _date: Label
var _batt: Label
var _rows: VBoxContainer
var _t := 0.0
var _shown := 0.0                # 0 hidden .. 1 up
var _want := 0.0
var _dark := 0.0                 # the screen going black (die)
var _blink := 0.0
# the phone in his hand
var _open: Control
var _scrim: ColorRect
var _status_time: Label
var _status_batt: Label
var _title: Label
var _back: Button
var _scroll: ScrollContainer
var _list: VBoxContainer
var _footer: VBoxContainer
var _items: Array = []           # [Button, Callable] the rows E / Enter picks, top to bottom
var _sel := -1                   # the highlighted row (-1: none; a thread scrolls instead)
var _open_k := 0.0               # 0 down .. 1 up in his hand
var _opened_at := 0.0
var _mark_row := false           # Messages starts with the "Mark all N as read" row
const OPEN_GUARD := 0.15         # the key that opened it does nothing in it
const CONFIRM_GUARD := 0.45      # E / Enter / A this soon after it opened (a tap through the lines before) picks nothing
var _sb_row: StyleBoxFlat
var _sb_sel: StyleBoxFlat


func _ready() -> void:
	layer = 11
	UITheme.init()
	_root = Control.new()
	_root.set_anchors_preset(Control.PRESET_FULL_RECT)
	_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_root)
	_card = Control.new()
	_card.size = SIZE
	_card.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_card.draw.connect(_draw_card)
	_root.add_child(_card)
	_batt = _label("1 %", 13, UITheme.print_700, LOW)
	_batt.position = Vector2(SIZE.x - 78, 16)
	_batt.size = Vector2(36, 16)
	_batt.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	_card.add_child(_batt)
	_time = _label("17:42", 58, UITheme.print_700, UITheme.FILM_WHITE)
	_time.position = Vector2(0, 46)
	_time.size = Vector2(SIZE.x, 70)
	_time.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_card.add_child(_time)
	_date = _label("jeudi 15 octobre", 15, UITheme.print_400, Color(UITheme.FILM_WHITE, 0.8))
	_date.position = Vector2(0, 116)
	_date.size = Vector2(SIZE.x, 20)
	_date.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_card.add_child(_date)
	_rows = VBoxContainer.new()
	_rows.position = Vector2(12, 150)
	_rows.size = Vector2(SIZE.x - 24, 180)
	_rows.add_theme_constant_override("separation", 8)
	_rows.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_card.add_child(_rows)
	_card.modulate.a = 0.0
	_build_open()


func _label(text: String, size: int, font: Font, color: Color) -> Label:
	var l := UITheme.label(text, size, font, color)
	l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return l


# ------------------------------------------------------------------ the lock screen
## The lock screen comes up at `clock` ("17:42"), no messages yet; the battery at 1 %, or full once charged.
func show_lock(clock := "17:42", date := "jeudi 15 octobre") -> void:
	for c in _rows.get_children():
		c.queue_free()
	_time.text = clock
	_date.text = date
	battery = _battery_now() if charged else 1
	_batt.text = "%d %%" % battery
	_batt.add_theme_color_override("font_color", LOW if battery <= 5 else UITheme.FILM_WHITE)
	_dark = 0.0
	state = "lock"
	_want = 1.0
	_card.queue_redraw()


## A message lands: the sender's name and the first line of it, a buzz. The oldest row goes past MAX_ROWS.
func preview(who: String, text: String, buzz := true) -> void:
	if state == "hidden" or state == "dead":
		show_lock(_time.text)
	var row := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(1, 1, 1, 0.13)
	sb.set_corner_radius_all(8)
	sb.content_margin_left = 10
	sb.content_margin_right = 10
	sb.content_margin_top = 7
	sb.content_margin_bottom = 8
	row.add_theme_stylebox_override("panel", sb)
	row.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 1)
	box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var head := HBoxContainer.new()
	head.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var nm := _label(who, 14, UITheme.print_700, UITheme.FILM_WHITE)
	nm.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(nm)
	head.add_child(_label("now", 12, UITheme.print_400, Color(UITheme.FILM_WHITE, 0.6)))
	box.add_child(head)
	var body := _label(text, 14, UITheme.print_400, Color(UITheme.FILM_WHITE, 0.92))
	body.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	body.custom_minimum_size = Vector2(SIZE.x - 44, 0)
	body.max_lines_visible = 2
	box.add_child(body)
	row.add_child(box)
	_rows.add_child(row)
	_rows.move_child(row, 0)   # the newest on top
	while _rows.get_child_count() > MAX_ROWS:
		var old := _rows.get_child(_rows.get_child_count() - 1)
		_rows.remove_child(old)
		old.queue_free()
	row.modulate.a = 0.0
	row.create_tween().tween_property(row, "modulate:a", 1.0, 0.25)
	if buzz:
		_buzz()


## The lock screen's clock (the story clock moves on while it is up: it dies at 17:43).
func set_time(clock: String) -> void:
	_time.text = clock


## 17:43: the battery blinks at 0 %, the screen goes black on an empty battery, then the phone goes away.
func die() -> void:
	if state == "hidden":
		show_lock(_time.text)
	state = "dying"
	battery = 0
	charged = false
	_batt.text = "0 %"
	var tw := create_tween()
	tw.tween_property(self, "_blink", 1.0, 0.9)
	tw.tween_property(self, "_dark", 1.0, 0.5)
	tw.tween_callback(func(): state = "dead")
	tw.tween_interval(1.0)
	tw.tween_callback(hide_card)


## Chapter 3: back from the BDE strip, full. The lock screen comes up at `clock` with the battery at 100 %.
func charge(clock: String) -> void:
	charged = true
	_dark = 0.0
	_blink = 0.0
	show_lock(clock)
	Sfx.ui("phone_buzz", -12.0)


## The phone as the save has it (Continue, a chapter started from the title): charged or not, put away.
func restore(is_charged: bool) -> void:
	charged = is_charged
	_dark = 0.0
	_blink = 0.0
	if state != "hidden":
		close(false)
		hide_card()


## The dead phone shown for a moment (the phone key before chapter 3): the black screen and its empty battery.
func show_dead() -> void:
	show_lock(_time.text)
	state = "dead"
	_dark = 1.0
	battery = 0
	_batt.text = "0 %"
	get_tree().create_timer(1.6, false).timeout.connect(func():
		if state == "dead":
			hide_card())


## Idle life: a glance at the phone, the lock screen with the story's clock for a moment (the black screen
## while it is dead), then away. Only when nothing else has the phone up.
func glance(dead: bool) -> void:
	if state != "hidden":
		return
	if dead:
		show_dead()
		return
	show_lock(Chapters.clock_text())
	get_tree().create_timer(2.4, false).timeout.connect(func():
		if state == "lock":
			hide_card())


## A batch of messages lands (`$ phone flood`): the buzz goes off once for every few of them, the last three show
## on the lock screen with "+N more" under them. Returns how long it takes.
func flood(msgs: Array, clock: String) -> float:
	if state == "hidden" or state == "dead":
		show_lock(clock)
	_time.text = clock
	var n := msgs.size()
	if n == 0:
		return 0.0
	var shown := msgs.slice(maxi(0, n - MAX_ROWS))
	var t := 0.0
	var buzzes := clampi(n / 6 + 1, 1, 6)
	for k in buzzes:
		get_tree().create_timer(t + k * 0.42, false).timeout.connect(func(): Sfx.ui("phone_buzz", -7.0 - k))
	for i in shown.size():
		var m: Dictionary = shown[i]
		var line := String(m.get("text", ""))
		if m.has("photo"):
			line = "Photo. " + line
		var head := Chat.sender_name(m)
		if Chat.threads().get(String(m.get("thread", "")), {}).get("group", false):
			head = "%s, %s" % [head, Chat.title(String(m.get("thread", "")))]
		var delay := 0.3 + i * 0.35
		get_tree().create_timer(delay, false).timeout.connect(func(): preview(head, line, false))
	if n > MAX_ROWS:
		get_tree().create_timer(0.3 + shown.size() * 0.35, false).timeout.connect(func():
			_more_row(n - MAX_ROWS))
	return 0.6 + shown.size() * 0.35 + 0.8


func _more_row(k: int) -> void:
	var l := _label("+%d more" % k, 14, UITheme.print_700, Color(UITheme.FILM_WHITE, 0.75))
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_rows.add_child(l)
	while _rows.get_child_count() > MAX_ROWS + 1:
		var old := _rows.get_child(0)
		_rows.remove_child(old)
		old.queue_free()


func hide_card() -> void:
	_want = 0.0
	if state != "dead" and state != "open":
		state = "hidden"


func is_up() -> bool:
	return _want > 0.0


func is_open() -> bool:
	return state == "open"


func _buzz() -> void:
	Sfx.ui("phone_buzz", -6.0)
	get_tree().create_timer(0.32, false).timeout.connect(func(): Sfx.ui("phone_buzz", -8.0))


## The battery since the BDE strip: 100 % at 19:10, a per cent every six minutes.
func _battery_now() -> int:
	return clampi(100 - maxi(0, Chapters.clock() - 1150) / 6, 5, 100)


# ------------------------------------------------------------------ the phone in his hand
func _build_open() -> void:
	_scrim = ColorRect.new()
	_scrim.color = Color(0.02, 0.02, 0.04, 0.0)
	_scrim.set_anchors_preset(Control.PRESET_FULL_RECT)
	_scrim.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_root.add_child(_scrim)
	_open = Control.new()
	_open.size = OPEN_SIZE
	_open.pivot_offset = OPEN_SIZE * 0.5
	_open.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_open.draw.connect(_draw_open)
	_open.visible = false
	_root.add_child(_open)
	var screen := Control.new()
	screen.position = Vector2(PAD, PAD)
	screen.size = OPEN_SIZE - Vector2(PAD, PAD) * 2.0
	screen.clip_contents = true
	screen.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_open.add_child(screen)
	var col := VBoxContainer.new()
	col.set_anchors_preset(Control.PRESET_FULL_RECT)
	col.add_theme_constant_override("separation", 0)
	col.mouse_filter = Control.MOUSE_FILTER_IGNORE
	screen.add_child(col)
	# status bar: the time and the battery
	var status := HBoxContainer.new()
	status.custom_minimum_size = Vector2(0, 34)
	status.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var sm := MarginContainer.new()
	sm.add_theme_constant_override("margin_left", 22)
	sm.add_theme_constant_override("margin_right", 22)
	sm.add_theme_constant_override("margin_top", 8)
	sm.mouse_filter = Control.MOUSE_FILTER_IGNORE
	sm.add_child(status)
	col.add_child(sm)
	_status_time = _label("19:12", T_SMALL, UITheme.print_700, UITheme.FILM_WHITE)
	_status_time.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	status.add_child(_status_time)
	_status_batt = _label("100 %", T_SMALL, UITheme.print_700, UITheme.FILM_WHITE)
	status.add_child(_status_batt)
	# header: back, title
	var head := HBoxContainer.new()
	head.custom_minimum_size = Vector2(0, 56)
	head.add_theme_constant_override("separation", 6)
	head.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var hm := MarginContainer.new()
	hm.add_theme_constant_override("margin_left", 10)
	hm.add_theme_constant_override("margin_right", 16)
	hm.mouse_filter = Control.MOUSE_FILTER_IGNORE
	hm.add_child(head)
	col.add_child(hm)
	_back = Button.new()
	_back.text = "Back"   # no arrow glued onto the text (docs/DESIGN.md §5.4)
	_back.flat = true
	_back.focus_mode = Control.FOCUS_NONE
	_back.add_theme_font_override("font", UITheme.print_500)
	_back.add_theme_font_size_override("font_size", T_NAME)
	_back.add_theme_color_override("font_color", ACCENT)
	_back.add_theme_color_override("font_hover_color", ACCENT.lightened(0.2))
	_back.pressed.connect(back)
	head.add_child(_back)
	_title = _label("", T_TITLE, UITheme.print_700, UITheme.FILM_WHITE)
	_title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_title.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_title.clip_text = true
	_title.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	head.add_child(_title)
	_scroll = ScrollContainer.new()
	_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_SHOW_NEVER
	col.add_child(_scroll)
	var lm := MarginContainer.new()
	lm.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	lm.add_theme_constant_override("margin_left", 12)
	lm.add_theme_constant_override("margin_right", 12)
	lm.add_theme_constant_override("margin_bottom", 10)
	_scroll.add_child(lm)
	_list = VBoxContainer.new()
	_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_list.add_theme_constant_override("separation", 6)
	lm.add_child(_list)
	var fm := MarginContainer.new()
	fm.add_theme_constant_override("margin_left", 12)
	fm.add_theme_constant_override("margin_right", 12)
	fm.add_theme_constant_override("margin_bottom", 14)
	fm.add_theme_constant_override("margin_top", 6)
	fm.mouse_filter = Control.MOUSE_FILTER_IGNORE
	col.add_child(fm)
	_footer = VBoxContainer.new()
	_footer.add_theme_constant_override("separation", 6)
	fm.add_child(_footer)
	_sb_row = _row_box(ROW)
	_sb_sel = _row_box(ROW_SEL)
	_sb_sel.border_color = Color(ACCENT, 0.8)
	_sb_sel.set_border_width_all(2)


func _row_box(c: Color) -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = c
	sb.set_corner_radius_all(12)
	sb.content_margin_left = 14
	sb.content_margin_right = 14
	sb.content_margin_top = 10
	sb.content_margin_bottom = 10
	sb.anti_aliasing = true
	return sb


## The phone up in his hand at `which`: an app (home, messages, find, music) or a chat thread's id.
func open_app(which := "home") -> void:
	if state != "open":
		_opened_at = Time.get_ticks_msec() / 1000.0
	hide_card()
	state = "open"
	_open.visible = true
	if which in APPS:
		_go(which)
	elif Chat.threads().has(which):
		_go("thread", which)
	else:
		_go("home")
	Sfx.ui("ui_open", -10.0)


## Puts it away; `emit` false when the game does it (a load, the title) rather than Mano.
func close(emit := true) -> void:
	if state != "open":
		return
	if app == "thread" and thread_id != "":
		Chat.mark_read(thread_id)
	state = "hidden"
	app = ""
	Sfx.ui("ui_close", -10.0)
	if emit:
		closed.emit()


## The autotest's way through the flood: everything read, nothing answered, put away.
func skip() -> void:
	Chat.mark_all_read()
	close()


## Back: a thread to the list, an app to the home screen, the home screen puts the phone away.
func back() -> void:
	match app:
		"thread":
			Chat.mark_read(thread_id)
			_go("messages")
		"home", "":
			close()
		_:
			_go("home")
	Sfx.ui("ui_back", -10.0)


func _go(to: String, thread := "") -> void:
	if app == "thread" and thread_id != "" and to != "thread":
		Chat.mark_read(thread_id)
	app = to
	thread_id = thread
	for c in _list.get_children():
		_list.remove_child(c)
		c.queue_free()
	for c in _footer.get_children():
		_footer.remove_child(c)
		c.queue_free()
	_items.clear()
	_sel = -1
	_scroll.scroll_vertical = 0
	_back.text = "Back" if to != "home" else "Put away"
	match to:
		"home":
			_home()
		"messages":
			_messages()
		"thread":
			_thread(thread)
		"find":
			_find()
		"music":
			_music()
	if not _items.is_empty() and to != "thread":
		# the newest thread first, not "Mark all N as read": a stray confirm reads one thread, never skips the flood
		_select(1 if to == "messages" and _mark_row and _items.size() > 1 else 0)


## A row Mano can pick: a flat button in a rounded box, the label's parts laid out by `fill`.
func _row(fill: Callable, act: Callable, parent: Control = null) -> Button:
	var b := Button.new()
	b.focus_mode = Control.FOCUS_NONE
	b.custom_minimum_size = Vector2(0, 64)
	b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	for s in ["normal", "hover", "pressed", "hover_pressed", "disabled", "focus"]:
		b.add_theme_stylebox_override(s, _sb_row)
	var box := HBoxContainer.new()
	box.set_anchors_preset(Control.PRESET_FULL_RECT)
	box.offset_left = 14
	box.offset_right = -14
	box.add_theme_constant_override("separation", 12)
	box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	b.add_child(box)
	fill.call(box)
	var i := _items.size()
	_items.append([b, act])
	b.pressed.connect(func(): _activate(i))
	b.mouse_entered.connect(func(): _select(i))
	(parent if parent else _list).add_child(b)
	return b


func _select(i: int) -> void:
	if i < 0 or i >= _items.size():
		_sel = -1
	else:
		_sel = i
	for k in _items.size():
		var b: Button = _items[k][0]
		for s in ["normal", "hover", "pressed", "hover_pressed"]:
			b.add_theme_stylebox_override(s, _sb_sel if k == _sel else _sb_row)
	if _sel >= 0:
		var b: Button = _items[_sel][0]
		if b.get_parent() == _list:
			_scroll.ensure_control_visible.call_deferred(b)


func _activate(i: int) -> void:
	if i < 0 or i >= _items.size():
		return
	Sfx.ui("ui_click", -12.0)
	(_items[i][1] as Callable).call()


# ------------------------------------------------------------------ apps
func _home() -> void:
	_title.text = ""
	var clock := _label(Chapters.clock_text(), 64, UITheme.print_700, UITheme.FILM_WHITE)
	clock.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_list.add_child(clock)
	var date := _label("jeudi 15 octobre", T_NAME, UITheme.print_400, DIM)
	date.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_list.add_child(date)
	_list.add_child(_gap(18))
	var n := Chat.total_unread()
	_row(func(box): _app_row(box, "messages", "Messages", "%d new" % n if n > 0 else "", n), func(): _go("messages"))
	if finder_ready():
		_row(func(box): _app_row(box, "find", "Find", "my AirPods", 0), func(): _go("find"))
	_row(func(box): _app_row(box, "music", "Music", "heard tonight", 0), func(): _go("music"))
	_hint("%s to put it away" % UITheme.action_key("phone"))


## The finder app is there once the phone is charged (chapter 3).
func finder_ready() -> bool:
	return charged or String(GameState.flags.get("finder_place", "")) != ""


func _app_row(box: HBoxContainer, icon: String, name: String, sub: String, badge: int) -> void:
	var ic := Control.new()
	ic.custom_minimum_size = Vector2(40, 40)
	ic.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	ic.mouse_filter = Control.MOUSE_FILTER_IGNORE
	ic.draw.connect(func(): _draw_icon(ic, icon))
	box.add_child(ic)
	var v := VBoxContainer.new()
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	v.alignment = BoxContainer.ALIGNMENT_CENTER
	v.add_theme_constant_override("separation", 0)
	v.mouse_filter = Control.MOUSE_FILTER_IGNORE
	v.add_child(_label(name, T_BODY, UITheme.print_700, UITheme.FILM_WHITE))
	if sub != "":
		v.add_child(_label(sub, T_SMALL, UITheme.print_400, DIM))
	box.add_child(v)
	if badge > 0:
		box.add_child(_badge(badge))


func _badge(n: int) -> Control:
	var c := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = BADGE
	sb.set_corner_radius_all(11)
	sb.content_margin_left = 8
	sb.content_margin_right = 8
	sb.content_margin_top = 1
	sb.content_margin_bottom = 2
	c.add_theme_stylebox_override("panel", sb)
	c.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	c.mouse_filter = Control.MOUSE_FILTER_IGNORE
	c.add_child(_label(str(n), T_SMALL, UITheme.print_700, Color.WHITE))
	return c


func _messages() -> void:
	_title.text = "Messages"
	var n := Chat.total_unread()
	_mark_row = n > 0
	if n > 0:
		_row(func(box):
			var l := _label("Mark all %d as read" % n, T_NAME, UITheme.print_500, ACCENT)
			l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			l.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
			box.add_child(l), func():
				Chat.mark_all_read()
				_go("messages"))
	var threads := Chat.active_threads()
	if threads.is_empty():
		_list.add_child(_note("No messages."))
	for t in threads:
		var tid := String(t)
		_row(func(box): _thread_row(box, tid), func(): _go("thread", tid))


func _thread_row(box: HBoxContainer, tid: String) -> void:
	var ms := Chat.thread(tid)
	var last: Dictionary = ms.back() if not ms.is_empty() else {}
	var v := VBoxContainer.new()
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	v.alignment = BoxContainer.ALIGNMENT_CENTER
	v.add_theme_constant_override("separation", 1)
	v.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var top := HBoxContainer.new()
	top.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var t := _label(Chat.title(tid), T_BODY, UITheme.print_700, UITheme.FILM_WHITE)
	t.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	t.clip_text = true
	t.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	top.add_child(t)
	top.add_child(_label(String(last.get("at", "")), T_SMALL, UITheme.print_400, DIM))
	v.add_child(top)
	var who := "" if not Chat.threads().get(tid, {}).get("group", false) else Chat.sender_name(last) + ": "
	var p := _label(who + String(last.get("text", "Photo")), T_SMALL, UITheme.print_400, DIM)
	p.clip_text = true
	p.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	p.custom_minimum_size = Vector2(240, 0)
	v.add_child(p)
	box.add_child(v)
	var u := Chat.unread(tid)
	if u > 0:
		box.add_child(_badge(u))


## A thread: its messages as bubbles (the sender's name in their colour over the first of a run, Mano's own on the
## right), a "new" divider where the unread ones start, a photo as a drawn print; under it the reply Mano can
## send. It opens at the first unread message.
func _thread(tid: String) -> void:
	_title.text = Chat.title(tid)
	var group: bool = Chat.threads().get(tid, {}).get("group", false)
	var ms := Chat.thread(tid)
	var read := Chat.read_count(tid)
	var last_from := ""
	var last_at := ""
	var first_new: Control = null
	for i in ms.size():
		var m: Dictionary = ms[i]
		var mine := String(m.get("from", "")) == "mano"
		if i == read and i > 0:
			var div := _label("new", T_SMALL, UITheme.print_700, BADGE)
			div.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
			_list.add_child(div)
			first_new = div
		var at := String(m.get("at", ""))
		if at != last_at and (last_at == "" or Conditions.minutes(at) - Conditions.minutes(last_at) >= 10):
			var tl := _label(at, T_SMALL, UITheme.print_400, DIM)
			tl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
			_list.add_child(tl)
		last_at = at
		var who := String(m.get("from", m.get("from_name", "")))
		var bubble := _bubble(m, mine, group and not mine and who != last_from)
		_list.add_child(bubble)
		if i == read and first_new == null:
			first_new = bubble
		last_from = who
	var r := Chat.pending_reply(tid)
	if not r.is_empty():
		# the replies come after the last message, so reading the thread has the whole screen
		_list.add_child(_gap(6))
		var lab := _label("Reply", T_SMALL, UITheme.print_700, DIM)
		_list.add_child(lab)
		var opts: Array = r.get("options", [])
		for k in opts.size():
			var o: Dictionary = opts[k]
			var text := "(say nothing)" if String(o.get("tone", "")) == "silent" else DialogueData.format(String(o.get("text", "")))
			var kk := k
			_row(func(box):
				var n := _label("%d" % (kk + 1), T_SMALL, UITheme.print_700, ACCENT)
				n.size_flags_vertical = Control.SIZE_SHRINK_CENTER
				box.add_child(n)
				var l := _label(text, T_NAME, UITheme.print_400, UITheme.FILM_WHITE)
				l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
				l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
				l.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
				box.add_child(l), func(): reply(kk))
		for it in _items:
			(it[0] as Button).custom_minimum_size = Vector2(0, 54)
	# open at the first unread message (or the end)
	await get_tree().process_frame
	await get_tree().process_frame
	if not is_instance_valid(_scroll) or app != "thread" or thread_id != tid:
		return
	if first_new != null and is_instance_valid(first_new):
		_scroll.scroll_vertical = maxi(0, int(first_new.position.y) - 8)
	else:
		_scroll.scroll_vertical = int(_list.size.y)


func _bubble(m: Dictionary, mine: bool, name: bool) -> Control:
	var row := HBoxContainer.new()
	row.alignment = BoxContainer.ALIGNMENT_END if mine else BoxContainer.ALIGNMENT_BEGIN
	row.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var p := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = BUBBLE_MINE if mine else BUBBLE
	sb.set_corner_radius_all(14)
	sb.content_margin_left = 12
	sb.content_margin_right = 12
	sb.content_margin_top = 7
	sb.content_margin_bottom = 9
	sb.anti_aliasing = true
	p.add_theme_stylebox_override("panel", sb)
	p.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 3)
	v.mouse_filter = Control.MOUSE_FILTER_IGNORE
	if name:
		v.add_child(_label(Chat.sender_name(m), T_SMALL, UITheme.print_700, Chat.sender_color(m)))
	if m.has("photo"):
		var ph := Control.new()
		ph.custom_minimum_size = Vector2(200, 124)
		ph.mouse_filter = Control.MOUSE_FILTER_IGNORE
		ph.draw.connect(func(): _draw_photo(ph))
		v.add_child(ph)
	var text := DialogueData.format(String(m.get("text", "")))
	var l := _label(text, T_BODY, UITheme.print_400, UITheme.FILM_WHITE)
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	var w := UITheme.print_400.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, T_BODY).x
	l.custom_minimum_size = Vector2(minf(w + 2.0, 250.0), 0)
	v.add_child(l)
	p.add_child(v)
	row.add_child(p)
	return row


## Mano answers the open thread's reply with option `i`: his message (unless he says nothing), and the friends'
## reactions buzzing in a moment later.
func reply(i: int) -> void:
	if app != "thread":
		return
	var r := Chat.pending_reply(thread_id)
	if r.is_empty():
		return
	var reacts := Chat.answer(r, i, Chapters.clock_text())
	var tid := thread_id
	Chat.mark_read(tid)
	_go("thread", tid)
	if not reacts.is_empty():
		get_tree().create_timer(1.1, false).timeout.connect(func():
			Sfx.ui("phone_buzz", -9.0)
			Chat.mark_read(tid)
			if app == "thread" and thread_id == tid:
				_go("thread", tid))


func _find() -> void:
	_title.text = "Find"
	var place := String(GameState.flags.get("finder_place", ""))
	var at := String(GameState.flags.get("finder_time", ""))
	var map := Control.new()
	map.custom_minimum_size = Vector2(0, 250)
	map.mouse_filter = Control.MOUSE_FILTER_IGNORE
	map.draw.connect(func(): _draw_find_map(map, place != "" and not (bool(GameState.flags.get("found", false)) and int(GameState.flags.get("chapter", 1)) >= 4)))
	_list.add_child(map)
	_list.add_child(_gap(10))
	_list.add_child(_label("Right AirPod", T_TITLE, UITheme.print_700, UITheme.FILM_WHITE))
	# found in the Under's sofa (flags.found), then both in the case for Anisha (flags.airpods_case)
	var found := bool(GameState.flags.get("found", false)) and int(GameState.flags.get("chapter", 1)) >= 4
	var in_case := bool(GameState.flags.get("airpods_case", false))
	if found:
		var where := "in the case" if in_case else "connected: in my right ear"
		if bool(GameState.flags.get("credits_done", false)):
			where = "down a drain on rue Pasteur"   # the post-credits' plink
		_list.add_child(_label(where, T_BODY, UITheme.print_400, UITheme.FILM_WHITE))
	elif place != "":
		var p := WorldData.finder_place(place)
		var line := _label("last seen: %s, %s" % [p.get("label", place), at], T_BODY, UITheme.print_400, UITheme.FILM_WHITE)
		line.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		_list.add_child(line)
		_list.add_child(_note("Out of range. The pin is on my map."))
	else:
		_list.add_child(_note("No location yet."))
	_list.add_child(_gap(10))
	_list.add_child(_label("Left AirPod", T_TITLE, UITheme.print_700, UITheme.FILM_WHITE))
	_list.add_child(_label("in the case" if in_case else "connected: in my left ear", T_BODY, UITheme.print_400, UITheme.FILM_WHITE))


func _music() -> void:
	_title.text = "Music"
	var heard: Array = GameState.flags.get("songs_heard", [])
	_list.add_child(_note("Heard tonight"))
	if heard.is_empty():
		_list.add_child(_note("Nothing yet."))
	for stem in heard:
		var s := String(stem)
		var now := Sfx.music_now() == s
		_row(func(box):
			var ic := Control.new()
			ic.custom_minimum_size = Vector2(32, 32)
			ic.size_flags_vertical = Control.SIZE_SHRINK_CENTER
			ic.mouse_filter = Control.MOUSE_FILTER_IGNORE
			ic.draw.connect(func(): _draw_icon(ic, "music"))
			box.add_child(ic)
			var v := VBoxContainer.new()
			v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			v.alignment = BoxContainer.ALIGNMENT_CENTER
			v.add_theme_constant_override("separation", 0)
			v.mouse_filter = Control.MOUSE_FILTER_IGNORE
			v.add_child(_label(Chat.song_title(s), T_BODY, UITheme.print_700, ACCENT if now else UITheme.FILM_WHITE))
			v.add_child(_label(Chat.song_artist(s) + ("  ·  playing" if now else ""), T_SMALL, UITheme.print_400, DIM))
			box.add_child(v), func(): pass)
	if not heard.is_empty():
		_list.add_child(_gap(8))
		_list.add_child(_note("Music: Kevin MacLeod (incompetech.com), CC BY 4.0"))


func _note(text: String) -> Label:
	var l := _label(text, T_SMALL, UITheme.print_400, DIM)
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	return l


func _gap(h: float) -> Control:
	var c := Control.new()
	c.custom_minimum_size = Vector2(0, h)
	c.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return c


func _hint(text: String) -> void:
	var l := _label(text, T_SMALL, UITheme.print_400, DIM)
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_footer.add_child(l)


# ------------------------------------------------------------------ input (the phone in his hand)
func _input(event: InputEvent) -> void:
	if state != "open":
		return
	# a held up / down repeats (41 presses to reach the steps group's replies otherwise); nothing else does
	var moving := event.is_action("ui_up") or event.is_action("ui_up_alt") or event.is_action("ui_down") or event.is_action("ui_down_alt")
	if event.is_echo() and not moving:
		return
	var since := Time.get_ticks_msec() / 1000.0 - _opened_at
	if since < OPEN_GUARD:
		return   # the key that opened it
	if since < CONFIRM_GUARD and (event.is_action_pressed("confirm") or event.is_action_pressed("interact")):
		get_viewport().set_input_as_handled()
		return
	var handled := true
	if event is InputEventKey and event.is_action_pressed("phone"):
		close()
	elif event.is_action_pressed("back"):   # Esc is also the pause key: in the phone it goes back; the Menu button pauses
		back()
	elif event.is_action_pressed("ui_up", true) or event.is_action_pressed("ui_up_alt", true):
		_move(-1)
	elif event.is_action_pressed("ui_down", true) or event.is_action_pressed("ui_down_alt", true):
		_move(1)
	elif event.is_action_pressed("confirm") or event.is_action_pressed("interact"):
		if _sel >= 0:
			_activate(_sel)
	elif event is InputEventKey and event.pressed and app == "thread" and event.physical_keycode >= KEY_1 and event.physical_keycode <= KEY_4:
		reply(event.physical_keycode - KEY_1)
	elif event is InputEventJoypadButton and event.is_action_pressed("phone"):
		_move(1)
	else:
		handled = false
	if handled:
		get_viewport().set_input_as_handled()


## Up and down: through the rows; in a thread, the messages scroll until the end, where the reply options start.
func _move(d: int) -> void:
	if app == "thread":
		var at_end := _scroll.scroll_vertical >= int(_list.size.y - _scroll.size.y) - 4
		if _sel < 0:
			if d > 0 and at_end and not _items.is_empty():
				_select(0)
			else:
				_scroll.scroll_vertical += int(SCROLL_STEP * d)
			return
		if d < 0 and _sel == 0:
			_select(-1)
			return
		_select(clampi(_sel + d, 0, _items.size() - 1))
		return
	if _items.is_empty():
		_scroll.scroll_vertical += int(SCROLL_STEP * d)
		return
	_select(clampi(_sel + d, 0, _items.size() - 1))


func _process(dt: float) -> void:
	_t += dt
	_shown = move_toward(_shown, _want, dt / 0.32)
	var vp := _root.get_viewport_rect().size
	var bar := hud.letterbox_height() if hud else 0.0
	var k := _shown * _shown * (3.0 - 2.0 * _shown)
	var home := Vector2(vp.x - MARGIN.x - SIZE.x, vp.y - bar - MARGIN.y - SIZE.y)
	_card.position = home + Vector2(0, (1.0 - k) * (SIZE.y * 0.6))
	_card.rotation = deg_to_rad(-3.0 + (1.0 - k) * 4.0)
	_card.pivot_offset = SIZE * 0.5
	var fade := hud.fade.color.a if hud and hud.fade else 0.0
	_card.modulate.a = k * (1.0 - fade)
	_card.visible = _card.modulate.a > 0.002
	var screen_on := 1.0 - _dark
	for c: CanvasItem in [_time, _date, _batt, _rows]:
		c.modulate.a = screen_on
	if state == "dying" and _blink > 0.0:
		_batt.modulate.a = screen_on * (0.35 + 0.65 * (0.5 + 0.5 * cos(_t * 14.0)))
	if _card.visible:
		_card.queue_redraw()
	if state == "dead" and _want == 0.0 and _shown == 0.0:
		state = "hidden"   # the dead phone is back in his pocket: the next glance or phone key shows it again
	# the phone in his hand: slides up from the bottom right, the scene dims behind it
	_open_k = move_toward(_open_k, 1.0 if state == "open" else 0.0, dt / 0.28)
	var ok := _open_k * _open_k * (3.0 - 2.0 * _open_k)
	_open.visible = ok > 0.002
	_scrim.color.a = 0.5 * ok
	if _open.visible:
		var at := Vector2(vp.x - OPEN_RIGHT - OPEN_SIZE.x, (vp.y - OPEN_SIZE.y) * 0.5)
		_open.position = at + Vector2(0, (1.0 - ok) * 260.0)
		_open.rotation = deg_to_rad((1.0 - ok) * 6.0 - 1.2)
		_open.modulate.a = ok
		_status_time.text = Chapters.clock_text()
		_status_batt.text = "%d %%" % _battery_now()


# ------------------------------------------------------------------ drawing
func _draw_card() -> void:
	var r := Rect2(Vector2.ZERO, SIZE)
	# the device: a dark body with a thin lighter bezel line, a shadow under it
	_round(_card, r.grow(3.0).grow_individual(0, 0, 0, 2), RADIUS + 3.0, Color(0, 0, 0, 0.35), Vector2(3, 6))
	_round(_card, r, RADIUS, BEZEL, Vector2.ZERO)
	_round(_card, r.grow(-2.0), RADIUS - 2.0, BODY, Vector2.ZERO)
	# the screen: a plain dark gradient wallpaper, black when the battery is gone
	var s := r.grow(-7.0)
	var steps := 12
	for i in steps:
		var a := float(i) / steps
		var b := float(i + 1) / steps
		var c := SCREEN_TOP.lerp(SCREEN_BOTTOM, (a + b) * 0.5).lerp(Color.BLACK, _dark)
		var band := Rect2(s.position + Vector2(0, s.size.y * a), Vector2(s.size.x, s.size.y * (b - a) + 1.0))
		_round_clip(band, s, RADIUS - 7.0, c)
	# the camera notch, the battery in the status bar
	_card.draw_circle(Vector2(SIZE.x * 0.5, 18), 4.0, Color("#05060a"))
	var bx := Rect2(SIZE.x - 38, 18, 20, 10)
	var on := 1.0 - _dark
	_card.draw_rect(bx, Color(UITheme.FILM_WHITE, 0.75 * on), false, 1.2)
	_card.draw_rect(Rect2(bx.end.x, bx.position.y + 3, 2, 4), Color(UITheme.FILM_WHITE, 0.75 * on))
	if battery > 0:
		var w := clampf(battery / 100.0, 0.1, 1.0) * 16.0
		_card.draw_rect(Rect2(bx.position + Vector2(2, 2), Vector2(w, 6)), Color(LOW if battery <= 5 else UITheme.FILM_WHITE, on))
	if _dark > 0.5:
		# the empty battery in the middle of the black screen, its red sliver blinking
		var a := (_dark - 0.5) * 2.0
		var c := Vector2(SIZE.x * 0.5, SIZE.y * 0.5)
		var big := Rect2(c - Vector2(30, 14), Vector2(60, 28))
		_card.draw_rect(big, Color(UITheme.FILM_WHITE, 0.55 * a), false, 2.0)
		_card.draw_rect(Rect2(big.end.x, c.y - 6, 4, 12), Color(UITheme.FILM_WHITE, 0.55 * a))
		var pulse := 0.5 + 0.5 * cos(_t * 6.0)
		_card.draw_rect(Rect2(big.position + Vector2(4, 4), Vector2(5, 20)), Color(LOW, a * pulse))


func _draw_open() -> void:
	var r := Rect2(Vector2.ZERO, OPEN_SIZE)
	_round(_open, r.grow(4.0).grow_individual(0, 0, 0, 3), 44.0, Color(0, 0, 0, 0.45), Vector2(6, 12))
	_round(_open, r, 42.0, BEZEL, Vector2.ZERO)
	_round(_open, r.grow(-3.0), 39.0, BODY, Vector2.ZERO)
	_round(_open, r.grow(-PAD + 4.0), 30.0, BG, Vector2.ZERO)
	_open.draw_circle(Vector2(OPEN_SIZE.x * 0.5, PAD + 6.0), 5.0, Color("#05060a"))


## The apps' icons, drawn plainly (no brand): a speech bubble, a pin on a ring, a note.
func _draw_icon(c: Control, id: String) -> void:
	var s := c.size
	var mid := s * 0.5
	match id:
		"messages":
			_round(c, Rect2(Vector2(2, 4), Vector2(s.x - 4, s.y - 14)), 10.0, Color("#3ba55d"), Vector2.ZERO)
			c.draw_colored_polygon(PackedVector2Array([Vector2(10, s.y - 11), Vector2(20, s.y - 11), Vector2(8, s.y - 2)]), Color("#3ba55d"))
			for k in 3:
				c.draw_circle(Vector2(12 + k * 8, s.y * 0.5 - 4), 2.4, Color.WHITE)
		"find":
			c.draw_circle(mid, s.x * 0.48, Color("#2b7de9"))
			c.draw_arc(mid, s.x * 0.3, 0, TAU, 32, Color(1, 1, 1, 0.55), 2.0, true)
			c.draw_circle(mid, 4.5, Color.WHITE)
		"music":
			c.draw_circle(mid, s.x * 0.48, Color("#e5484d"))
			c.draw_circle(mid + Vector2(-5, 6), 4.6, Color.WHITE)
			c.draw_line(mid + Vector2(-1, 6), mid + Vector2(-1, -10), Color.WHITE, 2.4)
			c.draw_line(mid + Vector2(-1, -10), mid + Vector2(7, -6), Color.WHITE, 2.4)


## Cristina's photo of the AirPod: a little print, the earbud on a table, an "M" scratched on it.
func _draw_photo(c: Control) -> void:
	var r := Rect2(Vector2.ZERO, c.size)
	_round(c, r, 8.0, Color("#c8bfae"), Vector2.ZERO)
	_round(c, Rect2(Vector2(0, r.size.y * 0.62), Vector2(r.size.x, r.size.y * 0.38)), 8.0, Color("#a8987f"), Vector2.ZERO)
	var o := Vector2(r.size.x * 0.5, r.size.y * 0.45)
	c.draw_circle(o, 15.0, Color("#f4f4f2"))
	c.draw_circle(o + Vector2(5, -2), 5.0, Color("#d8d8d6"))
	var stem := PackedVector2Array([o + Vector2(-8, 9), o + Vector2(-12, 44), o + Vector2(-4, 46), o + Vector2(2, 12)])
	c.draw_colored_polygon(stem, Color("#f4f4f2"))
	c.draw_polyline(PackedVector2Array([o + Vector2(-7, -6), o + Vector2(-5, -11), o + Vector2(-2, -6), o + Vector2(1, -11), o + Vector2(3, -6)]), Color("#6a6a68"), 1.4, true)
	for k in 3:
		c.draw_line(o + Vector2(-11 + k * 2, 30 + k * 4), o + Vector2(-6 + k * 2, 31 + k * 4), Color("#9a9a96"), 1.2)


## The finder's map: a plain grid, two streets, and the pin where it was last seen (or a grey ring). Drawn once,
## with plain rectangles, lines and circles (an animated version stalled the Metal driver in a test run).
func _draw_find_map(c: Control, found: bool) -> void:
	var r := Rect2(Vector2.ZERO, c.size)
	if r.size.x < 10.0 or r.size.y < 10.0:
		return
	c.draw_rect(r, Color("#1c2230"))
	for i in range(1, 8):
		var x := r.size.x * i / 8.0
		c.draw_line(Vector2(x, 0), Vector2(x, r.size.y), Color(1, 1, 1, 0.05), 1.0)
	for i in range(1, 6):
		var y := r.size.y * i / 6.0
		c.draw_line(Vector2(0, y), Vector2(r.size.x, y), Color(1, 1, 1, 0.05), 1.0)
	c.draw_rect(Rect2(0, r.size.y * 0.24, r.size.x, 9.0), Color(1, 1, 1, 0.14))
	c.draw_rect(Rect2(r.size.x * 0.44, r.size.y * 0.24, 7.0, r.size.y * 0.76), Color(1, 1, 1, 0.09))
	var p := Vector2(r.size.x * 0.62, r.size.y * 0.62)
	if found:
		c.draw_circle(p, 28.0, Color(ACCENT, 0.18))
		c.draw_circle(p, 9.0, ACCENT)
		c.draw_circle(p, 4.0, Color.WHITE)
	else:
		c.draw_circle(p, 20.0, Color(1, 1, 1, 0.12))


## A filled rounded rectangle (offset for a shadow) on `c`.
func _round(c: CanvasItem, r: Rect2, radius: float, col: Color, off: Vector2) -> void:
	var sb := StyleBoxFlat.new()
	sb.bg_color = col
	sb.set_corner_radius_all(int(radius))
	sb.anti_aliasing = true
	c.draw_style_box(sb, Rect2(r.position + off, r.size))


## A horizontal band of the screen, its corners rounded where it meets the screen's rounded corners.
func _round_clip(band: Rect2, screen: Rect2, radius: float, c: Color) -> void:
	var sb := StyleBoxFlat.new()
	sb.bg_color = c
	sb.anti_aliasing = false
	var top := band.position.y <= screen.position.y + 0.5
	var bottom := band.end.y >= screen.end.y - 1.5
	if top:
		sb.corner_radius_top_left = int(radius)
		sb.corner_radius_top_right = int(radius)
	if bottom:
		sb.corner_radius_bottom_left = int(radius)
		sb.corner_radius_bottom_right = int(radius)
	var rr := band
	if not top and not bottom:
		_card.draw_rect(rr, c)
		return
	_card.draw_style_box(sb, rr)
