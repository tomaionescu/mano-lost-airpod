extends Node
## The sound search (chapter 4, V2-26, docs/DESIGN.md §3.10): the right AirPod is somewhere in the Under, in fact between
## the old sofa's cushions (world.json findmy_pod), and the BDE's sound check thumps through the room. Mano walks
## about freely (the follow camera, his own feet) with the finder open on his phone: Q (the phone key) or the
## d-pad makes the AirPod ring, a 3D chirp from where it is, with a 4 s cooldown; his phone is at 10 %, five rings.
## A ring timed between two thumps is clear, and the phone's five-step signal bar says how close he is (for
## players who cannot hear it); a ring under a thump is drowned out. E digs in the cushions once he is close. If the
## battery runs out, Cristina's phone takes over; Cristina says "Shh. Near the sofa." after a few rings or 40 s,
## and the AirPod catches the light after 70 s: nobody is stuck. Ends with _done.call(true) when it is found
## (the story autotest calls that too).

const CHIRP := "res://assets/audio/sfx/airpod_chirp.ogg"
const THUMP := "res://assets/audio/sfx/soundcheck_thump.ogg"
const COOLDOWN := 4.0
const RINGS := 5               # 10 % battery, 2 % a ring
const THUMP_EVERY := 1.7       # the sound check's kick
const MASK := 0.42             # a ring that starts this close to a thump is drowned out
const FIND_R := 1.7            # metres from the AirPod (flat) where E digs in the cushions
const HINT_AFTER_RINGS := 3
const HINT_AFTER := 40.0
const GLINT_AFTER := 70.0
const SPEAKER := Vector3(24.6, -2.0, 46.0)   # the BDE's speaker by the bar (the thumps come from there)

var game
var _done: Callable
var pod_pos := Vector3.ZERO
var rings_left := RINGS
var rings := 0                 # rings played, clear or drowned (autotests read it)
var clear_rings := 0
var signal_now := 0            # 0..5, the last clear ring's reading
var found := false
var borrowed := false          # Cristina's phone after the battery ran out
var _t := 0.0
var _cool := 0.0
var _thump_t := 0.6
var _since_thump := 9.0
var _sig_show := 0.0
var _masked_show := 0.0
var _hinted := false
var _glint: OmniLight3D = null
var _chirp: AudioStreamPlayer3D
var _thump: AudioStreamPlayer3D
var _layer: CanvasLayer
var _card: Control
var _batt: Label
var _status: Label
var _dig: Label
var _bars: Control


func setup(g, _opts: Dictionary, done: Callable) -> void:
	game = g
	_done = done
	var p := WorldData.point("findmy_pod")
	pod_pos = p.pos if not p.is_empty() else Vector3(4.45, -3.2, 42.25)
	# Mano walks: the minigame takes no control from him but the phone's
	game.player.frozen = false
	game.camera_rig.input_enabled = true
	game.camera_rig.clear_shot(true)
	var e := WorldData.point("under_entry")
	if not e.is_empty() and game.player.global_position.distance_to(e.pos) < 6.0:
		# on the mark inside the door, facing the room: where the scene leaves him (facing Cristina) the follow camera
		# behind him is out past the door, filming the wall; the sofa is round a corner, so facing it does not help
		game.player.teleport(e.pos, e.yaw)
	game.camera_rig.snap_behind(game.player.facing_yaw())
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	Sfx.music("", -60.0, 0.5, 1.5)   # the sound check is the only music here
	_chirp = AudioStreamPlayer3D.new()
	_chirp.stream = load(CHIRP) if ResourceLoader.exists(CHIRP) else null
	_chirp.bus = "SFX"
	_chirp.unit_size = 3.0
	_chirp.max_distance = 36.0
	_chirp.volume_db = 4.0
	add_child(_chirp)
	_chirp.global_position = pod_pos
	_thump = AudioStreamPlayer3D.new()
	_thump.stream = load(THUMP) if ResourceLoader.exists(THUMP) else null
	_thump.bus = "SFX"
	_thump.unit_size = 14.0
	_thump.max_distance = 60.0
	_thump.volume_db = 2.0
	add_child(_thump)
	_thump.global_position = SPEAKER
	_build_ui()
	print("[findmy] the AirPod at %s, Mano %.1f m from it, %d rings" % [pod_pos, _dist(), rings_left])


