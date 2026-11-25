extends Node3D
## The lost & found box (V2-23, the twist): five joke AirPods to inspect up close, and an empty slot with a sticky
## note: "Took the M one to find its owner. — C." Mano's is not there: no pod is the right one, by design.
## Reading the note ends it (the story's c2.twist sets lf_twist). After three wrong picks Mme Dupont points at the
## empty slot. The note is set in the pen font, in Cristina's ink.

const PODS := [
	{"m": true, "desc": "A little M scratched on it. The stem is spotless.", "wrong": "That one belongs to a SPE student who doesn't chew things. Respectable."},
	{"w": true, "chew": true, "desc": "A chewed stem, and a W scratched on the bud.", "wrong": "That's a W, Mano. Did you sleep through the alphabet too?"},
	{"slot": true, "desc": "An empty slot in the felt. A sticky note in blue-green ink.", "read": true},
	{"s42": true, "chew": true, "desc": "A chewed stem with a \"42\" sticker on it.", "wrong": "A 42 sticker? Mano. Have some respect for your school."},
	{"acu": true, "desc": "A label on the stem: PROPERTY OF THE ACUs.", "wrong": "Touch that and the ACUs will give you -42. For life."},
	{"gold": true, "desc": "Gold-plated. Engraved: DIRECTION.", "wrong": "That's the director's. Put it DOWN. Slowly."},
]
## C.'s note (docs/DESIGN.md §3.5), in Cristina's ink.
const NOTE_TEXT := "Took the M one\n(chewed stem!)\nto find its owner.\nIf it's yours: I'm\nlooking for you!\n— C."
const NOTE_TIME := "18:10"
const NOTE_INK := Color("#1a6f86")
const NUDGE_AFTER := 3     # wrong picks before Mme Dupont points at the empty slot
const SPACING := 0.065

var game
var _done: Callable
var _items: Array = []
var _sel := 0
var _rejected := {}
var _won := 0.0
var _desc: Label
var _reply: Label
var _reply_t := 0.0
var _t := 0.0
var _white: StandardMaterial3D
var _chewed: StandardMaterial3D
var _goldm: StandardMaterial3D
var _note: Control          # the note, readable, when the slot is picked
var _note_a := 0.0
var _read := false
var _wrong := 0
var _hint: Label


func setup(g, _opts: Dictionary, done: Callable) -> void:
	game = g
	_done = done
	var a: Dictionary = game.binder.anchors.get("lostfound", {})
	var pos: Vector3 = a.get("pos", game.player.global_position + Vector3(0, 1.0, -0.6))
	var yaw: float = a.get("yaw", game.player.facing_yaw())
	global_position = pos
	rotation.y = yaw
	# Mano stands just behind the camera, facing the tray
	var back := Vector3(sin(yaw), 0, cos(yaw))
	var floor_y: float = game.player.global_position.y
	game.player.teleport(Vector3(pos.x, floor_y, pos.z) + back * 1.15, yaw + PI)
	_white = StandardMaterial3D.new()
	_white.albedo_color = Color(0.965, 0.965, 0.955)
	_white.roughness = 0.16
	_white.clearcoat_enabled = true
	_white.clearcoat = 1.0
	_chewed = _white.duplicate()
	_chewed.albedo_color = Color(0.93, 0.91, 0.84)
	_chewed.roughness = 0.55
	_chewed.normal_enabled = true
	var nt := NoiseTexture2D.new()
	nt.as_normal_map = true
	nt.bump_strength = 6.0
	nt.noise = FastNoiseLite.new()
	nt.noise.frequency = 0.08
	_chewed.normal_texture = nt
	_chewed.normal_scale = 1.4
	_goldm = StandardMaterial3D.new()
	_goldm.albedo_color = Color(0.91, 0.73, 0.19)
	_goldm.metallic = 1.0
	_goldm.roughness = 0.2
	_build_tray()
	var order := range(PODS.size())
	order.shuffle()
	for i in order.size():
		var p: Dictionary = PODS[order[i]]
		var n := _make_slot() if p.get("slot", false) else _make_pod(p)
		n.position = Vector3((i - (PODS.size() - 1) * 0.5) * SPACING, 0.03, 0.0)
		add_child(n)
		_items.append({"def": p, "node": n})
	# steep view down onto the tray: the desk fills the background, nobody's chest does
	var from := to_global(Vector3(0.0, 0.36, 0.2))
	var look := to_global(Vector3(0.0, 0.02, -0.015))
	game.camera_rig.set_shot(from, look, 32.0, from.distance_to(look))
	_build_ui()
	_refresh()


