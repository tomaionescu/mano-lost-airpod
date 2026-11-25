class_name NotebookCover
extends Control
## Mano's algo notebook closed (docs/DESIGN.md §5.5: the loading screen and the pause menu): a cahier in a plastic
## polypropylene cover, the hinge crease down its left edge, a faint sheen, and a white school étiquette whose
## printed fields Mano filled in by hand ("Nom : Mano", "Matière : retrouver mon AirPod"). Blank étiquette
## lines below the fields take whatever is written there (the pause menu); line_y() says where.

const PAPER_SHADER := preload("res://scripts/fx/paper.gdshader")
const FIELD_SIZE := 18      # the printed field names: Atkinson 500, 22 px at 1080p
const VALUE_SIZE := 30      # Mano's pen: Mynerve, 36 px at 1080p
const NBSP := " "     # French typography: a no-break space before the colon

var cover_color := Color("#2b5a7a")
## [printed field, what Mano wrote]
var fields: Array = [["Nom", "Mano"], ["Matière", "retrouver mon AirPod"]]
## Blank lines on the étiquette under the fields.
var blank_lines := 0
var line_h := 50.0
## Where the étiquette's middle sits, as a fraction of the cover's height.
var label_center := 0.5
var seed_value := 4
## The étiquette, in the cover's units (set when the cover is laid out).
var label_rect := Rect2()
var _values: Array[Label] = []
var _ink: Control


func _init() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	var m := ShaderMaterial.new()
	m.shader = PAPER_SHADER
	m.set_shader_parameter("grain", 23.0)
	material = m


func _ready() -> void:
	_layout()
	resized.connect(_layout)


## y of étiquette line `i` (0 = the first field), in the cover's units: the line text sits on.
func line_y(i: int) -> float:
	return label_rect.position.y + 46.0 + line_h * i


## The handwritten value labels (one per field), for writing them on.
func values() -> Array[Label]:
	return _values


func _layout() -> void:
	var lw := size.x * 0.84
	var lh := 46.0 + line_h * (fields.size() + blank_lines) - line_h * 0.35
	label_rect = Rect2(Vector2((size.x - lw) * 0.5 + 6.0, size.y * label_center - lh * 0.5), Vector2(lw, lh))
	for c in get_children():
		if c.has_meta("cover_part"):
			c.queue_free()
	_values.clear()
	var x0 := label_rect.position.x + 22.0
	for i in fields.size():
		var f: Array = fields[i]
		var field := UITheme.label(String(f[0]) + NBSP + ":", FIELD_SIZE, UITheme.print_500, Color(UITheme.INK_BLACK, 0.8))
		var fw := UITheme.print_500.get_string_size(field.text, HORIZONTAL_ALIGNMENT_LEFT, -1, FIELD_SIZE).x
		field.position = Vector2(x0, line_y(i) - UITheme.print_500.get_ascent(FIELD_SIZE))
		_part(field)
		var v := UITheme.label(String(f[1]), VALUE_SIZE, UITheme.pen, UITheme.INK_BLUE)
		v.position = Vector2(x0 + fw + 12.0, line_y(i) - UITheme.pen.get_ascent(VALUE_SIZE) + 4.0)
		_part(v)
		_values.append(v)
	_ink = Control.new()
	_ink.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_ink.draw.connect(_draw_label_print)
	_part(_ink)
	move_child(_ink, 0)
	queue_redraw()


func _part(c: Control) -> void:
	c.set_meta("cover_part", true)
	c.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(c)


