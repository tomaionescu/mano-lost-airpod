class_name Doodles
extends RefCounted
## Mano's ballpoint doodles (docs/DESIGN.md §5.4, docs/ART_DIRECTION.md): the icons on toasts and hint notes, the
## prompt ring and the waypoint, drawn as pen strokes in a 48-unit box with draw_polyline, so they stay sharp at
## any scale and on Retina. No image, no emoji, no generated art. The wobble of the hand comes from a seed: one
## seed draws the same doodle on every run, and seeds 0, 1, 2 cycled at 8 fps make a mark "boil".
## A scanned hand-drawn master saved as res://assets/ui/doodles/<id>.png (128 px, the ink as white on transparent,
## so the game can colour it) replaces the drawn one: the set can be redrawn by a real hand without touching code.

const BOX := 48.0
const MASTERS := "res://assets/ui/doodles/"
const IDS := ["pencil", "coin", "coffee", "airpod", "camera", "duck", "cross", "tick", "smile", "notebook", "map",
	"hoodie", "target", "arrow", "ring", "question", "heart", "star", "babyfoot", "phone", "music", "pin"]
## On paper most doodles are Mano's blue ballpoint; corrections and ticks are the red and green pens.
const INK := {"cross": Color("#c2302b"), "tick": Color("#1d7449"), "heart": Color("#c2302b"), "target": Color("#d23a2c")}

static var _cache := {}
static var _masters := {}


## The current boil drawing (0-2) at 8 fps, or 0 with Settings > Reduce motion.
static func boil() -> int:
	if GameState.settings.get("reduce_motion", false):
		return 0
	return int(Time.get_ticks_msec() / 125.0) % 3


## Ink for `id` on paper (blue unless the doodle has its own pen).
static func ink(id: String) -> Color:
	return INK.get(id, UITheme.INK_BLUE)


## Draws doodle `id` into `rect` (square) on `ci`, in `color`, `width` canvas units wide, turned by `rot`
## radians about the rect's centre. `frame` picks one of the hand's drawings (boil() cycles 0-2). `under` is an
## ink stroke under the line (over the 3D scene); `progress` draws it on from 0 to 1 in the order the hand draws it.
static func draw(ci: CanvasItem, id: String, rect: Rect2, color: Color, width := 2.0, frame := 0,
		under := Color(0, 0, 0, 0), progress := 1.0, rot := 0.0) -> void:
	if progress <= 0.0:
		return
	var tex := _master(id)
	if tex:
		ci.draw_set_transform(rect.get_center(), rot, Vector2.ONE)
		ci.draw_texture_rect(tex, Rect2(-rect.size * 0.5, rect.size), false, Color(color, color.a * clampf(progress * 3.0, 0.0, 1.0)))
		ci.draw_set_transform_matrix(Transform2D.IDENTITY)
		return
	var k := rect.size.x / BOX
	ci.draw_set_transform_matrix(Transform2D(rot, Vector2(k, k), 0.0, rect.get_center()) * Transform2D(0.0, Vector2(-BOX, -BOX) * 0.5))
	var w := width / k
	var lines := _clip(strokes(id, frame), progress)
	if under.a > 0.0:
		for pts: PackedVector2Array in lines:
			ci.draw_polyline(pts, under, w + 2.4 / k, true)
	for pts: PackedVector2Array in lines:
		ci.draw_polyline(pts, color, w, true)
	ci.draw_set_transform_matrix(Transform2D.IDENTITY)


## The doodle's strokes in the 48-unit box (y down), in drawing order. Cached per id and drawing (seed).
static func strokes(id: String, frame := 0) -> Array:
	var key := "%s:%d" % [id, frame]
	if _cache.has(key):
		return _cache[key]
	var rng := RandomNumberGenerator.new()
	rng.seed = hash(id) * 31 + frame * 7919 + 17
	var out: Array = []
	for s: Array in _shape(id, rng):
		var pts: PackedVector2Array = s[0]
		match s[1]:
			"smooth":
				out.append(_catmull(_jitter(pts, rng, 0.45)))
			"sharp":
				out.append(_bowed(_jitter(pts, rng, 0.4), rng))
			_:
				out.append(pts)
	# the whole drawing sits a little differently each time: a small turn and scale about the centre
	var turn := rng.randf_range(-0.045, 0.045)
	var sc := rng.randf_range(0.975, 1.02)
	var c := Vector2(BOX, BOX) * 0.5
	for i in out.size():
		var pts: PackedVector2Array = out[i]
		for j in pts.size():
			pts[j] = c + (pts[j] - c).rotated(turn) * sc
		out[i] = pts
	_cache[key] = out
	return out


