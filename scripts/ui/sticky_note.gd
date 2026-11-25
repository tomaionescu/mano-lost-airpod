class_name StickyNote
extends Control
## A sticky note in Mano's pen (docs/DESIGN.md §5.5, docs/ART_DIRECTION.md): a toast top-right, or a one-off
## control hint. A ballpoint doodle on the left (never an emoji), the words in Mynerve, keys as sketched caps
## round the live key letter. It lands with a small slide and turn while the doodle draws itself, holds, and
## peels away. The HUD stacks the notes by setting `base`.

signal gone

const PAPER_SHADER := preload("res://scripts/fx/paper.gdshader")
const W := 250.0            # the widest toast: 300 px at 1080p
const PAD := 13.0
const DOODLE := 34.0        # 40 px at 1080p
const GAP := 10.0           # between the doodle and the words
const SIZE := 25            # Mynerve, 30 px at 1080p
const KEY_SIZE := 18        # the key letter (Atkinson 700), 22 px at 1080p
const IN_T := 0.26
const OUT_T := 0.2

var text := ""
var doodle := ""
var paper := UITheme.STICKY_YELLOW
var base := Vector2.ZERO    # where the stack wants it; the note glides there
var leaving := false
var max_w := W              # a bigger note (a loading tip, the pause menu's tally) before the words wrap
var _rows: Array = []       # hint rows: [[key letters], words]
var _ink := UITheme.INK_BLUE
var _frame := 0
var _doodle_in := 0.0
var _ofs := Vector2.ZERO
var _turn := 0.0
var _rest := 0.0
var _at := Vector2.ZERO
var _placed := false
var _shape := PackedVector2Array()
var _w := W


## A toast: a doodle id from Doodles.IDS and a few handwritten words ("+1 €", "Noted").
static func toast(words: String, doodle_id: String, color := UITheme.STICKY_YELLOW) -> StickyNote:
	var n := StickyNote.new()
	n.text = words
	n.doodle = doodle_id
	n.paper = color
	return n


## A control hint: rows of [key letters, words], e.g. [[["Tab"], "my notebook"]].
static func hint(rows: Array, doodle_id: String, color := UITheme.STICKY_PINK) -> StickyNote:
	var n := StickyNote.new()
	n._rows = rows
	n.doodle = doodle_id
	n.paper = color
	return n


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	var m := ShaderMaterial.new()
	m.shader = PAPER_SHADER
	m.set_shader_parameter("grain", float(hash(text + doodle) & 0xFF))
	material = m
	var rng := RandomNumberGenerator.new()
	rng.seed = hash(text + doodle + str(_rows))
	_frame = rng.randi() % 3
	_rest = deg_to_rad(rng.randf_range(-1.6, 1.6))
	_build()
	pivot_offset = Vector2(size.x * 0.5, 0.0)   # it turns about its glued top edge


func _build() -> void:
	var left := PAD + (DOODLE + GAP if doodle != "" else 0.0)
	var content: Control
	if _rows.is_empty():
		# as wide as the words need (a short "+1 €" gets a small note), wrapping past 250
		var l := UITheme.label(text, SIZE, UITheme.pen, _ink)
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		var words := UITheme.pen.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, SIZE).x
		_w = clampf(left + words + PAD + 22.0, 170.0, max_w)
		l.custom_minimum_size = Vector2(_w - left - PAD, 0)
		l.size = l.custom_minimum_size   # an autowrapped label measures its height at its own width
		content = l
	else:
		var v := VBoxContainer.new()
		v.add_theme_constant_override("separation", 2)
		for row: Array in _rows:
			var line := HBoxContainer.new()
			line.add_theme_constant_override("separation", 5)
			for k: String in row[0]:
				line.add_child(paper_key(k))
			if String(row[1]) != "":
				if not (row[0] as Array).is_empty():
					var gap := Control.new()
					gap.custom_minimum_size = Vector2(3, 0)
					line.add_child(gap)
				var l := UITheme.label(row[1], SIZE, UITheme.pen, _ink)
				l.size_flags_vertical = Control.SIZE_SHRINK_CENTER
				line.add_child(l)
			v.add_child(line)
		content = v
	content.position = Vector2(left, PAD - 2.0)
	content.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(content)
	if not _rows.is_empty():
		_w = maxf(left + content.get_combined_minimum_size().x + PAD + 8.0, 170.0)
	var h := maxf(content.get_combined_minimum_size().y + PAD * 2.0 - 4.0, DOODLE + PAD * 2.0)
	size = Vector2(_w, h)
	content.position.y = roundf((h - content.get_combined_minimum_size().y) * 0.5)
	# square die-cut paper; the bottom edge has curled up a little off the screen
	_shape = PackedVector2Array([Vector2(0, 0), Vector2(_w, 0), Vector2(_w, h - 2.6), Vector2(_w * 0.7, h - 0.2),
		Vector2(_w * 0.35, h + 0.3), Vector2(0, h)])


