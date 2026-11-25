class_name PaperSheet
extends Control
## A sheet of paper as a Control (docs/DESIGN.md §5, docs/ART_DIRECTION.md): a page of Mano's Seyès notebook,
## a sheet of his 5 mm algo pad or a printed school sheet, drawn as one polygon with scripts/fx/paper.gdshader
## (fibre, ruling and the red margin, sharp at any scale and on Retina), its edges cut, torn or perforated, a
## soft shadow under it and a corner that can curl up. Seeded: a sheet is the same on every run. Children (text,
## tape, stickers) are laid out on it in its own units; the ruling is measured from its top-left corner.

const PAPER_SHADER := preload("res://scripts/fx/paper.gdshader")

enum Ruling { SEYES, SQUARES, PLAIN }
enum Edge { CUT, TORN, PERFORATED }

var ruling := Ruling.SEYES:
	set(v):
		ruling = v
		_sync()
## Seyès violet line spacing (8 mm) in canvas units; the squares are 5/8 of it.
var row := 40.0:
	set(v):
		row = v
		_sync()
## y of the first violet line (handwriting sits on the violet lines).
var first_line := 40.0:
	set(v):
		first_line = v
		_sync()
## x of the red margin line; negative: no margin.
var margin_x := 80.0:
	set(v):
		margin_x = v
		_sync()
var paper := UITheme.PAPER
## Top, right, bottom and left edges.
var edges: Array = [Edge.CUT, Edge.CUT, Edge.CUT, Edge.CUT]
## Punched holes down the left edge, as on a sheet from a ring binder (0, 2 or 4).
var holes := 0
## How far the sheet stands off whatever is under it (1: lying flat on a desk).
var lift := 1.0
## The bottom-right corner curling up (0-1): the paper there catches more light and its shadow deepens.
var curl := 0.0
var seed_value := 1

var _outline := PackedVector2Array()
var _built_for := Vector2.ZERO


func _init() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	var m := ShaderMaterial.new()
	m.shader = PAPER_SHADER
	material = m
	_sync()


func _notification(what: int) -> void:
	if what == NOTIFICATION_RESIZED:
		queue_redraw()


func _sync() -> void:
	var m := material as ShaderMaterial
	if m == null:
		return
	m.set_shader_parameter("row", row)
	m.set_shader_parameter("first_line", first_line)
	m.set_shader_parameter("margin_x", margin_x)
	m.set_shader_parameter("margin", margin_x >= 0.0)
	m.set_shader_parameter("ruling", 1 if ruling == Ruling.SQUARES else 0)
	m.set_shader_parameter("square", row * 0.625)
	m.set_shader_parameter("grain", float(seed_value % 97))
	queue_redraw()


## y of the violet line `n` (0 = the first one): where handwriting on line n sits.
func line_y(n: int) -> float:
	return first_line + row * n


## Places `content` on the sheet at `pad` (left, top) and sizes the sheet to it plus `pad_end` (right, bottom),
## following it when it grows.
func wrap(content: Control, pad: Vector2, pad_end: Vector2) -> void:
	content.position = pad
	if content.get_parent() != self:
		add_child(content)
	var fit := func() -> void:
		var s := content.get_combined_minimum_size()
		custom_minimum_size = pad + s + pad_end
		size = custom_minimum_size
	content.minimum_size_changed.connect(fit)
	fit.call()


## Paper drawn over this sheet's own children across `r`, from transparent at the top of `r` to opaque at its
## bottom, with the sheet's material in the sheet's units, so its fibre matches exactly: text scrolling under it
## fades into the same paper instead of being sliced at the window's edge. Add it after the content.
func paper_over(r: Rect2) -> Control:
	var c := Control.new()
	c.mouse_filter = Control.MOUSE_FILTER_IGNORE
	c.use_parent_material = true
	c.draw.connect(func():
		var pts := PackedVector2Array([r.position, Vector2(r.end.x, r.position.y), r.end, Vector2(r.position.x, r.end.y)])
		var cols := PackedColorArray()
		for i in 4:
			var col := _shade(pts[i])
			col.a = 0.0 if i < 2 else 1.0
			cols.append(col)
		c.draw_polygon(pts, cols, _uvs(4, Vector2(0.0, 1.0))))
	add_child(c)
	return c


