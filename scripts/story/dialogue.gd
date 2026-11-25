class_name Dialogue
extends Node
## Runs dialogue scripts and draws the subtitles and choices in the print voice (docs/DESIGN.md §5.5): no box,
## film white Atkinson Hyperlegible with an ink outline and a soft shadow, the speaker's name inline in their
## colour when the speaker changes, a 140 ms fade. In conversations a line sits in the letterbox bar,
## elsewhere just above the bottom edge over a soft scrim. The inner voice (`think`, V2-10) and the stage sounds
## (`nar`: "*plink*") are Mano's pen, unnamed. bark() shows a line that does not stop play (a look-at's thought):
## it never takes the controls and gives way to any conversation.
## Choices are words in Mano's marker; the highlighted one is circled in red and is the one E picks.
## A script is an Array of steps:
##   ["speaker", "text"]  or  ["speaker", "text", "expression"]
##   {"who": "speaker", "t": "text", "ask": [["Choice", [steps...]], ...]}
##   Callable  (runs immediately, can start minigames or new dialogue)

signal line_shown(who: String, text: String, expression: String)
signal finished

const CPS := 52.0          # Settings > Typewriter: characters per second
const WIDTH := 640.0       # about 40 characters of Atkinson at size M, so a card is two lines at most
const SIZE_M := 32         # font_size at the 1600×900 base: 38 px at 1080p
const NAR_SIZE := 1.1      # the inner voice (Mynerve) runs a little larger: its x-height is smaller
const CHOICE_SIZE := 28    # 34 px at 1080p
const FADE := 0.14         # a line fades in while rising RISE pixels
const RISE := 6.0
const READ_MIN := 0.3      # the continue mark waits 0.3 s + 40 ms per character
const READ_PER_CHAR := 0.04
const GUARD := 0.15        # a key still held from the last line neither skips nor chooses
const BARK_BASE := 2.2     # a bark shows for 2.2 s + 0.05 s per character (docs/DESIGN.md §4.2)
const BARK_PER_CHAR := 0.05
const BARK_QUEUE := 2      # at most two wait behind the one showing; a third replaces the last one waiting
const BARK_FADE := 0.3

var running := false
var speaker_info: Callable    # (id) -> {"name": String, "color": Color}
## A card with a recording (VoiceLines: the fictional NPCs) plays it on the Voice bus while it is shown and
## ducks the music; skipping the card stops it. `voice` is the playing card's {key, stream, seconds, env}.
var voice_player: AudioStreamPlayer
var voice := {}
var _voice_len := 0.0

var _queue: Array = []
var _text := ""
var _last_who := ""
var _shown := 0.0
var _total := 0
var _t_line := 0.0
var _choices: Array = []
var _choice_i := 0
var _marked := -1
var _choices_at := 0
var _waiting := false
var _on_end: Callable
var _in_next := 0         # inside _next() (nested calls count): end_now() finishes once the running step returns
var _end_asked := false
var _hold := false        # pause_for(): the step that asked returns and the queue waits for the timer
var _alpha := 0.0
var _hud: HUD
var _arrows: Array[Texture2D] = []
var _arrow_frame := -1
var _checked := false
var _loop: PenStyle
var _no_box := StyleBoxEmpty.new()

var sub: RichTextLabel
var choice_box: VBoxContainer
var scrim: TextureRect
var bark_label: RichTextLabel
var _barks: Array = []      # [who, text, seconds] waiting
var _bark: Array = []       # the one showing, or []
var _bark_t := 0.0          # seconds it has shown
var _bark_a := 0.0