static func _master(id: String) -> Texture2D:
	if not _masters.has(id):
		var path := MASTERS + id + ".png"
		_masters[id] = load(path) if ResourceLoader.exists(path) else null
	return _masters[id]


## Truncates the strokes to the first `progress` of their total length.
static func _clip(lines: Array, progress: float) -> Array:
	if progress >= 1.0:
		return lines
	var total := 0.0
	for pts: PackedVector2Array in lines:
		total += _length(pts)
	var budget := total * progress
	var out: Array = []
	for pts: PackedVector2Array in lines:
		var l := _length(pts)
		if budget >= l:
			out.append(pts)
			budget -= l
			continue
		var part := PackedVector2Array([pts[0]])
		for i in range(1, pts.size()):
			var d := pts[i - 1].distance_to(pts[i])
			if budget >= d:
				part.append(pts[i])
				budget -= d
			else:
				part.append(pts[i - 1].lerp(pts[i], budget / maxf(d, 1e-4)))
				break
		if part.size() >= 2:
			out.append(part)
		break
	return out


static func _length(pts: PackedVector2Array) -> float:
	var l := 0.0
	for i in range(1, pts.size()):
		l += pts[i - 1].distance_to(pts[i])
	return l


static func _jitter(pts: PackedVector2Array, rng: RandomNumberGenerator, j: float) -> PackedVector2Array:
	var out := pts.duplicate()
	for i in out.size():
		out[i] += Vector2(rng.randf_range(-j, j), rng.randf_range(-j, j))
	return out


## Uniform Catmull-Rom through the points, about one sample per 1.5 units.
static func _catmull(p: PackedVector2Array) -> PackedVector2Array:
	if p.size() < 3:
		return _bowed(p, null)
	var out := PackedVector2Array()
	var n := p.size()
	for i in n - 1:
		var p0 := p[maxi(i - 1, 0)] if i > 0 else p[0] * 2.0 - p[1]
		var p1 := p[i]
		var p2 := p[i + 1]
		var p3 := p[i + 2] if i + 2 < n else p[n - 1] * 2.0 - p[n - 2]
		var steps := maxi(int(p1.distance_to(p2) / 1.5), 2)
		for s in steps:
			var t := float(s) / steps
			var t2 := t * t
			var t3 := t2 * t
			out.append(0.5 * ((2.0 * p1) + (p2 - p0) * t + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2 + (3.0 * p1 - p0 - 3.0 * p2 + p3) * t3))
	out.append(p[n - 1])
	return out


## Straight segments drawn by hand: each one bows a little (rng null: a fixed small bow).
static func _bowed(p: PackedVector2Array, rng: RandomNumberGenerator) -> PackedVector2Array:
	var out := PackedVector2Array()
	for i in p.size() - 1:
		var a := p[i]
		var b := p[i + 1]
		var d := b - a
		var bow := d.length() * 0.018 * (rng.randf_range(-1.0, 1.0) if rng else 0.6)
		var mid := (a + b) * 0.5 + d.orthogonal().normalized() * bow
		var steps := maxi(int(d.length() / 2.0), 2)
		for s in steps:
			var t := float(s) / steps
			out.append(a.lerp(mid, t).lerp(mid.lerp(b, t), t))
	out.append(p[p.size() - 1])
	return out


## An ellipse drawn in one movement: `turns` past a full turn so the end overlaps the start, the radius
## breathing a little, the end drifting off the start (a pen never closes a circle exactly).
static func _loop(c: Vector2, rx: float, ry: float, a0: float, turns: float, rng: RandomNumberGenerator, n := 36, tilt := 0.0) -> Array:
	var pts := PackedVector2Array()
	var ph1 := rng.randf() * TAU
	var ph2 := rng.randf() * TAU
	var drift := rng.randf_range(0.02, 0.06)
	var steps := int(n * turns)
	for i in steps + 1:
		var t := float(i) / steps
		var a := a0 + t * TAU * turns
		var k := 1.0 + 0.035 * sin(a * 2.0 + ph1) + 0.02 * sin(a * 3.0 + ph2) + t * drift
		pts.append(c + Vector2(cos(a) * rx * k, sin(a) * ry * k).rotated(tilt))
	return [pts, "dense"]