func _dist() -> float:
	var m: Vector3 = game.player.global_position
	return Vector2(m.x - pod_pos.x, m.z - pod_pos.z).length()


## The five-step signal: 5 within 2 m, 4 within 4, 3 within 7, 2 within 11, else 1.
func signal_for(d: float) -> int:
	if d < 2.0:
		return 5
	if d < 4.0:
		return 4
	if d < 7.0:
		return 3
	if d < 11.0:
		return 2
	return 1


func _build_ui() -> void:
	_layer = CanvasLayer.new()
	_layer.layer = 15
	add_child(_layer)
	var root := Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.theme = UITheme.theme
	_layer.add_child(root)
	# what to do, in Mano's pen over the scene
	var top := UITheme.over_scene(UITheme.label("Make it ring. Listen between the thumps.", 34, UITheme.pen, UITheme.FILM_WHITE), 7, 0.5) as Label
	top.set_anchors_preset(Control.PRESET_CENTER_TOP)
	top.grow_horizontal = Control.GROW_DIRECTION_BOTH
	top.offset_top = 44
	root.add_child(top)
	# the finder on his phone, bottom right: a generic device (Phone's colours), print inside
	_card = PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Phone.BODY
	sb.border_color = Phone.BEZEL
	sb.set_border_width_all(5)
	sb.set_corner_radius_all(26)
	sb.content_margin_left = 22
	sb.content_margin_right = 22
	sb.content_margin_top = 20
	sb.content_margin_bottom = 22
	sb.shadow_color = Color(0, 0, 0, 0.45)
	sb.shadow_size = 18
	_card.add_theme_stylebox_override("panel", sb)
	_card.custom_minimum_size = Vector2(300, 0)
	_card.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_card.set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)
	_card.grow_horizontal = Control.GROW_DIRECTION_BEGIN
	_card.grow_vertical = Control.GROW_DIRECTION_BEGIN
	_card.offset_right = -56
	_card.offset_bottom = -40
	root.add_child(_card)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 8)
	v.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_card.add_child(v)
	var head := HBoxContainer.new()
	head.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var title := UITheme.label("Find", 22, UITheme.print_700, UITheme.FILM_WHITE)
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(title)
	_batt = UITheme.label("10 %", 18, UITheme.print_500, Phone.LOW)
	head.add_child(_batt)
	v.add_child(head)
	v.add_child(UITheme.label("Right AirPod", 20, UITheme.print_700, UITheme.FILM_WHITE))
	_bars = Control.new()
	_bars.custom_minimum_size = Vector2(0, 54)
	_bars.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_bars.draw.connect(_draw_bars)
	v.add_child(_bars)
	_status = UITheme.label("Ring it to hear where it is.", 18, UITheme.print_400, Phone.DIM)
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_status.custom_minimum_size = Vector2(256, 0)
	v.add_child(_status)
	var keys := HBoxContainer.new()
	keys.add_theme_constant_override("separation", 10)
	keys.mouse_filter = Control.MOUSE_FILTER_IGNORE
	keys.add_child(UITheme.key_cap(UITheme.action_key("phone"), 16))
	keys.add_child(UITheme.label("play sound", 18, UITheme.print_500, UITheme.FILM_WHITE))
	v.add_child(keys)
	# the dig prompt, near the middle of the screen, once he is close
	_dig = UITheme.over_scene(UITheme.label("%s  dig in the cushions" % UITheme.action_key("interact"), 30, UITheme.marker, UITheme.FILM_WHITE), 7, 0.5) as Label
	_dig.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	_dig.grow_horizontal = Control.GROW_DIRECTION_BOTH
	_dig.offset_top = -280   # above the subtitles (Cristina's barks)
	_dig.offset_bottom = -240
	_dig.modulate.a = 0.0
	root.add_child(_dig)


## Five bars, filled to the last clear ring's reading; while a ring was drowned out, they flicker grey.
func _draw_bars() -> void:
	var w := 28.0
	var gap := 12.0
	var base := _bars.size.y - 4.0
	for i in 5:
		var h := 12.0 + i * 9.0
		var r := Rect2(Vector2(i * (w + gap), base - h), Vector2(w, h))
		var lit := _sig_show > 0.0 and i < signal_now
		var c := Phone.ACCENT if lit else Color(1, 1, 1, 0.14)
		if _masked_show > 0.0 and not lit:
			c = Color(1, 1, 1, 0.1 + 0.25 * absf(sin(_t * 18.0 + i)))
		_bars.draw_rect(r, c)