func build_ui(parent: Control) -> void:
	UITheme.init()
	_hud = parent.get_parent() as HUD
	for k in 3:
		_arrows.append(arrow_texture(k))
	# both option styles share margins, so the circled one does not change size
	_loop = PenStyle.make(PenStyle.Kind.LOOP, UITheme.MARKER_RED, 2.6, 7)
	for sb: StyleBox in [_loop, _no_box]:
		sb.content_margin_left = 44
		sb.content_margin_right = 16
		sb.content_margin_top = 5
		sb.content_margin_bottom = 7
	# a soft scrim behind lines shown outside the letterbox (0 to 65 %)
	scrim = TextureRect.new()
	scrim.texture = _scrim_texture()
	scrim.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	scrim.offset_left = 0
	scrim.offset_right = 0
	scrim.offset_bottom = 0
	scrim.offset_top = -240
	scrim.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	scrim.stretch_mode = TextureRect.STRETCH_SCALE
	scrim.mouse_filter = Control.MOUSE_FILTER_IGNORE
	scrim.modulate.a = 0.0
	parent.add_child(scrim)
	# the options stack above the line, centred as a block and left-aligned inside it
	choice_box = VBoxContainer.new()
	choice_box.add_theme_constant_override("separation", 0)
	choice_box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(choice_box)
	sub = make_label()
	sub.modulate.a = 0.0
	parent.add_child(sub)
	bark_label = make_label()
	bark_label.modulate.a = 0.0
	parent.add_child(bark_label)
	voice_player = AudioStreamPlayer.new()
	voice_player.bus = "Voice"
	voice_player.finished.connect(_voice_done)
	add_child(voice_player)


## The subtitle label: the print voice in film white with an ink outline and a soft shadow, wrapped at WIDTH.
## scripts/dev/line_check.gd measures every card with one of these.
static func make_label() -> RichTextLabel:
	var l := RichTextLabel.new()
	l.fit_content = true
	l.scroll_active = false
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.visible_characters_behavior = TextServer.VC_CHARS_AFTER_SHAPING
	l.custom_minimum_size = Vector2(WIDTH, 0)
	l.size = Vector2(WIDTH, 0)
	l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	l.add_theme_font_override("normal_font", UITheme.print_400)
	l.add_theme_font_override("bold_font", UITheme.print_700)
	l.add_theme_color_override("default_color", UITheme.FILM_WHITE)
	l.add_theme_constant_override("line_separation", 2)
	UITheme.over_scene(l, 7, 0.45)
	return l


## Writes one card into `l`: the speaker's name in their colour (when given), the line, and the hidden
## continue mark glued to the last word by a no-break space. Returns the length of the name part, where the
## typewriter starts.
static func fill_line(l: RichTextLabel, who: String, who_name: String, color: Color, text: String, size: int, mark: Texture2D) -> int:
	l.clear()
	l.visible_characters = -1
	l.push_paragraph(HORIZONTAL_ALIGNMENT_CENTER)
	var lead := 0
	if who == "nar" or who == "think":
		l.push_font(UITheme.pen, int(round(size * NAR_SIZE)))
	else:
		l.push_font(UITheme.print_400, size)
		if who_name != "":
			l.push_font(UITheme.print_700, size)
			l.push_color(color)
			l.add_text(who_name + ": ")
			l.pop()
			l.pop()
			lead = who_name.length() + 2
	l.add_text(text + String.chr(0xA0))
	l.add_image(mark, 0, 0, Color(1, 1, 1, 0), INLINE_ALIGNMENT_CENTER, Rect2(), "cont")
	l.pop()
	l.pop()
	return lead


## Size M is 38 px at 1080p; the subtitles_size setting scales it (S 0.84, L 1.2, XL 1.5).
static func subtitle_size() -> int:
	return int(round(SIZE_M * float(GameState.settings.get("subtitles_size", 1.0))))


## A line that does not stop play: shown for BARK_BASE + BARK_PER_CHAR per character (or `secs`), after the
## barks already waiting (two at most). Returns how long it will show. A conversation clears them.
func bark(who: String, text: String, secs := -1.0) -> float:
	var t := secs if secs > 0.0 else BARK_BASE + BARK_PER_CHAR * text.length()
	if running:
		return 0.0
	if _barks.size() >= BARK_QUEUE:
		_barks.pop_back()
	_barks.append([who, text, t])
	return t