static func _arc(c: Vector2, rx: float, ry: float, a0: float, a1: float, n := 16) -> Array:
	var pts := PackedVector2Array()
	for i in n + 1:
		var a := lerpf(a0, a1, float(i) / n)
		pts.append(c + Vector2(cos(a) * rx, sin(a) * ry))
	return [pts, "smooth"]


## A rounded rectangle in one stroke, starting near the top-left corner and overshooting it.
static func _rrect(r: Rect2, rad: float) -> Array:
	var pts := PackedVector2Array()
	var corners := [[r.position + Vector2(rad, rad), PI], [Vector2(r.end.x - rad, r.position.y + rad), PI * 1.5],
		[r.end - Vector2(rad, rad), 0.0], [Vector2(r.position.x + rad, r.end.y - rad), PI * 0.5]]
	for c: Array in corners:
		for i in 4:
			var a: float = c[1] + float(i) / 3.0 * PI * 0.5
			pts.append(c[0] + Vector2(cos(a), sin(a)) * rad)
	pts.append(pts[0])
	pts.append(pts[0] + (pts[1] - pts[0]).normalized() * 3.0)
	return [pts, "sharp"]


static func _s(points: Array) -> Array:
	return [PackedVector2Array(points), "smooth"]


static func _h(points: Array) -> Array:
	return [PackedVector2Array(points), "sharp"]


