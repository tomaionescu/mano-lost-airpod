class_name HUD
extends CanvasLayer
## The in-game HUD in Mano's pen (docs/DESIGN.md §5.5): the objective on a torn Seyès strip (ObjectiveStrip: only
## when it changes, or while the journal key is held), sticky-note toasts top-right (two at most), one-off
## control hints on sticky notes bottom-left, the interaction prompt as a pen ring and a leader line
## (PenPrompt), the optional red-pen waypoint (PenWaypoint, off by default, never a distance), the area
## banner, the letterbox bars and a full-screen fade. Every icon is a ballpoint doodle (Doodles).

const SAFE := 53.0              # the safe margin: 64 px at 1080p
const MAX_TOASTS := 2
const TOAST_HOLD := 3.2
const HINT_MAX := 16.0          # a hint nobody acts on peels off by itself after this long on screen
const HINT_WALK := 6.0          # metres walked that retire the walking hint
const TAPE_PAD := Vector2(26, 4)   # masking tape round the banner's place name
## One-off control hints, shown once per save the first time each action matters, and peeled off as soon as
## the action has been used: [doodle, rows of [actions whose live keys are drawn, words]].
const HINTS := {
	"move": ["", [[["move_forward", "move_left", "move_back", "move_right"], "walk"], [["run"], "jog"]]],
	"journal": ["notebook", [[["journal"], "my notebook"], [[], "hold it for my to-do"]]],
	"map": ["map", [[["map"], "campus map"]]],
	"wardrobe": ["hoodie", [[["wardrobe"], "my fits"]]],
	"photo_mode": ["camera", [[["photo_mode"], "photo mode"]]],
	"phone": ["phone", [[["phone"], "my phone"]]],
}
## Toasts on another colour of note than yellow.
const TOAST_PAPER := {"coin": UITheme.STICKY_MINT, "cross": UITheme.STICKY_PINK}

var camera: Camera3D
var root: Control
var strip: ObjectiveStrip
var prompt: PenPrompt
var waypoint: PenWaypoint
var waypoint_target = null      # Vector3 or null
var mano_pos = null             # Mano's position (Vector3) while playing: the waypoint's fade, the walking hint
var toasts: Control
var hints: Control
var banner: VBoxContainer
var banner_title: Label
var banner_sub: Label
var _banner_t := 0.0
var _tape: Control
var _tape_shape := PackedVector2Array()
var bar_top: ColorRect
var bar_bottom: ColorRect
var _bars := 0.0
var _bars_target := 0.0
var fade: ColorRect
var hud_visible := true
var _hint_queue: Array[String] = []
var _hint: StickyNote = null
var _hint_id := ""
var _hint_t := 0.0
var _hint_gap := 0.0
var _hint_from = null
var _hint_alpha := 0.0


func _ready() -> void:
	layer = 10
	UITheme.init()
	root = Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.theme = UITheme.theme
	add_child(root)

	bar_top = _bar(true)
	bar_bottom = _bar(false)

	strip = ObjectiveStrip.new()
	root.add_child(strip)
	strip.set_home(Vector2(SAFE, SAFE - 10.0))
	prompt = PenPrompt.new()
	root.add_child(prompt)
	waypoint = PenWaypoint.new()
	root.add_child(waypoint)
	toasts = _layer()
	hints = _layer()

	# the area banner: the place in marker on a strip of masking tape, the line under it in pen
	banner = VBoxContainer.new()
	banner.set_anchors_preset(Control.PRESET_CENTER_TOP)
	banner.position = Vector2(-400, 84)
	banner.custom_minimum_size = Vector2(800, 0)
	banner.add_theme_constant_override("separation", 8)
	_tape = Control.new()
	_tape.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	_tape.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var tm := ShaderMaterial.new()
	tm.shader = ObjectiveStrip.PAPER_SHADER
	_tape.material = tm
	_tape.draw.connect(_draw_tape)
	banner_title = UITheme.label("", 47, UITheme.marker_title, UITheme.INK_BLACK)
	banner_title.position = TAPE_PAD
	_tape.add_child(banner_title)
	banner_sub = UITheme.over_scene(UITheme.label("", 25, UITheme.pen, UITheme.FILM_WHITE), 6, 0.5) as Label
	banner_sub.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	banner.add_child(_tape)
	banner.add_child(banner_sub)
	banner.modulate.a = 0.0
	root.add_child(banner)

	fade = ColorRect.new()
	fade.color = Color(0, 0, 0, 1)
	fade.set_anchors_preset(Control.PRESET_FULL_RECT)
	fade.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(fade)