func _build_tray() -> void:
	var wood := StandardMaterial3D.new()
	wood.albedo_color = Color("#c8a165")
	wood.roughness = 0.8
	var base := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = Vector3(0.44, 0.012, 0.16)
	base.mesh = bm
	base.material_override = wood
	base.position.y = 0.006
	add_child(base)
	var felt := StandardMaterial3D.new()
	felt.albedo_color = Color("#1f3a5f")
	felt.roughness = 1.0
	var pad := MeshInstance3D.new()
	var pm := BoxMesh.new()
	pm.size = Vector3(0.42, 0.004, 0.14)
	pad.mesh = pm
	pad.material_override = felt
	pad.position.y = 0.014
	add_child(pad)
	var lamp := SpotLight3D.new()
	lamp.position = Vector3(0.05, 0.45, 0.2)
	lamp.light_energy = 2.5
	lamp.spot_range = 1.2
	lamp.spot_angle = 35.0
	lamp.light_color = Color(1.0, 0.95, 0.88)
	lamp.shadow_enabled = true
	add_child(lamp)
	lamp.look_at(global_position)


## The empty slot: a hollow in the felt, and a small yellow sticky note on it with "C." in blue-green.
func _make_slot() -> Node3D:
	var root := Node3D.new()
	var hollow := MeshInstance3D.new()
	var hm := CylinderMesh.new()
	hm.top_radius = 0.012
	hm.bottom_radius = 0.011
	hm.height = 0.002
	hollow.mesh = hm
	var dark := StandardMaterial3D.new()
	dark.albedo_color = Color("#14263f")
	dark.roughness = 1.0
	hollow.material_override = dark
	hollow.position.y = -0.012
	root.add_child(hollow)
	var note := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = Vector3(0.034, 0.0008, 0.034)
	note.mesh = bm
	var paper := StandardMaterial3D.new()
	paper.albedo_color = UITheme.STICKY_YELLOW
	paper.roughness = 0.9
	note.material_override = paper
	note.position = Vector3(0.0, -0.009, 0.004)
	note.rotation.y = 0.22
	root.add_child(note)
	var l := Label3D.new()
	l.text = "C."
	l.font = UITheme.pen
	l.font_size = 64
	l.pixel_size = 0.00016
	l.modulate = NOTE_INK
	l.outline_size = 0
	l.rotation = Vector3(-PI / 2, 0.22, 0.0)
	l.position = Vector3(0.002, -0.0082, 0.006)
	root.add_child(l)
	return root