## A bark is showing or waiting (autotests, look-at checks).
func is_barking() -> bool:
	return not _bark.is_empty() or not _barks.is_empty()


func bark_text() -> String:
	return String(_bark[1]) if not _bark.is_empty() else ""


func clear_barks() -> void:
	_barks.clear()
	_bark = []


func _update_bark(dt: float) -> void:
	if running:
		clear_barks()
	if _bark.is_empty() and not _barks.is_empty():
		_bark = _barks.pop_front()
		_bark_t = 0.0
		var info: Dictionary = speaker_info.call(_bark[0]) if speaker_info.is_valid() else {"name": "", "color": UITheme.FILM_WHITE}
		var nm := "" if String(_bark[0]) in ["think", "nar", "mano"] else String(info.get("name", ""))
		fill_line(bark_label, String(_bark[0]), nm, info.get("color", UITheme.FILM_WHITE), String(_bark[1]), subtitle_size(), _arrows[0])
		if OS.is_debug_build():
			print("[bark] %s: %s" % [_bark[0], _bark[1]])
	var want := 0.0
	if not _bark.is_empty():
		_bark_t += dt
		var hold: float = _bark[2]
		want = clampf(minf(_bark_t / FADE, (hold - _bark_t) / BARK_FADE + 1.0), 0.0, 1.0)
		if _bark_t >= hold + BARK_FADE:
			_bark = []
	_bark_a = want if not running else 0.0


func say(steps: Array, on_end := Callable()) -> void:
	clear_barks()
	_queue = steps.duplicate()
	_on_end = on_end
	if not running:
		running = true
		_last_who = ""
	_next()


## Insert steps to run right after the current line (used by callables that chain dialogue).
func push(steps: Array) -> void:
	_queue = steps + _queue


## Replace everything still to come with `steps` (a `=> cue` jump in the dialogue data).
func jump(steps: Array) -> void:
	_queue = steps.duplicate()


## End the conversation now (`=> END`): from inside a step it finishes once that step returns.
func end_now() -> void:
	_queue.clear()
	if not running:
		return
	if _in_next > 0:
		_end_asked = true
	else:
		_finish()


## Hold the conversation for `seconds` with no card showing (`$ wait` in a cutscene, the phone), then go on. If
## something else moved the conversation on meanwhile (an autotest), the timer does nothing.
func pause_for(seconds: float) -> void:
	_hold = true
	_waiting = false
	sub.clear()
	_text = ""
	_pause_id += 1
	var id := _pause_id
	get_tree().create_timer(maxf(seconds, 0.0)).timeout.connect(func():
		if running and id == _pause_id and not _waiting and _choices.is_empty():
			_next())


var _pause_id := 0


## Hold the conversation until `sig` fires (`$ phone open`: until Mano puts his phone away), then go on. Like
## pause_for, nothing happens if something else moved the conversation on meanwhile.
func wait_until(sig: Signal) -> void:
	_hold = true
	_waiting = false
	sub.clear()
	_text = ""
	_pause_id += 1
	var id := _pause_id
	sig.connect(func(_a = null, _b = null):
		if running and id == _pause_id and not _waiting and _choices.is_empty():
			_next(), CONNECT_ONE_SHOT)


## A hold is on (pause_for or wait_until) and no card is showing: the conversation waits on something.
func is_holding() -> bool:
	return running and not _waiting and _choices.is_empty()


func _next() -> void:
	_stop_voice()
	_clear_choices()
	_in_next += 1
	while not _queue.is_empty():
		var step = _queue.pop_front()
		if step is Callable:
			step.call()
			if not running:
				_in_next -= 1
				return
			if _end_asked:
				break
			if _hold:
				_hold = false
				_in_next -= 1
				return
			continue
		if step is Array:
			_in_next -= 1
			_show(step[0], step[1], step[2] if step.size() > 2 else "")
			return
		if step is Dictionary:
			_in_next -= 1
			_choices = step.get("ask", [])
			_show(step.who, step.t, step.get("e", ""))
			return
	_in_next -= 1
	_end_asked = false
	_finish()