## A key cap sketched in ballpoint round the key letter, for notes on paper (UITheme.key_cap is for the scene).
static func paper_key(letter: String) -> PanelContainer:
	var p := PanelContainer.new()
	var sb := PenStyle.make(PenStyle.Kind.BOX, UITheme.INK_BLUE, 1.5, letter.length() + 3, Vector2(6, 0))
	sb.shadow = Color(0, 0, 0, 0)
	p.add_theme_stylebox_override("panel", sb)
	var l := UITheme.label(letter, KEY_SIZE, UITheme.print_700, UITheme.INK_BLUE)
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	l.custom_minimum_size = Vector2(14, 0)
	p.add_child(l)
	p.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	p.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return p


## Slides in 42 px (from the right unless `from` says otherwise) while turning from 3° to its resting angle.
func land(from := Vector2(35, 0)) -> void:
	var calm: bool = GameState.settings.get("reduce_motion", false)
	modulate.a = 0.0
	_ofs = Vector2.ZERO if calm else from
	_turn = _rest + (0.0 if calm else deg_to_rad(3.0 * signf(_rest + 0.0001)))
	_doodle_in = 1.0 if calm else 0.0
	# its first frame can be drawn before _process has run (a toast from a line that ends a conversation):
	# put it where the stack wants it now, not at the layer's top-left corner
	if not _placed:
		_at = base
		_placed = true
	position = _at + _ofs
	rotation = _turn
	var tw := create_tween().set_parallel()
	tw.tween_property(self, "modulate:a", 1.0, IN_T * 0.6)
	tw.tween_property(self, "_ofs", Vector2.ZERO, IN_T).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	tw.tween_property(self, "_turn", _rest, IN_T).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	if not calm:
		tw.tween_property(self, "_doodle_in", 1.0, 0.34).set_delay(0.1).set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)


## Peels off: a turn and a lift from the bottom corner, then gone.
func peel() -> void:
	if leaving:
		return
	leaving = true
	var calm: bool = GameState.settings.get("reduce_motion", false)
	var tw := create_tween().set_parallel()
	tw.tween_property(self, "modulate:a", 0.0, OUT_T).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_IN)
	if not calm:
		tw.tween_property(self, "_ofs", Vector2(14, -12), OUT_T).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_IN)
		tw.tween_property(self, "_turn", _rest + deg_to_rad(7.0), OUT_T).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_IN)
	tw.chain().tween_callback(func():
		gone.emit()
		queue_free())


func _process(dt: float) -> void:
	if not _placed:
		_at = base
		_placed = true
	_at = _at.lerp(base, 1.0 - exp(-dt * 12.0))
	position = _at + _ofs
	rotation = _turn
	if _doodle_in < 1.0:
		queue_redraw()


func _draw() -> void:
	if _shape.size() < 3:
		return
	var h := size.y
	# the curl lifts the bottom off the screen, so the shadow is deeper there than under the glued top
	var sh1 := PackedVector2Array([Vector2(1.0, 1.5), Vector2(_w + 1.0, 1.5), Vector2(_w + 3.5, h + 3.0), Vector2(1.5, h + 5.0)])
	var sh2 := PackedVector2Array([Vector2(2.0, 3.0), Vector2(_w + 2.5, 3.0), Vector2(_w + 5.5, h + 6.5), Vector2(3.0, h + 9.0)])
	var none := PackedVector2Array([Vector2.ZERO, Vector2.ZERO, Vector2.ZERO, Vector2.ZERO])
	draw_polygon(sh2, PackedColorArray([Color(UITheme.INK_SHADOW, 0.1)]), none)
	draw_polygon(sh1, PackedColorArray([Color(UITheme.INK_SHADOW, 0.2)]), none)
	var fibre := PackedVector2Array()
	fibre.resize(_shape.size())
	fibre.fill(Vector2(0, 1))
	draw_polygon(_shape, PackedColorArray([paper]), fibre)
	# a little less light on the curled bottom
	var band := PackedVector2Array([Vector2(0, h * 0.62), Vector2(_w, h * 0.62), Vector2(_w, h - 2.6), Vector2(0, h)])
	draw_polygon(band, PackedColorArray([Color(0, 0, 0, 0), Color(0, 0, 0, 0), Color(0.3, 0.22, 0, 0.07), Color(0.3, 0.22, 0, 0.09)]), none)
	if doodle != "":
		var y := roundf((h - DOODLE) * 0.5)
		Doodles.draw(self, doodle, Rect2(PAD - 2.0, y, DOODLE, DOODLE), Doodles.ink(doodle), 2.0, _frame, Color(0, 0, 0, 0), _doodle_in)
