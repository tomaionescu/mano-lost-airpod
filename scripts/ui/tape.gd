class_name Tape
extends Control
## A strip of masking tape (docs/DESIGN.md §5.2: #EFE6CF at 80 %), torn off the roll by hand at both ends, its long
## edges nearly straight, with the paper fibre in it and a faint shadow. It sticks pages, photos and stickers
## down; seeded, so a strip is the same on every run. Its origin is its centre, so `rotation` turns it in place.

const PAPER_SHADER := preload("res://scripts/fx/paper.gdshader")

var length := 110.0
var width := 32.0
var color := UITheme.TAPE
var seed_value := 1
var _shape := PackedVector2Array()


## A strip `length` long centred on `at` in `parent`, turned `angle_deg`.
static func stick(parent: Control, at: Vector2, length_units := 110.0, angle_deg := 0.0, s := 1, width_units := 32.0) -> Tape:
	var t := Tape.new()
	t.length = length_units
	t.width = width_units
	t.seed_value = s
	t.position = at
	t.rotation_degrees = angle_deg
	parent.add_child(t)
	return t


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	var m := ShaderMaterial.new()
	m.shader = PAPER_SHADER
	m.set_shader_parameter("grain", float(seed_value % 53) + 7.0)
	material = m
	_build()


func _build() -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = seed_value * 104729 + 5
	var hl := length * 0.5
	var hw := width * 0.5
	_shape = PackedVector2Array()
	for i in 9:   # top edge, left to right
		_shape.append(Vector2(lerpf(-hl + 4.0, hl - 4.0, i / 8.0), -hw + rng.randf_range(-0.5, 0.5)))
	for i in 7:   # the right end, torn: a little zigzag
		_shape.append(Vector2(hl - 4.0 + (4.5 if i % 2 == 0 else 0.0) + rng.randf_range(-1.4, 1.4), lerpf(-hw, hw, (i + 0.5) / 7.0)))
	for i in 9:   # bottom edge, right to left
		_shape.append(Vector2(lerpf(hl - 4.0, -hl + 4.0, i / 8.0), hw + rng.randf_range(-0.5, 0.5)))
	for i in 7:   # the left end
		_shape.append(Vector2(-hl + 4.0 - (4.5 if i % 2 == 0 else 0.0) + rng.randf_range(-1.4, 1.4), lerpf(hw, -hw, (i + 0.5) / 7.0)))
	queue_redraw()


func _draw() -> void:
	if _shape.size() < 3:
		return
	var n := _shape.size()
	draw_polygon(ObjectiveStrip._shifted(_shape, Vector2(1.0, 1.8)), PackedColorArray([Color(UITheme.INK_SHADOW, 0.14)]), ObjectiveStrip._uv(n, Vector2.ZERO))
	draw_polygon(_shape, PackedColorArray([color]), ObjectiveStrip._uv(n, Vector2(0, 1)))
	# the crepe of the tape: faint lines across it
	var crepe := Color(0.55, 0.48, 0.34, 0.06)
	var x := -length * 0.5 + 6.0
	var rng := RandomNumberGenerator.new()
	rng.seed = seed_value
	while x < length * 0.5 - 6.0:
		draw_line(Vector2(x, -width * 0.5 + 1.5), Vector2(x + 1.2, width * 0.5 - 1.5), crepe, 1.0)
		x += rng.randf_range(2.2, 4.0)