func _show(who: String, text: String, expr: String) -> void:
	var info: Dictionary = speaker_info.call(who) if speaker_info.is_valid() else {"name": who, "color": UITheme.FILM_WHITE}
	# the name only when the speaker changes (XAG 104 allows it)
	var who_name := String(info.get("name", "")) if who != _last_who and who != "nar" and who != "think" else ""
	var lead := fill_line(sub, who, who_name, info.color, text, subtitle_size(), _arrows[0])
	_arrow_frame = -1
	_checked = false
	_last_who = who
	_text = text
	_total = sub.get_total_character_count()
	_t_line = 0.0
	_waiting = true
	if GameState.settings.get("typewriter", false):
		_shown = lead
		sub.visible_characters = lead
	else:
		_complete_line()
	_play_voice(who, text)
	line_shown.emit(who, text, expr)


## The card's recording, when it has one; without one the card is silent.
func _play_voice(who: String, text: String) -> void:
	voice = VoiceLines.find(who, text) if voice_player else {}
	_voice_len = float(voice.get("seconds", 0.0))
	if voice.is_empty():
		return
	voice_player.stream = voice.stream
	voice_player.play()
	Sfx.duck_voice(true)
	if OS.is_debug_build():
		print("[voice] %s (%s) %.2f s: %s" % [voice.key, who, _voice_len, text])


## Skipping or leaving the card cuts its recording.
func _stop_voice() -> void:
	if voice_player == null:
		return
	if voice_player.playing:
		voice_player.stop()
	voice_player.stream = null   # the speaker's lip sync follows this stream only (CharacterRig.lip_sync)
	if not voice.is_empty():
		voice = {}
		Sfx.duck_voice(false)


func _voice_done() -> void:
	Sfx.duck_voice(false)


func _finish() -> void:
	_stop_voice()
	running = false
	_waiting = false
	_clear_choices()
	var cb := _on_end
	_on_end = Callable()
	finished.emit()
	if cb.is_valid():
		cb.call()


func _process(dt: float) -> void:
	if running:
		_t_line += dt
	_update_bark(dt)
	_layout(dt)
	if not running or not _waiting:
		return
	if _shown < _total:
		_shown += dt * CPS * (3.0 if Input.is_action_pressed("confirm") else 1.0)
		sub.visible_characters = int(_shown)
		if int(_shown) >= _total:
			_complete_line()
	elif _choices.is_empty() and _t_line > maxf(READ_MIN + READ_PER_CHAR * _text.length(), _voice_len - 0.2):
		# the mark boils at 8 fps; a voiced card shows it as the recording ends (E still skips at any time)
		_show_arrow(int(Time.get_ticks_msec() / 125.0) % _arrows.size())
	if not _checked and _t_line > 0.1 and OS.is_debug_build():
		_checked = true
		if sub.get_line_count() > 2:
			push_warning("Subtitle runs over two lines (keep cards to 2 x 40 characters): " + _text)


## Placement: centred in the letterbox bar while it is in, otherwise 72 px (at 1080p) above the bottom
## edge over the scrim; the options sit just above the line and clear of the bar.
func _layout(dt: float) -> void:
	_alpha = move_toward(_alpha, 1.0 if running else 0.0, dt / FADE)
	var area := (sub.get_parent() as Control).size
	var bar := _hud.letterbox_height() if _hud else 0.0
	var h := sub.size.y
	var k := smoothstep(0.0, 1.0, bar / (h + 16.0))
	var y := lerpf(area.y - 60.0 - h, area.y - bar * 0.5 - h * 0.5, k)
	var line_a := clampf(_t_line / FADE, 0.0, 1.0)
	sub.position = Vector2(roundf((area.x - WIDTH) * 0.5), roundf(y + (1.0 - line_a) * RISE))
	sub.modulate.a = _alpha * line_a
	scrim.modulate.a = maxf(_alpha * (1.0 - k), _bark_a * (1.0 - k))
	sub.visible = _alpha > 0.0
	scrim.visible = scrim.modulate.a > 0.002
	# a bark sits where a line outside the letterbox does, and rises in as one
	var bh := bark_label.size.y
	bark_label.position = Vector2(roundf((area.x - WIDTH) * 0.5), roundf(area.y - 60.0 - bh + (1.0 - clampf(_bark_t / FADE, 0.0, 1.0)) * RISE))
	bark_label.modulate.a = _bark_a
	bark_label.visible = _bark_a > 0.0
	if choice_box.get_child_count() > 0:
		var cs := choice_box.get_combined_minimum_size()
		choice_box.size = cs
		choice_box.position = Vector2(roundf((area.x - cs.x) * 0.5), roundf(minf(y, area.y - bar) - cs.y - 8.0))
		choice_box.modulate.a = sub.modulate.a