func _draw() -> void:
	var w := size.x
	var h := size.y
	if w < 10.0:
		return
	var none := ObjectiveStrip._uv(4, Vector2.ZERO)
	# lying on the desk: a soft double shadow
	for k: Array in [[Vector2(5, 9), 0.16], [Vector2(2, 3.5), 0.24]]:
		var d: Vector2 = k[0]
		draw_polygon(_rect_pts(Rect2(d, size), 5.0), PackedColorArray([Color(UITheme.INK_SHADOW, k[1])]), ObjectiveStrip._uv(_rect_pts(Rect2(d, size), 5.0).size(), Vector2.ZERO))
	# the cover, a little lighter toward the top where the light falls; the plastic's grain is the fibre
	var outline := _rect_pts(Rect2(Vector2.ZERO, size), 5.0)
	var cols := PackedColorArray()
	for p in outline:
		cols.append(cover_color.lightened(0.06 * (1.0 - p.y / h)).darkened(0.08 * p.x / w))
	draw_polygon(outline, cols, ObjectiveStrip._uv(outline.size(), Vector2(0, 1)))
	# the sheen of the plastic: a broad soft diagonal band
	var band := PackedVector2Array([Vector2(w * 0.18, 0), Vector2(w * 0.5, 0), Vector2(w * 0.05, h * 0.62), Vector2(0, h * 0.62), Vector2(0, h * 0.45)])
	draw_polygon(band, PackedColorArray([Color(1, 1, 1, 0.0), Color(1, 1, 1, 0.07), Color(1, 1, 1, 0.0), Color(1, 1, 1, 0.0), Color(1, 1, 1, 0.03)]), ObjectiveStrip._uv(5, Vector2.ZERO))
	# the hinge crease down the left, and the folded rim of the plastic
	draw_line(Vector2(17, 4), Vector2(17, h - 4), Color(cover_color.darkened(0.35), 0.8), 2.0, true)
	draw_line(Vector2(19.5, 4), Vector2(19.5, h - 4), Color(1, 1, 1, 0.12), 1.5, true)
	outline.append(outline[0])
	draw_polyline(outline, cover_color.darkened(0.3), 1.6, true)
	# the étiquette: a white self-adhesive school label, its corners die-cut round
	var lr := label_rect
	var lab := _rect_pts(lr, 8.0)
	draw_polygon(_shift(lab, Vector2(1.2, 2.0)), PackedColorArray([Color(UITheme.INK_SHADOW, 0.25)]), ObjectiveStrip._uv(lab.size(), Vector2.ZERO))
	draw_polygon(lab, PackedColorArray([Color("#fdfcf8")]), ObjectiveStrip._uv(lab.size(), Vector2(0, 1)))


## What is printed on the étiquette: its double frame and the dotted lines Mano writes on.
func _draw_label_print() -> void:
	var lr := label_rect
	var frame := Color("#3d5fa8")
	var f1 := _rect_pts(lr.grow(-7.0), 5.0)
	f1.append(f1[0])
	_ink.draw_polyline(f1, Color(frame, 0.85), 1.6, true)
	var f2 := _rect_pts(lr.grow(-10.5), 3.5)
	f2.append(f2[0])
	_ink.draw_polyline(f2, Color(frame, 0.55), 0.8, true)
	for i in fields.size() + blank_lines:
		var y := line_y(i) + 6.0
		var x := lr.position.x + 22.0
		var x1 := lr.end.x - 22.0
		if i < fields.size():
			x += UITheme.print_500.get_string_size(String(fields[i][0]) + NBSP + ":", HORIZONTAL_ALIGNMENT_LEFT, -1, FIELD_SIZE).x + 6.0
		while x < x1:
			_ink.draw_line(Vector2(x, y), Vector2(minf(x + 1.6, x1), y), Color(frame, 0.55), 1.3, true)
			x += 5.0


## A rectangle with its corners rounded by `r`, clockwise from the top-left.
static func _rect_pts(r: Rect2, rad: float) -> PackedVector2Array:
	var pts := PackedVector2Array()
	var cs := [[r.position + Vector2(rad, rad), PI], [Vector2(r.end.x - rad, r.position.y + rad), PI * 1.5],
		[r.end - Vector2(rad, rad), 0.0], [Vector2(r.position.x + rad, r.end.y - rad), PI * 0.5]]
	for c: Array in cs:
		for i in 5:
			var a: float = c[1] + float(i) / 4.0 * PI * 0.5
			pts.append(c[0] + Vector2(cos(a), sin(a)) * rad)
	return pts


static func _shift(pts: PackedVector2Array, d: Vector2) -> PackedVector2Array:
	return ObjectiveStrip._shifted(pts, d)