# ------------------------------------------------------------------ the cold open and the finale
var _freeze: TextureRect = null
var _caption: Label = null


## A still of the frame (main.freeze_frame: the cold open stops on Mano's face): it holds over the scene, under the
## black and the subtitles, a touch colder than the moving picture, after a quick white flash, until clear_freeze().
func freeze(tex: Texture2D) -> void:
	if _freeze:
		_freeze.queue_free()
	_freeze = TextureRect.new()
	_freeze.texture = tex
	_freeze.set_anchors_preset(Control.PRESET_FULL_RECT)
	_freeze.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_freeze.stretch_mode = TextureRect.STRETCH_SCALE
	_freeze.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_freeze.modulate = Color(0.9, 0.93, 1.0)
	root.add_child(_freeze)
	root.move_child(_freeze, fade.get_index())
	flash(0.4)


func clear_freeze() -> void:
	if _freeze:
		_freeze.queue_free()
		_freeze = null
	if _caption:
		_caption.queue_free()
		_caption = null


## A camera flash: the whole screen white for an instant, fading in 0.3 s (the photos, the freeze).
func flash(strength := 0.6) -> void:
	var f := ColorRect.new()
	f.color = Color(1, 1, 1, strength)
	f.set_anchors_preset(Control.PRESET_FULL_RECT)
	f.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(f)
	var tw := f.create_tween()
	tw.tween_property(f, "color:a", 0.0, 0.3).set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_OUT)
	tw.tween_callback(f.queue_free)


## One line written on in Mano's pen in the middle of the black ("Six hours earlier."), held `seconds`, then gone.
func caption(text: String, seconds := 2.4) -> void:
	if _caption:
		_caption.queue_free()
	var l := UITheme.label(text, 44, UITheme.pen, UITheme.FILM_WHITE)
	l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(l)
	# sized to its words and centred (the write-on sweeps across the label itself, left to right)
	l.set_anchors_preset(Control.PRESET_CENTER)
	l.grow_horizontal = Control.GROW_DIRECTION_BOTH
	l.grow_vertical = Control.GROW_DIRECTION_BOTH
	var ms := l.get_combined_minimum_size()
	l.offset_left = -ms.x * 0.5
	l.offset_right = ms.x * 0.5
	l.offset_top = -ms.y * 0.5
	l.offset_bottom = ms.y * 0.5
	_caption = l
	Ink.write_on(l, minf(1.1, seconds * 0.45))
	var tw := l.create_tween()
	tw.tween_interval(maxf(seconds - 0.4, 0.2))
	tw.tween_property(l, "modulate:a", 0.0, 0.4)
	tw.tween_callback(func():
		if _caption == l:
			_caption = null
		l.queue_free())


func _bar(_top: bool) -> ColorRect:
	var r := ColorRect.new()
	r.color = Color(0, 0, 0, 1)
	r.mouse_filter = Control.MOUSE_FILTER_IGNORE
	r.size = Vector2.ZERO   # placed and sized every frame in _process
	root.add_child(r)
	return r


func _layer() -> Control:
	var c := Control.new()
	c.set_anchors_preset(Control.PRESET_FULL_RECT)
	c.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(c)
	return c


# ------------------------------------------------------------------ API
## A new objective. With `flash` the strip plays the change (old line struck through, new one written on)
## as soon as the HUD is visible; without it the text changes quietly.
func set_objective(text: String, flash := true) -> void:
	strip.set_objective(text, flash)


## The objective set outright, with no strike-through (loading a save, starting a chapter from the title).
func reset_objective(text: String) -> void:
	strip.reset(text)


## Shows the objective strip for a while (after loading a save).
func show_objective(seconds := 6.0) -> void:
	strip.show_for(seconds)


## The journal key held down: the objective strip stays up until the key comes up.
func peek_objective(on: bool) -> void:
	strip.peek(on)
	if on:
		hint_used("journal")