func ring() -> void:
	if found or _cool > 0.0:
		return
	if rings_left <= 0 and not borrowed:
		borrowed = true
		game.dialogue.bark("cristina", "Battery's dead? Use mine. Ringing it now.")
		_batt.text = "Cristina's"
		_batt.add_theme_color_override("font_color", Phone.ACCENT)
	_cool = COOLDOWN
	if not borrowed:
		rings_left -= 1
		_batt.text = "%d %%" % (rings_left * 2)
	rings += 1
	GameState.flags["findmy_chirps"] = rings
	# drowned out when it starts right on a thump (or one is due any moment)
	var masked := _since_thump < MASK or (THUMP_EVERY - _since_thump) < MASK * 0.5
	_chirp.volume_db = -14.0 if masked else 4.0
	if _chirp.stream:
		_chirp.play()
	var d := _dist()
	if masked:
		_masked_show = 2.0
		_status.text = "Drowned out by the bass. Wait for the gap."
	else:
		clear_rings += 1
		signal_now = signal_for(d)
		_sig_show = 3.0
		_status.text = ["", "Far. Somewhere in the room.", "Getting warmer.", "Close. This side of the room.", "Very close.", "Right here. In the cushions?"][signal_now]
	_bars.queue_redraw()
	print("[findmy] ring %d at %.1f s: %s, %.1f m, signal %d, rings left %d%s" % [rings, _t, "drowned" if masked else "clear", d,
		signal_now if not masked else 0, rings_left, " (Cristina's phone)" if borrowed else ""])
	if not _hinted and rings >= HINT_AFTER_RINGS:
		_hint()


func _hint() -> void:
	_hinted = true
	game.dialogue.bark("cristina", "Shh. Near the sofa.")


func dig() -> void:
	if found or _dist() > FIND_R:
		return
	found = true
	_dig.modulate.a = 0.0
	Sfx.play("pickup")
	_status.text = "Found."
	print("[findmy] found at %.1f s after %d rings (%d clear), %.2f m from it" % [_t, rings, clear_rings, _dist()])
	var tw := create_tween()
	tw.tween_interval(0.5)
	tw.tween_callback(func(): _done.call(true))


func _process(dt: float) -> void:
	if found:
		return
	_t += dt
	_cool = maxf(_cool - dt, 0.0)
	_sig_show = maxf(_sig_show - dt, 0.0)
	_masked_show = maxf(_masked_show - dt, 0.0)
	_since_thump += dt
	_thump_t -= dt
	if _thump_t <= 0.0:
		_thump_t = THUMP_EVERY
		_since_thump = 0.0
		if _thump.stream:
			_thump.play()
		game.camera_rig.add_trauma(0.02)
	if _sig_show > 0.0 or _masked_show > 0.0:
		_bars.queue_redraw()
	var near := _dist() <= FIND_R
	_dig.modulate.a = move_toward(_dig.modulate.a, 1.0 if near else 0.0, dt * 4.0)
	if not _hinted and _t > HINT_AFTER:
		_hint()
	if _glint == null and _t > GLINT_AFTER:
		# it catches the light: a small cold glint in the cushions, and Cristina says where
		_glint = OmniLight3D.new()
		_glint.light_color = Color(0.85, 0.92, 1.0)
		_glint.light_energy = 1.2
		_glint.omni_range = 0.9
		_glint.shadow_enabled = false
		add_child(_glint)
		_glint.global_position = pod_pos + Vector3.UP * 0.15
		game.dialogue.bark("cristina", "There. In the cushions. Something white.")
	if _glint:
		_glint.light_energy = 0.8 + 0.6 * absf(sin(_t * 3.0))


func _unhandled_input(event: InputEvent) -> void:
	if found:
		return
	if event.is_action_pressed("phone"):
		ring()
	elif event.is_action_pressed("interact"):
		dig()
	else:
		return
	get_viewport().set_input_as_handled()