func _make_pod(p: Dictionary) -> Node3D:
	var root := Node3D.new()
	var body_mat := _goldm if p.get("gold", false) else _white
	var bud := MeshInstance3D.new()
	var sm := SphereMesh.new()
	sm.radius = 0.0105
	sm.height = 0.021
	bud.mesh = sm
	bud.scale = Vector3(1.0, 0.95, 1.1)
	bud.material_override = body_mat
	root.add_child(bud)
	var grille := MeshInstance3D.new()
	var gm := CylinderMesh.new()
	gm.top_radius = 0.0035
	gm.bottom_radius = 0.0035
	gm.height = 0.001
	grille.mesh = gm
	grille.rotation.x = PI / 2
	grille.position = Vector3(0, 0.002, 0.0112)
	var dark := StandardMaterial3D.new()
	dark.albedo_color = Color(0.08, 0.08, 0.09)
	dark.roughness = 0.7
	grille.material_override = dark
	root.add_child(grille)
	var stem := MeshInstance3D.new()
	var cm := CapsuleMesh.new()
	cm.radius = 0.0034
	cm.height = 0.034
	stem.mesh = cm
	stem.position = Vector3(0.0, -0.017, -0.004)
	stem.rotation.x = -0.25
	stem.material_override = _chewed if p.get("chew", false) else body_mat
	root.add_child(stem)
	var mark := ""
	var mark_col := Color(0.42, 0.45, 0.5)
	if p.get("m", false):
		mark = "M"
	elif p.get("w", false):
		mark = "W"
	elif p.get("gold", false):
		mark = "DIR"
		mark_col = Color(0.35, 0.25, 0.05)
	if mark != "":
		var l := Label3D.new()
		l.text = mark
		l.font = UITheme.bold
		l.font_size = 64
		l.pixel_size = 0.00011 if mark != "DIR" else 0.00007
		l.modulate = mark_col
		l.outline_size = 0
		l.position = Vector3(0.0075, 0.004, 0.006)
		l.rotation.y = 0.8
		root.add_child(l)
	if p.get("s42", false):
		var st := Label3D.new()
		st.text = "42"
		st.font = UITheme.bold
		st.font_size = 48
		st.pixel_size = 0.00012
		st.modulate = Color(1, 1, 1)
		st.outline_modulate = Color(0.1, 0.2, 0.6)
		st.outline_size = 22
		st.position = Vector3(0.0, -0.02, 0.0035)
		root.add_child(st)
	if p.get("acu", false):
		var tag := Label3D.new()
		tag.text = "PROPERTY OF\nTHE ACUs"
		tag.font = UITheme.bold
		tag.font_size = 32
		tag.pixel_size = 0.0001
		tag.modulate = Color(0.85, 0.12, 0.1)
		tag.position = Vector3(0.0, -0.022, 0.0036)
		root.add_child(tag)
	root.rotation = Vector3(-0.35, randf_range(-0.6, 0.6), 0.0)
	return root


func _build_ui() -> void:
	var layer := CanvasLayer.new()
	layer.layer = 15
	add_child(layer)
	var root := Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.theme = UITheme.theme
	layer.add_child(root)
	var top := UITheme.shadowed(UITheme.label("Lost & found - find YOUR AirPod", 40, UITheme.display_xb, UITheme.INK), 3, 0.6)
	top.anchor_left = 0.5
	top.anchor_right = 0.5
	top.offset_left = -500
	top.offset_right = 500
	top.offset_top = 48
	top.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	root.add_child(top)
	var box := VBoxContainer.new()
	box.anchor_left = 0.5
	box.anchor_right = 0.5
	box.anchor_top = 1.0
	box.anchor_bottom = 1.0
	box.offset_left = -520
	box.offset_right = 520
	box.offset_top = -200
	box.add_theme_constant_override("separation", 8)
	_desc = UITheme.shadowed(UITheme.label("", 32, UITheme.hand, UITheme.INK), 2, 0.7)
	_desc.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_desc.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	box.add_child(_desc)
	_reply = UITheme.shadowed(UITheme.label("", 26, UITheme.body_semi, Color("#a99bff")), 2, 0.7)
	_reply.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_reply.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	box.add_child(_reply)
	_hint = UITheme.shadowed(UITheme.label("", 18, UITheme.body_semi, UITheme.MUTED), 1, 0.6)
	_hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(_hint)
	root.add_child(box)
	_note = _build_note()
	root.add_child(_note)