## The drawings, as Mano would do them in a margin: a few quick strokes each.
static func _shape(id: String, rng: RandomNumberGenerator) -> Array:
	var V := func(x: float, y: float) -> Vector2: return Vector2(x, y)
	match id:
		"pencil":
			# a pencil lying at 45°, tip bottom-left, and the squiggle it just wrote
			var tip := Vector2(7, 41)
			var u := Vector2(1, -1).normalized()
			var nn := Vector2(1, 1).normalized()
			var P := func(s: float, t: float) -> Vector2: return tip + u * s + nn * t
			return [
				_h([P.call(9, -4.5), P.call(38, -4.5)]),
				_h([P.call(9, 4.5), P.call(38, 4.5)]),
				_h([P.call(11, 0), P.call(32, 0)]),
				_h([P.call(9, -4.5), P.call(0.4, -0.3), P.call(9, 4.5)]),
				_s([P.call(9, -4.5), P.call(10.3, -2.2), P.call(9, 0), P.call(10.3, 2.2), P.call(9, 4.5)]),
				_h([P.call(33, -4.5), P.call(33, 4.5)]),
				_h([P.call(35.5, -4.5), P.call(35.5, 4.5)]),
				_s([P.call(38, -4.5), P.call(40.6, -3.1), P.call(41.6, 0), P.call(40.6, 3.1), P.call(38, 4.5)]),
				_h([P.call(0.8, 0.0), P.call(3.4, -1.0), P.call(3.4, 1.0), P.call(1.0, 0.2)]),
				_s([V.call(9, 44.6), V.call(12, 42.6), V.call(15, 45.6), V.call(18.5, 43.1), V.call(22, 45.9), V.call(26.5, 44.1)]),
			]
		"coin":
			return [
				_loop(Vector2(24, 24.5), 17, 16.4, 2.2, 1.08, rng, 40),
				_arc(Vector2(24, 24.5), 13, 12.6, -1.15, 3.55, 20),
				_arc(Vector2(25.5, 24.5), 7.4, 8.0, 0.85, 5.43, 16),
				_h([V.call(15.8, 22.4), V.call(26.4, 22.4)]),
				_h([V.call(15.8, 26.6), V.call(25.4, 26.6)]),
				_h([V.call(39.4, 7.6), V.call(42.6, 4.4)]),
				_h([V.call(42.0, 11.6), V.call(46.0, 10.6)]),
			]
		"coffee":
			# the machine's little plastic cup, still steaming
			return [
				_loop(Vector2(24, 16), 11, 3.2, PI, 1.05, rng, 28),
				_s([V.call(13, 16.5), V.call(14.8, 30), V.call(16.6, 43)]),
				_s([V.call(35, 16.5), V.call(33.2, 30), V.call(31.4, 43)]),
				_s([V.call(16.6, 43), V.call(24, 44.3), V.call(31.4, 43)]),
				_s([V.call(14.2, 25), V.call(24, 26.8), V.call(33.8, 25)]),
				_s([V.call(16.2, 17.3), V.call(24, 18.9), V.call(31.8, 17.3)]),
				_s([V.call(20, 11), V.call(18.5, 8), V.call(21, 5), V.call(19.5, 1.5)]),
				_s([V.call(27.5, 11), V.call(29, 8), V.call(26.5, 5), V.call(28, 1.5)]),
			]
		"airpod":
			# the pair as everyone draws them: two buds facing each other, the speakers inside, stems down
			var out: Array = []
			for m: float in [1.0, -1.0]:
				var mx := func(x: float) -> float: return 24.0 + (x - 24.0) * m
				out.append(_loop(Vector2(mx.call(13.8), 12.0), 7.4, 6.3, 0.9, 1.06, rng, 32, -0.32 * m))
				out.append(_loop(Vector2(mx.call(19.0), 13.8), 1.3, 2.0, 0.0, 2.3, rng, 12, -0.32 * m))
				out.append(_s([V.call(mx.call(9.3), 16.2), V.call(mx.call(10.2), 29.0), V.call(mx.call(11.0), 41.2)]))
				out.append(_s([V.call(mx.call(15.0), 18.3), V.call(mx.call(15.3), 30.0), V.call(mx.call(15.6), 41.2)]))
				out.append(_s([V.call(mx.call(11.0), 41.2), V.call(mx.call(11.7), 42.9), V.call(mx.call(13.3), 43.6), V.call(mx.call(14.9), 42.9), V.call(mx.call(15.6), 41.2)]))
			return out
		"camera":
			return [
				_rrect(Rect2(5, 15, 38, 24), 3.5),
				_h([V.call(28.5, 15), V.call(29.5, 10.5), V.call(38, 10.5), V.call(39, 15)]),
				_h([V.call(9.5, 15), V.call(10, 12.6), V.call(15, 12.6), V.call(15.5, 15)]),
				_loop(Vector2(24, 27), 8, 8, 2.4, 1.06, rng, 32),
				_loop(Vector2(24, 27), 4.2, 4.2, 0.6, 1.0, rng, 22),
				_arc(Vector2(24, 27), 6, 6, 3.6, 4.4, 6),
				_rrect(Rect2(8.5, 18.5, 5, 3), 0.8),
			]
		"duck":
			# a rubber duck on the water, facing left
			return [
				_loop(Vector2(17, 15), 7.4, 7.2, 0.8, 1.04, rng, 30),
				_h([V.call(10.2, 13.6), V.call(3.4, 16.4), V.call(10.4, 19.2)]),
				_h([V.call(4.6, 16.5), V.call(9.8, 16.6)]),
				_loop(Vector2(15.2, 12.8), 1.1, 1.1, 0.0, 2.0, rng, 10),
				_s([V.call(22.4, 20.2), V.call(28, 23.6), V.call(35.5, 22), V.call(40.8, 15.2)]),
				_s([V.call(40.8, 15.2), V.call(42.8, 22.5), V.call(40, 31), V.call(31, 36.6), V.call(19.5, 36.6), V.call(10.8, 32), V.call(8.6, 26.2), V.call(11.6, 21.4)]),
				_s([V.call(19.5, 27.5), V.call(25.5, 23.8), V.call(32.5, 25.5), V.call(28, 30.2), V.call(20.5, 29.6)]),
				_s([V.call(1.5, 41.5), V.call(8, 40), V.call(14, 42), V.call(20, 40.3), V.call(26, 42.2), V.call(32, 40.4), V.call(38, 41.8), V.call(46.5, 40.5)]),
			]
		"cross":
			return [
				_s([V.call(9.5, 9.5), V.call(24.5, 23.5), V.call(39, 38.5)]),
				_s([V.call(38.5, 9), V.call(23.5, 25), V.call(9.5, 39)]),
			]
		"tick":
			return [
				_s([V.call(8, 25.5), V.call(13.5, 31), V.call(18.5, 38.5)]),
				_s([V.call(18.5, 38.5), V.call(27, 23.5), V.call(41.5, 7.5)]),
			]
		"smile", "welcome":
			return [
				_loop(Vector2(24, 24.5), 17, 16.5, 2.0, 1.07, rng, 40),
				_h([V.call(18.5, 17.5), V.call(18.3, 21.5)]),
				_h([V.call(29.5, 17.2), V.call(29.7, 21.2)]),
				_s([V.call(14.5, 28), V.call(19, 33), V.call(24.5, 34.8), V.call(30, 32.8), V.call(33.8, 27.6)]),
			]
		"notebook":
			# a closed cahier with its name label
			return [
				_rrect(Rect2(11, 5, 26, 38), 1.5),
				_rrect(Rect2(15, 13, 18, 9), 1.0),
				_h([V.call(17.5, 18.6), V.call(30.5, 18.6)]),
				_h([V.call(38.6, 6.8), V.call(38.6, 43.6)]),
				_h([V.call(11.8, 44.4), V.call(38.2, 44.4)]),
			]
		"map":
			return [
				_h([V.call(5, 11), V.call(17, 7), V.call(29, 11), V.call(41, 7)]),
				_h([V.call(41, 7), V.call(41, 37)]),
				_h([V.call(41, 37), V.call(29, 41), V.call(17, 37), V.call(5, 41)]),
				_h([V.call(5, 41), V.call(5, 11)]),
				_h([V.call(17, 7), V.call(17, 37)]),
				_h([V.call(29, 11), V.call(29, 41)]),
				_h([V.call(9, 34), V.call(11, 31)]),
				_h([V.call(12.5, 29), V.call(15, 27)]),
				_h([V.call(17.5, 26), V.call(20.5, 24.5)]),
				_h([V.call(23, 22.5), V.call(25.5, 20.5)]),
				_h([V.call(28, 19), V.call(31, 18)]),
				_h([V.call(32.5, 13), V.call(37.5, 18)]),
				_h([V.call(37.5, 13), V.call(32.5, 18)]),
			]
		"hoodie":
			# a hoodie on a hanger (the fits)
			return [
				_s([V.call(24, 12.5), V.call(24, 8.5), V.call(25.8, 5.2), V.call(28.6, 5.8), V.call(28.8, 8.6)]),
				_h([V.call(19, 12.5), V.call(10.5, 15.5), V.call(5.5, 26.5), V.call(10.6, 28.4), V.call(13.2, 22.6), V.call(13.2, 43.5),
					V.call(34.8, 43.5), V.call(34.8, 22.6), V.call(37.4, 28.4), V.call(42.5, 26.5), V.call(37.5, 15.5), V.call(29, 12.5)]),
				_s([V.call(19, 12.5), V.call(21, 17.5), V.call(24, 19.5), V.call(27, 17.5), V.call(29, 12.5)]),
				_h([V.call(16.8, 39.5), V.call(18, 34), V.call(30, 34), V.call(31.2, 39.5)]),
				_h([V.call(22.2, 19), V.call(21.8, 25)]),
				_h([V.call(25.8, 19), V.call(26.2, 25)]),
			]
		"target":
			# the waypoint, in red pen
			return [
				_loop(Vector2(24, 24), 11, 11, 2.3, 1.1, rng, 40),
				_loop(Vector2(24, 24), 5.6, 5.6, 0.5, 1.08, rng, 26),
				_loop(Vector2(24, 24), 1.3, 1.3, 0.0, 2.0, rng, 10),
				_h([V.call(24, 5.5), V.call(24, 10)]),
				_h([V.call(24, 38), V.call(24, 42.5)]),
				_h([V.call(5.5, 24), V.call(10, 24)]),
				_h([V.call(38, 24), V.call(42.5, 24)]),
			]
		"arrow":
			# pointing right; drawn turned toward whatever it points at
			return [
				_s([V.call(6, 24.5), V.call(16, 23.3), V.call(26, 23.5), V.call(40, 24)]),
				_h([V.call(30.5, 15), V.call(40.8, 24), V.call(31, 33)]),
			]
		"ring":
			# the prompt's pen ring round the thing you can use
			return [_loop(Vector2(24, 24), 17, 17, 2.4, 1.12, rng, 40)]
		"question":
			return [
				_s([V.call(15.5, 16), V.call(17, 10), V.call(22.5, 6.2), V.call(29, 7.2), V.call(32.5, 12.5), V.call(30, 18.5), V.call(25, 22), V.call(24, 27.5), V.call(24.2, 31.5)]),
				_loop(Vector2(24.3, 38.5), 1.6, 1.6, 0.0, 2.0, rng, 12),
			]
		"heart":
			return [
				_s([V.call(24, 41), V.call(15, 33), V.call(8.5, 24), V.call(8.2, 16), V.call(13, 10.5), V.call(19.5, 10.8), V.call(24, 17)]),
				_s([V.call(24, 17), V.call(28.5, 10.8), V.call(35, 10.5), V.call(39.8, 16), V.call(39.5, 24), V.call(33, 33), V.call(24, 41)]),
			]
		"star":
			var pts: Array = []
			for i in 11:
				var a := -PI * 0.5 + i * PI / 5.0
				var r := 19.0 if i % 2 == 0 else 8.0
				pts.append(Vector2(24, 25) + Vector2(cos(a), sin(a)) * r)
			return [_h(pts)]
		"babyfoot":
			return [
				_rrect(Rect2(6, 15, 36, 19), 1.5),
				_h([V.call(9.5, 34), V.call(9.5, 44)]),
				_h([V.call(38.5, 34), V.call(38.5, 44)]),
				_h([V.call(2, 20.5), V.call(46, 20.5)]),
				_h([V.call(2, 28.5), V.call(46, 28.5)]),
				_h([V.call(14, 17.5), V.call(14, 23.5)]),
				_h([V.call(24, 17.5), V.call(24, 23.5)]),
				_h([V.call(34, 17.5), V.call(34, 23.5)]),
				_h([V.call(19, 25.5), V.call(19, 31.5)]),
				_h([V.call(29, 25.5), V.call(29, 31.5)]),
				_loop(Vector2(23.5, 25.3), 1.3, 1.3, 0.0, 2.0, rng, 10),
			]
		"phone":
			# a phone held upright, its screen and the little notch (V2-24)
			return [
				_rrect(Rect2(14, 4, 20, 40), 4.0),
				_rrect(Rect2(17, 9, 14, 28), 1.5),
				_h([V.call(21.5, 6.6), V.call(26.5, 6.6)]),
				_loop(Vector2(24, 40.6), 1.2, 1.2, 0.0, 2.0, rng, 10),
				_s([V.call(36.5, 12), V.call(39, 15.5), V.call(36.5, 19)]),
				_s([V.call(40, 9.5), V.call(43.5, 15.5), V.call(40, 21.5)]),
			]
		"music":
			# two quavers on a beam, as a margin doodle
			return [
				_loop(Vector2(14, 37), 5.2, 4.0, 0.4, 1.06, rng, 22, -0.35),
				_loop(Vector2(33, 33), 5.2, 4.0, 0.4, 1.06, rng, 22, -0.35),
				_h([V.call(18.8, 36), V.call(18.8, 10.5)]),
				_h([V.call(37.8, 32), V.call(37.8, 6.5)]),
				_s([V.call(18.8, 10.5), V.call(28, 8.2), V.call(37.8, 6.5)]),
				_s([V.call(18.8, 15.5), V.call(28, 13.2), V.call(37.8, 11.5)]),
			]
		"pin":
			# a map pin: a drop with a hole, and its shadow
			return [
				_s([V.call(24, 41), V.call(16, 29), V.call(12.5, 19.5), V.call(14.5, 11), V.call(24, 5.5), V.call(33.5, 11),
					V.call(35.5, 19.5), V.call(32, 29), V.call(24, 41)]),
				_loop(Vector2(24, 18.5), 4.4, 4.4, 0.8, 1.08, rng, 22),
				_s([V.call(16, 44), V.call(24, 45.4), V.call(32, 44)]),
			]
	# an unknown id: a question mark, so a typo shows up instead of a blank note
	return _shape("question", rng)