## A sticky note top-right in Mano's pen. `doodle` is a ballpoint icon id from Doodles.IDS (pencil, coin,
## coffee, airpod, camera, duck, cross, smile...), never a character or emoji. Two notes at most: a third
## peels the oldest off.
func toast(text: String, doodle := "") -> void:
	# the same note twice in a row (two journal entries from one line) shows once
	var live: Array = []
	for c in toasts.get_children():
		var n := c as StickyNote
		if n and not n.leaving:
			if n.text == text:
				return
			live.append(n)
	while live.size() >= MAX_TOASTS:
		(live.pop_front() as StickyNote).peel()
	var note := StickyNote.toast(text, doodle, TOAST_PAPER.get(doodle, UITheme.STICKY_YELLOW))
	toasts.add_child(note)
	_stack_toasts()
	note.land()
	var tw := note.create_tween()
	tw.tween_interval(StickyNote.IN_T + TOAST_HOLD)
	tw.tween_callback(note.peel)
	Sfx.ui("toast", -8.0)


## Queues the one-off control hint `id` (HINTS) unless this save has already seen it.
func hint(id: String) -> void:
	if not HINTS.has(id) or id == _hint_id or id in _hint_queue or id in GameState.flags.get("hints", []):
		return
	_hint_queue.append(id)
	# in the order of HINTS: walking before the notebook, the notebook before the map
	var order: Array = HINTS.keys()
	_hint_queue.sort_custom(func(a: String, b: String) -> bool: return order.find(a) < order.find(b))


## The player has just used `action` (a menu's name or a hint id): its hint has done its job.
func hint_used(action: String) -> void:
	var id := "photo_mode" if action == "photo" else action
	if not HINTS.has(id):
		return
	_hint_queue.erase(id)
	_seen(id)
	if id == _hint_id:
		_hint_t = maxf(_hint_t, HINT_MAX - 0.5)


func _seen(id: String) -> void:
	var seen: Array = GameState.flags.get("hints", [])
	if not id in seen:
		seen.append(id)
		GameState.flags["hints"] = seen


func _show_hint(id: String) -> void:
	var def: Array = HINTS[id]
	var rows: Array = []
	for r: Array in def[1]:
		var actions: Array = r[0]
		var keys: Array = []
		var words: String = r[1]
		if GameState.using_pad and not actions.is_empty() and String(actions[0]).begins_with("move_"):
			words = "left stick to " + words
		else:
			for a: String in actions:
				keys.append(UITheme.action_key(a))
		rows.append([keys, words])
	_hint = StickyNote.hint(rows, def[0])
	hints.add_child(_hint)
	_hint.base = Vector2(SAFE, root.size.y - SAFE - _hint.size.y)
	_hint.land(Vector2(0, 26))
	_hint_id = id
	_hint_t = 0.0
	_hint_from = null
	_seen(id)
	Sfx.ui("toast", -10.0)


func _update_hints(dt: float, show: bool) -> void:
	_hint_alpha = move_toward(_hint_alpha, 1.0 if show else 0.0, dt / 0.15)
	hints.modulate.a = _hint_alpha
	hints.visible = _hint_alpha > 0.002
	if _hint_id != "" and not is_instance_valid(_hint):   # it has peeled off and been freed
		_hint = null
		_hint_id = ""
		_hint_gap = 0.8
	if _hint_id == "":
		_hint_gap -= dt
		if show and _hint_gap <= 0.0 and not _hint_queue.is_empty():
			_show_hint(_hint_queue.pop_front())
		return
	_hint.base = Vector2(SAFE, root.size.y - SAFE - _hint.size.y)
	if not show or _hint.leaving:
		return
	_hint_t += dt
	if _hint_id == "move" and mano_pos != null:
		if _hint_from == null:
			_hint_from = mano_pos
		elif (mano_pos as Vector3).distance_to(_hint_from) > HINT_WALK:
			_hint_t = maxf(_hint_t, HINT_MAX - 1.0)
	if _hint_t >= HINT_MAX:
		_hint.peel()


## Toasts stack down from the top-right corner; the ones peeling off stay where they are.
func _stack_toasts() -> void:
	var y := SAFE - 10.0
	for c in toasts.get_children():
		var n := c as StickyNote
		if n == null or n.leaving:
			continue
		n.base = Vector2(root.size.x - SAFE - n.size.x, y)
		y += n.size.y + 14.0