func _complete_line() -> void:
	_shown = _total
	sub.visible_characters = -1
	if not _choices.is_empty() and choice_box.get_child_count() == 0:
		_build_choices()


func _show_arrow(frame: int) -> void:
	if frame == _arrow_frame:
		return
	_arrow_frame = frame
	sub.update_image("cont", RichTextLabel.UPDATE_TEXTURE | RichTextLabel.UPDATE_COLOR, _arrows[frame], 0, 0, Color(1, 1, 1, 1))


func _build_choices() -> void:
	_clear_buttons()
	_choices_at = Time.get_ticks_msec()
	_marked = -1
	var n := _choices.size()
	for i in n:
		var b := Button.new()
		b.text = String(_choices[i][0])
		b.alignment = HORIZONTAL_ALIGNMENT_LEFT
		b.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
		b.add_theme_font_override("font", UITheme.marker_calm)
		b.add_theme_font_size_override("font_size", CHOICE_SIZE)
		b.add_theme_constant_override("outline_size", 6)
		b.add_theme_color_override("font_outline_color", Color(UITheme.INK_SHADOW, 0.85))
		b.add_theme_stylebox_override("focus", _no_box)
		b.mouse_entered.connect(_select.bind(i))
		b.focus_entered.connect(_mark.bind(i))
		b.pressed.connect(_pick.bind(i))
		b.draw.connect(_draw_number.bind(b, i))
		choice_box.add_child(b)
	# arrow keys and the d-pad move the focus inside the list only, so it never lands on another control
	for i in n:
		var b := choice_box.get_child(i) as Button
		b.focus_neighbor_top = b.get_path_to(choice_box.get_child(maxi(i - 1, 0)))
		b.focus_neighbor_bottom = b.get_path_to(choice_box.get_child(mini(i + 1, n - 1)))
		b.focus_neighbor_left = b.get_path_to(b)
		b.focus_neighbor_right = b.get_path_to(b)
		b.focus_previous = b.focus_neighbor_top
		b.focus_next = b.focus_neighbor_bottom
	_select(0)


func _select(i: int) -> void:
	var n := choice_box.get_child_count()
	if n == 0:
		return
	i = clampi(i, 0, n - 1)
	var b := choice_box.get_child(i) as Button
	if b and not b.has_focus():
		b.grab_focus()   # focus_entered marks it
	_mark(i)


## The circled option is always _choice_i, the one confirm picks: arrow keys and the d-pad move the
## focus (focus_entered), W/S and the mouse call _select(), and all of them land here.
func _mark(i: int) -> void:
	_choice_i = i
	if _marked == i:
		return
	_marked = i
	for j in choice_box.get_child_count():
		var b := choice_box.get_child(j) as Button
		var st: StyleBox = _loop if j == i else _no_box
		for s in ["normal", "hover", "pressed", "hover_pressed"]:
			b.add_theme_stylebox_override(s, st)
	_loop.progress = 0.0
	create_tween().tween_property(_loop, "progress", 1.0, 0.16).set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_OUT)
	Sfx.ui("ui_hover", -14.0)


