class_name PenStyle
extends StyleBox
## A hand-drawn pen mark as a StyleBox, for Mano's notebook UI (docs/DESIGN.md §5): an underline, a loop round the
## content ("circle the answer") or a sketched box (key caps). The wobble is seeded from `mark_seed` and the box
## size, so a mark is the same on every frame and every run; `progress` draws it on from 0 to 1.

enum Kind { UNDERLINE, LOOP, BOX }

var kind := Kind.UNDERLINE
var color := Color("#d23a2c")
var width := 2.5
## A darker stroke under the ink so the mark reads over a pale sky; transparent on paper.
var shadow := Color(0.07, 0.055, 0.04, 0.6)
var mark_seed := 1
var progress := 1.0:
	set(v):
		progress = clampf(v, 0.0, 1.0)
		emit_changed()


static func make(k: Kind, c: Color, w := 2.5, s := 1, margins := Vector2(0, 0)) -> PenStyle:
	var p := PenStyle.new()
	p.kind = k
	p.color = c
	p.width = w
	p.mark_seed = s
	p.content_margin_left = margins.x
	p.content_margin_right = margins.x
	p.content_margin_top = margins.y
	p.content_margin_bottom = margins.y
	return p


func _draw(to_canvas_item: RID, rect: Rect2) -> void:
	if progress <= 0.0:
		return
	var pts := path(rect)
	var n := clampi(int(ceil(pts.size() * progress)), 2, pts.size())
	if n < pts.size():
		pts = pts.slice(0, n)
	if shadow.a > 0.0:
		RenderingServer.canvas_item_add_polyline(to_canvas_item, pts, PackedColorArray([shadow]), width + 2.2, true)
	RenderingServer.canvas_item_add_polyline(to_canvas_item, pts, PackedColorArray([color]), width, true)


## The stroke as a polyline in the order a hand draws it.
func path(r: Rect2) -> PackedVector2Array:
	var rng := RandomNumberGenerator.new()
	rng.seed = mark_seed * 7919 + int(r.size.x) * 31 + int(r.size.y)
	var ph := PackedFloat32Array([rng.randf() * TAU, rng.randf() * TAU, rng.randf() * TAU])
	var pts := PackedVector2Array()
	match kind:
		Kind.UNDERLINE:
			# a quick stroke under the words, slightly rising, with a small flick at the end
			var x0 := r.position.x + content_margin_left * 0.5 - 3.0
			var x1 := r.end.x - content_margin_right * 0.5 + 4.0
			var y := r.end.y - maxf(content_margin_bottom * 0.45, 2.0)
			var steps := 18
			for i in steps + 1:
				var t := float(i) / steps
				var wob := 1.1 * sin(t * 5.0 + ph[0]) + 0.6 * sin(t * 11.0 + ph[1])
				pts.append(Vector2(lerpf(x0, x1, t), y + wob - t * 2.5))
			pts.append(pts[pts.size() - 1] + Vector2(5.0, -4.0))
		Kind.LOOP:
			# an oval round the content, started at the lower left and closed with an overshoot
			var c := r.get_center()
			var rx := r.size.x * 0.5 + 9.0
			var ry := r.size.y * 0.5 + 3.0
			var tilt := deg_to_rad(rng.randf_range(-2.5, 1.0))
			var a0 := 2.3 + rng.randf_range(-0.15, 0.15)
			var steps := 44
			for i in steps + 1:
				var t := float(i) / steps
				var a := a0 + t * TAU * 1.09
				var k := 1.0 + 0.045 * sin(a * 2.0 + ph[0]) + 0.025 * sin(a * 3.0 + ph[1]) + t * 0.05
				var p := Vector2(cos(a) * rx * k, sin(a) * ry * k).rotated(tilt)
				pts.append(c + p)
		Kind.BOX:
			# four slightly bent sides drawn in one go, corners overshooting a little
			var g := r.grow(-1.0)
			var corners := [g.position, Vector2(g.end.x, g.position.y), g.end, Vector2(g.position.x, g.end.y), g.position]
			for s in 4:
				var a: Vector2 = corners[s]
				var b: Vector2 = corners[s + 1]
				var nrm := (b - a).orthogonal().normalized()
				for i in 9:
					var t := float(i) / 8.0
					var bend := sin(t * PI) * 1.2 * sin(ph[s % 3] + s)
					pts.append(a.lerp(b, t) + nrm * bend + (b - a).normalized() * (2.0 if i == 8 else 0.0))
	return pts