func _draw() -> void:
	if size.x < 4.0 or size.y < 4.0:
		return
	if _built_for != size:
		_outline = _shape()
		_built_for = size
	var n := _outline.size()
	var flat := _uvs(n, Vector2.ZERO)
	# the shadow: wider and softer the higher the sheet stands, deeper under a curled corner
	if lift > 0.0:
		var far := Vector2(3.0, 5.5) * lift
		var near := Vector2(1.2, 2.0) * lift
		draw_polygon(_offset(_outline, far, curl * 5.0), PackedColorArray([Color(UITheme.INK_SHADOW, 0.12)]), flat)
		draw_polygon(_offset(_outline, near, curl * 2.0), PackedColorArray([Color(UITheme.INK_SHADOW, 0.2)]), flat)
	var cols := PackedColorArray()
	cols.resize(n)
	for i in n:
		cols[i] = _shade(_outline[i])
	draw_polygon(_outline, cols, _uvs(n, Vector2(0.0 if ruling == Ruling.PLAIN else 1.0, 1.0)))
	# punched holes: what is under the sheet shows through, darker on the side the light comes from
	for i in holes:
		var y := size.y * (0.5 + (float(i) - (holes - 1) * 0.5) * (0.22 if holes > 2 else 0.5))
		var c := Vector2(22.0, y)
		var ring := PackedVector2Array()
		var dark := PackedVector2Array()
		for k in 24:
			var a := TAU * k / 24.0
			ring.append(c + Vector2(cos(a), sin(a)) * 7.8)
			dark.append(c + Vector2(cos(a), sin(a)) * 6.6 + Vector2(0.6, 0.9))
		draw_polygon(ring, PackedColorArray([UITheme.PAPER_SHADE]), _uvs(24, Vector2.ZERO))
		draw_polygon(dark, PackedColorArray([Color(UITheme.INK_SHADOW, 0.62)]), _uvs(24, Vector2.ZERO))


## Paper colour at a point: a little shade toward the bottom, light on a curled corner.
func _shade(p: Vector2) -> Color:
	var k := clampf((p.y / maxf(size.y, 1.0)) * 0.035, 0.0, 0.035)
	var c := paper.darkened(k)
	if curl > 0.0:
		var d := clampf(1.0 - (size - p).length() / (minf(size.x, size.y) * 0.35), 0.0, 1.0)
		c = c.lerp(Color(1, 1, 1, paper.a), d * curl * 0.6)
	return c


## The outline, clockwise from the top-left corner, each edge in its own style.
func _shape() -> PackedVector2Array:
	var rng := RandomNumberGenerator.new()
	rng.seed = seed_value * 7919 + 13
	var w := size.x
	var h := size.y
	var corners := [Vector2(0, 0), Vector2(w, 0), Vector2(w, h), Vector2(0, h)]
	var outs := [Vector2(0, -1), Vector2(1, 0), Vector2(0, 1), Vector2(-1, 0)]
	var pts := PackedVector2Array()
	for side in 4:
		var a: Vector2 = corners[side]
		var b: Vector2 = corners[(side + 1) % 4]
		var out: Vector2 = outs[side]
		var edge: int = edges[side]
		var length := a.distance_to(b)
		match edge:
			Edge.TORN:
				var steps := maxi(int(length / 3.4), 2)
				var walk := 0.0
				for i in steps:
					var t := float(i) / steps
					walk = clampf(walk * 0.6 + rng.randf_range(-1.0, 1.0) * 1.3, -1.8, 1.8)
					if rng.randf() < 0.05:
						walk -= 1.8   # a little bite out of the edge
					pts.append(a.lerp(b, t) + out * walk)
			Edge.PERFORATED:
				# torn off a pad along its perforation: a row of small tabs left by the holes
				var pitch := 9.0
				var steps := maxi(int(length / pitch), 2)
				for i in steps:
					var t := float(i) / steps
					var p := a.lerp(b, t)
					var dir := (b - a) / length
					pts.append(p)
					pts.append(p + dir * pitch * 0.3 + out * (1.4 + rng.randf() * 0.6))
					pts.append(p + dir * pitch * 0.7 + out * (1.4 + rng.randf() * 0.6))
			_:
				# a guillotine cut: straight, with the faint waver of a blade through a stack
				var steps := maxi(int(length / 60.0), 2)
				for i in steps:
					var t := float(i) / steps
					pts.append(a.lerp(b, t) + out * (rng.randf_range(-0.25, 0.25) if i > 0 else 0.0))
	return pts


static func _offset(pts: PackedVector2Array, d: Vector2, grow: float) -> PackedVector2Array:
	var out := pts.duplicate()
	if out.is_empty():
		return out
	var c := Vector2.ZERO
	for p in out:
		c += p
	c /= out.size()
	for i in out.size():
		out[i] += d + (out[i] - c).normalized() * grow * 0.3
	return out


static func _uvs(n: int, v: Vector2) -> PackedVector2Array:
	var out := PackedVector2Array()
	out.resize(n)
	out.fill(v)
	return out