## The option's number in a small sketched circle in its left margin (keys 1-4 still pick it).
func _draw_number(b: Button, i: int) -> void:
	var c := Vector2(21.0, b.size.y * 0.5)
	var pts := PackedVector2Array()
	for k in 25:
		var a := -2.2 + k / 24.0 * TAU * 1.08
		var r := 11.5 + 0.8 * sin(a * 2.0 + i)
		pts.append(c + Vector2(cos(a) * r, sin(a) * r * 0.94))
	b.draw_polyline(pts, Color(UITheme.INK_SHADOW, 0.55), 3.8, true)
	b.draw_polyline(pts, UITheme.FILM_WHITE, 1.7, true)
	var f: Font = UITheme.print_700
	var s := str(i + 1)
	var fs := 17
	var w := f.get_string_size(s, HORIZONTAL_ALIGNMENT_LEFT, -1, fs).x
	var base := c + Vector2(-w * 0.5, (f.get_ascent(fs) - f.get_descent(fs)) * 0.5)
	b.draw_string_outline(f, base, s, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, 5, Color(UITheme.INK_SHADOW, 0.85))
	b.draw_string(f, base, s, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, UITheme.FILM_WHITE)


func _pick(i: int) -> void:
	if i < 0 or i >= _choices.size() or Time.get_ticks_msec() - _choices_at < GUARD * 1000.0:
		return
	Sfx.ui("ui_click", -6.0)
	var steps: Array = _choices[i][1]
	_choices = []
	_queue = steps + _queue
	_next()


func _clear_buttons() -> void:
	for c in choice_box.get_children():
		choice_box.remove_child(c)
		c.queue_free()


func _clear_choices() -> void:
	_clear_buttons()
	_choices = []


func _unhandled_input(event: InputEvent) -> void:
	if not running or not _waiting:
		return
	if not _choices.is_empty() and _shown >= _total:
		if event.is_action_pressed("ui_up_alt") or event.is_action_pressed("ui_up"):
			_select(_choice_i - 1)
		elif event.is_action_pressed("ui_down_alt") or event.is_action_pressed("ui_down"):
			_select(_choice_i + 1)
		elif event.is_action_pressed("confirm"):
			_pick(_choice_i)
		elif event is InputEventKey and event.pressed and not event.echo and event.physical_keycode >= KEY_1 and event.physical_keycode <= KEY_4:
			_pick(event.physical_keycode - KEY_1)
		else:
			return
		get_viewport().set_input_as_handled()
		return
	if event.is_action_pressed("confirm") or (event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT):
		get_viewport().set_input_as_handled()
		if _shown < _total:
			_complete_line()
		elif _choices.is_empty() and _t_line > GUARD:
			Sfx.ui("ui_click", -16.0)
			_next()


## The continue mark: a small pen arrow, three drawings that "boil" at 8 fps.
static func arrow_texture(k: int) -> Texture2D:
	var rng := RandomNumberGenerator.new()
	rng.seed = 41 + k * 13
	var j := func() -> Vector2: return Vector2(rng.randf_range(-0.55, 0.55), rng.randf_range(-0.55, 0.55))
	var shaft := PackedVector2Array([Vector2(3, 10.8) + j.call(), Vector2(13, 10.1) + j.call(), Vector2(23.5, 10) + j.call()])
	var head := PackedVector2Array([Vector2(17.5, 4.5) + j.call(), Vector2(24.5, 10) + j.call(), Vector2(17.8, 15.5) + j.call()])
	return UITheme.stroke_texture(Vector2i(28, 20), [shaft, head], UITheme.FILM_WHITE, 2.0)


func _scrim_texture() -> GradientTexture2D:
	var g := Gradient.new()
	g.set_color(0, Color(UITheme.SCRIM, 0.0))
	g.set_color(1, Color(UITheme.SCRIM, 0.65))
	g.add_point(0.5, Color(UITheme.SCRIM, 0.32))
	var t := GradientTexture2D.new()
	t.gradient = g
	t.width = 4
	t.height = 128
	t.fill_from = Vector2(0, 0)
	t.fill_to = Vector2(0, 1)
	return t