## The place's name on masking tape at the top centre, and a line under it in pen.
func show_banner(title: String, sub := "") -> void:
	banner_title.text = title
	banner_sub.text = sub
	_banner_t = 4.2
	var ts := banner_title.get_combined_minimum_size()
	var s := ts + TAPE_PAD * 2.0
	_tape.custom_minimum_size = s
	_tape.pivot_offset = s * 0.5
	var rng := RandomNumberGenerator.new()
	rng.seed = hash(title)
	_tape.rotation = deg_to_rad(rng.randf_range(-2.2, -0.6))
	# torn by hand at both ends (a zigzag), the long edges nearly straight
	_tape_shape = PackedVector2Array()
	for i in 9:
		_tape_shape.append(Vector2(lerpf(4.0, s.x - 4.0, i / 8.0), rng.randf_range(-0.6, 0.6)))
	for i in 7:
		_tape_shape.append(Vector2(s.x - 4.0 + (5.0 if i % 2 == 0 else 0.0) + rng.randf_range(-1.2, 1.2), s.y * (i + 0.5) / 7.0))
	for i in 9:
		_tape_shape.append(Vector2(lerpf(s.x - 4.0, 4.0, i / 8.0), s.y + rng.randf_range(-0.6, 0.6)))
	for i in 7:
		_tape_shape.append(Vector2(4.0 - (5.0 if i % 2 == 0 else 0.0) + rng.randf_range(-1.2, 1.2), s.y * (6.5 - i) / 7.0))
	_tape.queue_redraw()


func _draw_tape() -> void:
	if _tape_shape.size() < 3:
		return
	var n := _tape_shape.size()
	var flat := ObjectiveStrip._uv(n, Vector2(0, 0))
	_tape.draw_polygon(ObjectiveStrip._shifted(_tape_shape, Vector2(1.5, 2.5)), PackedColorArray([Color(UITheme.INK_SHADOW, 0.18)]), flat)
	_tape.draw_polygon(_tape_shape, PackedColorArray([UITheme.TAPE]), ObjectiveStrip._uv(n, Vector2(0, 1)))


## Current height of each letterbox bar in UI units (the subtitles sit centred in the bottom one).
func letterbox_height() -> float:
	return bar_bottom.size.y


## The chapter card over the black (ChapterCard, docs/DESIGN.md §5.5): a fresh notebook page where the date writes
## itself top-right and is ruled in red, the time goes on in marker and the place in pen, then the page turns
## away, about 3.6 s in all. `small` is "date\nplace" (or just the place); `chapter` ("2 Lost & Found") adds
## the chapter with its number circled. It draws above the fade.
func title_card(big: String, small: String, hold := ChapterCard.HOLD, chapter := "") -> ChapterCard:
	var card := ChapterCard.new()
	card.time_text = big
	var parts := small.split("\n")
	if parts.size() > 1:
		card.date = parts[0]
		card.place = parts[1]
	else:
		card.place = small
	card.hold = hold
	card.chapter = chapter
	root.add_child(card)
	return card


## The nearest thing Mano can use (an Interactable) or null; `text` overrides the words PenPrompt picks.
func set_prompt(target, text := "") -> void:
	prompt.set_target(target, text)


## The bars slide in or out in 0.5 s; `instant` sets them at once (under the black, where a slide would show).
func set_letterbox(on: bool, instant := false) -> void:
	_bars_target = 1.0 if on else 0.0
	if instant:
		_bars = _bars_target


func set_hud_visible(v: bool) -> void:
	hud_visible = v


func fade_to(alpha: float, time := 0.6) -> Tween:
	var tw := create_tween()
	tw.tween_property(fade, "color:a", alpha, time)
	return tw


func _process(dt: float) -> void:
	var vp := root.get_viewport_rect().size
	# letterbox to 2.39:1
	_bars = move_toward(_bars, _bars_target, dt / 0.5)
	var bar_h := maxf(0.0, (vp.y - vp.x / 2.39) * 0.5) * _ease(_bars)
	bar_top.size = Vector2(vp.x, bar_h)
	bar_top.position = Vector2.ZERO
	bar_bottom.size = Vector2(vp.x, bar_h)
	bar_bottom.position = Vector2(0, vp.y - bar_h)
	# a clear full-screen rect still costs a blend over every Retina pixel
	fade.visible = fade.color.a > 0.002

	# in conversations and cutscenes (the letterbox) the scene has the screen to itself
	var show := hud_visible and _bars < 0.05
	strip.tick(dt, show)
	prompt.tick(dt, show, camera)
	waypoint.tick(dt, show and GameState.settings.get("waypoint", false), camera, waypoint_target, mano_pos)
	_stack_toasts()
	_update_hints(dt, show)

	_banner_t -= dt
	var ba := clampf(minf(_banner_t, 4.2 - _banner_t) / 0.6, 0.0, 1.0) if _banner_t > 0 else 0.0
	banner.modulate.a = ba if hud_visible else 0.0


static func _ease(t: float) -> float:
	return t * t * (3.0 - 2.0 * t)