## C.'s note as Mano reads it: a yellow sticky note, slanted, in Cristina's blue-green ink, the time in the corner.
func _build_note() -> Control:
	var c := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = UITheme.STICKY_YELLOW
	sb.set_corner_radius_all(2)
	sb.shadow_color = Color(UITheme.INK_SHADOW, 0.35)
	sb.shadow_size = 10
	sb.shadow_offset = Vector2(4, 7)
	sb.content_margin_left = 26
	sb.content_margin_right = 26
	sb.content_margin_top = 18
	sb.content_margin_bottom = 20
	c.add_theme_stylebox_override("panel", sb)
	c.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 2)
	var t := UITheme.label(NOTE_TIME, 20, UITheme.pen, NOTE_INK)
	t.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	v.add_child(t)
	var body := UITheme.label(NOTE_TEXT, 34, UITheme.pen, NOTE_INK)
	body.add_theme_constant_override("line_spacing", -4)
	v.add_child(body)
	c.add_child(v)
	c.custom_minimum_size = Vector2(330, 0)
	c.size = Vector2(330, 0)
	c.rotation = deg_to_rad(-4.0)
	c.modulate.a = 0.0
	return c


func _refresh() -> void:
	var d: Dictionary = _items[_sel].def
	_desc.text = d.desc
	_hint.text = "A / D  inspect      %s  %s" % [UITheme.action_key("confirm"), "read the note" if d.get("read", false) else "this one is mine"]
	Sfx.ui("ui_hover", -12.0)


## Picks the empty slot (Mme Dupont's nudge after three wrong ones).
func _select_slot() -> void:
	for i in _items.size():
		if _items[i].def.get("read", false):
			_sel = i
	_refresh()


func _unhandled_input(event: InputEvent) -> void:
	if _won > 0.0:
		return
	if event.is_action_pressed("move_left") or event.is_action_pressed("ui_left"):
		_sel = (_sel + _items.size() - 1) % _items.size()
		_refresh()
	elif event.is_action_pressed("move_right") or event.is_action_pressed("ui_right"):
		_sel = (_sel + 1) % _items.size()
		_refresh()
	elif event.is_action_pressed("confirm"):
		var d: Dictionary = _items[_sel].def
		if d.get("read", false):
			# the twist: the note is read, and that is the end of the box
			_read = true
			_won = 3.4
			_desc.text = "It's not here. Somebody took it."
			_reply.text = ""
			Sfx.play("pickup")
		else:
			_rejected[_sel] = true
			_wrong += 1
			_reply.text = "Mme Dupont: \"%s\"" % d.wrong
			_reply_t = 4.0
			Sfx.ui("ui_back")
			game.camera_rig.add_trauma(0.12)
			if _wrong >= NUDGE_AFTER:
				_reply.text = "Mme Dupont: \"What about the empty one, genius?\""
				_select_slot()
	else:
		return
	get_viewport().set_input_as_handled()


func _process(dt: float) -> void:
	_t += dt
	for i in _items.size():
		var n: Node3D = _items[i].node
		var lift := 0.045 if i == _sel else (0.0 if not _rejected.has(i) else -0.01)
		n.position.y = lerpf(n.position.y, 0.03 + lift, 1.0 - exp(-dt * 10.0))
		if i == _sel:
			n.rotation.y += dt * 0.9
			n.rotation.x = lerpf(n.rotation.x, -0.15 + sin(_t * 1.3) * 0.15, 1.0 - exp(-dt * 4.0))
		else:
			n.rotation.x = lerpf(n.rotation.x, -0.35, 1.0 - exp(-dt * 4.0))
	if _reply_t > 0.0:
		_reply_t -= dt
		if _reply_t <= 0.0:
			_reply.text = ""
	# C.'s note comes up over the tray while the slot is picked, and stays once it is read
	var want := 1.0 if _read or _items[_sel].def.get("read", false) else 0.0
	_note_a = move_toward(_note_a, want, dt / 0.25)
	var vp := _note.get_viewport_rect().size
	_note.size = _note.get_combined_minimum_size()
	_note.position = Vector2(vp.x * 0.5 - _note.size.x * 0.5 + (40.0 if _read else 230.0), vp.y * 0.17 + (1.0 - _note_a) * 18.0)
	_note.modulate.a = _note_a
	if _won > 0.0:
		_won -= dt
		if _won <= 0.0:
			_done.call(true)
