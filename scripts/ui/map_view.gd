class_name MapView
extends Control
## The M map as a page of Mano's notebook (V2-09, docs/DESIGN.md §6). A sheet of 5 mm grid paper
## ("petits carreaux", 1 carreau = 4 m) taped onto the page, with the campus in pencil from
## assets/levels/campus_plan.json (tools/map/export_plan.py: the level's own footprints): KB1, 24 rue Pasteur,
## Paritalie, the courtyard (stippled), the covered passages, the rooms (inked once Mano has been in them, pencil and
## "?" before), the streets with their names and one-way arrows, a north arrow 13.6° clockwise of page-up, a scale
## bar and the OpenStreetMap credit. All of that is drawn once into a SubViewport (UPDATE_ONCE) when the map opens;
## only Mano ("moi"), the friends, the objective's loop and the finder's pin are drawn over it, ten times a second.
## No two labels overlap: each one takes the first free place among a few around its point (place_label, tested in
## tests/test_map.gd).

const PLAN := "res://assets/levels/campus_plan.json"
const SHEET_H := 740.0          # the grid sheet's height at the 1600x900 base
const OVERLAY_HZ := 10.0
const LABEL_SIZE := 21
const NAME_SIZE := 19          # Atkinson: 22.8 px at 1080p, the §5.3 floor is 22
const PENCIL := Color("#6b6d73")
const PENCIL_SOFT := Color(0.42, 0.43, 0.46, 0.55)

var game
var plan := {}
var sheet := Rect2()            # where the grid sheet is on screen
var scale_px := 6.0             # pixels per metre
var static_rects: Array = []    # the baked labels' rects (the overlay keeps clear of them)
var overlay_rects: Array = []   # the last overlay's label rects (tests and autotests)
var overlay_dots: Array = []    # the last overlay's dots and pin (labels keep clear of them)
var _bounds := Rect2(-55, -50, 110, 115)
var _vp: SubViewport
var _tex: TextureRect
var _over: Control               # the live layer, a child over the baked sheet (a parent draws under its children)
var _t := 0.0
var _redraw := 0.0
var _seen: Array = []


func _ready() -> void:
	plan = load_plan()
	var b: Array = plan.get("bounds", [-55, -50, 110, 115])
	_bounds = Rect2(float(b[0]), float(b[1]), float(b[2]), float(b[3]))
	_seen = GameState.flags.get("zones_seen", [])
	resized.connect(_layout)
	_layout.call_deferred()


static func load_plan() -> Dictionary:
	if not FileAccess.file_exists(PLAN):
		push_warning("MapView: %s is missing (python3 tools/map/export_plan.py)" % PLAN)
		return {}
	var j = JSON.parse_string(FileAccess.get_file_as_string(PLAN))
	return j if j is Dictionary else {}


func _layout() -> void:
	var vp := get_viewport_rect().size
	scale_px = SHEET_H / _bounds.size.y
	var w := _bounds.size.x * scale_px
	sheet = Rect2(Vector2(70.0, (vp.y - SHEET_H) * 0.5 + 18.0), Vector2(w, SHEET_H))
	_bake()
	queue_redraw()


func to_screen(x: float, z: float) -> Vector2:
	return sheet.position + (Vector2(x, z) - _bounds.position) * scale_px


# ------------------------------------------------------------------ the baked sheet
func _bake() -> void:
	if _vp:
		_vp.queue_free()
		_tex.queue_free()
	_vp = SubViewport.new()
	_vp.size = Vector2i(get_viewport_rect().size)
	_vp.transparent_bg = true
	_vp.render_target_update_mode = SubViewport.UPDATE_ONCE
	_vp.disable_3d = true
	var painter := Control.new()
	painter.size = Vector2(_vp.size)
	painter.draw.connect(func(): _draw_static(painter))
	_vp.add_child(painter)
	add_child(_vp)
	_tex = TextureRect.new()
	_tex.texture = _vp.get_texture()
	_tex.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_tex.size = Vector2(_vp.size)
	add_child(_tex)
	if _over == null:
		_over = Control.new()
		_over.mouse_filter = Control.MOUSE_FILTER_IGNORE
		_over.draw.connect(func(): _draw_overlay(_over))
		add_child(_over)
	_over.size = Vector2(_vp.size)
	move_child(_tex, 0)


func _draw_static(c: Control) -> void:
	static_rects.clear()
	var rng := RandomNumberGenerator.new()
	rng.seed = 1406
	# the notebook page behind, and the grid sheet taped on it
	var page := Rect2(sheet.position - Vector2(40, 46), Vector2(get_viewport_rect().size.x - 60.0, sheet.size.y + 92.0))
	c.draw_rect(page, UITheme.PAPER.lerp(UITheme.PAPER_SHADE, 0.3))
	c.draw_rect(sheet.grow(6), Color(0, 0, 0, 0.08))
	c.draw_rect(sheet, UITheme.PAPER)
	var step := float(plan.get("carreau_m", 4.0)) * scale_px
	var x0 := sheet.position.x + fposmod(-_bounds.position.x * scale_px, step)
	var x := x0
	while x < sheet.end.x:
		c.draw_line(Vector2(x, sheet.position.y), Vector2(x, sheet.end.y), Color(UITheme.GRID_5MM, 0.7), 1.0)
		x += step
	var y := sheet.position.y + fposmod(-_bounds.position.y * scale_px, step)
	while y < sheet.end.y:
		c.draw_line(Vector2(sheet.position.x, y), Vector2(sheet.end.x, y), Color(UITheme.GRID_5MM, 0.7), 1.0)
		y += step
	# tape at the top corners
	for corner in [sheet.position + Vector2(18, -6), Vector2(sheet.end.x - 70, sheet.position.y - 6)]:
		c.draw_rect(Rect2(corner, Vector2(56, 20)), UITheme.TAPE)
	# the streets: two pencil kerbs, the name and the one-way arrow
	for st in plan.get("streets", []):
		var a := Vector2(st.a[0], st.a[1])
		var b := Vector2(st.b[0], st.b[1])
		var n := (b - a).normalized().orthogonal() * float(st.get("half", 5.0))
		for side in [-1.0, 1.0]:
			_pencil(c, [a + n * side, b + n * side], rng, PENCIL_SOFT, 1.4)
	# the courtyard, stippled
	var court := _poly(plan.get("court", []))
	if court.size() >= 3:
		var box := _box(court)
		for i in 420:
			var p := Vector2(rng.randf_range(box.position.x, box.end.x), rng.randf_range(box.position.y, box.end.y))
			if Geometry2D.is_point_in_polygon(p, court):
				c.draw_circle(p, 0.9, PENCIL_SOFT)
		_outline(c, court, rng, PENCIL, 1.3)
	# the buildings: pencil outlines with an architect's overshoot, hatched
	for bd in plan.get("buildings", []):
		var pts := _poly(bd.pts)
		_hatch(c, pts, float(bd.get("hatch", 45)), 7.0, Color(PENCIL, 0.28))
		_outline(c, pts, rng, PENCIL, 1.6)
	for cv in plan.get("covered", []):
		_outline(c, _poly(cv.pts), rng, PENCIL_SOFT, 1.1, true)
	# the rooms: inked once visited, pencil and "?" before
	for rm in plan.get("rooms", []):
		var pts := _poly(rm.pts)
		var seen := String(rm.id) in _seen or (String(rm.id) == "accueil" and "volt_gf" in _seen)
		var col := UITheme.INK_BLUE if seen else PENCIL
		_outline(c, pts, rng, col, 2.0 if seen else 1.3, bool(rm.get("dashed", false)))
	# the north arrow, the scale bar and the credit hold their corners; the labels keep clear of them
	static_rects.append_array(fixed_rects())
	# labels: buildings, rooms, places, streets, off the page (first come, first placed; none overlapping)
	for it in static_label_items():
		var f: Font = it.font
		var sz := f.get_string_size(it.text, HORIZONTAL_ALIGNMENT_LEFT, -1, it.size)
		var rect := place_label(it.at, sz, static_rects, sheet, it.centred)
		static_rects.append(rect)
		c.draw_string(f, rect.position + Vector2(0, f.get_ascent(it.size)), it.text, HORIZONTAL_ALIGNMENT_LEFT, -1, it.size, it.color)
	# the north arrow, 13.6° clockwise of page-up, top right of the sheet
	var na := sheet.position + Vector2(sheet.size.x - 46, 64)
	var nd := Vector2.UP.rotated(deg_to_rad(float(plan.get("north_deg", 13.6))))
	c.draw_line(na - nd * 26, na + nd * 26, UITheme.INK_BLUE, 2.2, true)
	c.draw_colored_polygon(PackedVector2Array([na + nd * 30, na + nd * 16 + nd.orthogonal() * 7, na + nd * 16 - nd.orthogonal() * 7]), UITheme.INK_BLUE)
	c.draw_string(UITheme.marker, na + nd * 42 - Vector2(7, -8), "N", HORIZONTAL_ALIGNMENT_LEFT, -1, 22, UITheme.INK_BLUE)
	# the scale bar: four carreaux, and what one is
	var sb := Vector2(sheet.position.x + 24, sheet.end.y - 30)
	for i in 4:
		c.draw_rect(Rect2(sb + Vector2(i * step, 0), Vector2(step, 6)), UITheme.INK_BLUE if i % 2 == 0 else UITheme.PAPER)
	c.draw_rect(Rect2(sb, Vector2(step * 4, 6)), UITheme.INK_BLUE, false, 1.2)
	c.draw_string(UITheme.pen, sb + Vector2(0, -8), "1 carreau = 4 m", HORIZONTAL_ALIGNMENT_LEFT, -1, 22, UITheme.INK_BLUE)
	# the credit, in pencil, in the corner (OpenStreetMap asks for it)
	var credit := String(plan.get("credit", ""))
	var cs := UITheme.print_400.get_string_size(credit, HORIZONTAL_ALIGNMENT_LEFT, -1, 13)
	c.draw_string(UITheme.print_400, Vector2(sheet.end.x - cs.x - 10, sheet.end.y - 10), credit, HORIZONTAL_ALIGNMENT_LEFT, -1, 13, PENCIL)
	# the title, in marker, over the sheet
	c.draw_string(UITheme.marker_title, sheet.position + Vector2(0, -14), "campus map (roughly)", HORIZONTAL_ALIGNMENT_LEFT, -1, 30, UITheme.INK_BLACK)


## The corners the north arrow, the scale bar and the credit take.
func fixed_rects() -> Array:
	var step := float(plan.get("carreau_m", 4.0)) * scale_px
	var na := sheet.position + Vector2(sheet.size.x - 46, 64)
	var sb := Vector2(sheet.position.x + 24, sheet.end.y - 30)
	var cs := UITheme.print_400.get_string_size(String(plan.get("credit", "")), HORIZONTAL_ALIGNMENT_LEFT, -1, 13)
	return [Rect2(na - Vector2(30, 60), Vector2(60, 96)), Rect2(sb + Vector2(0, -30), Vector2(maxf(step * 4, UITheme.pen.get_string_size("1 carreau = 4 m", HORIZONTAL_ALIGNMENT_LEFT, -1, 22).x + 4.0), 40)),
		Rect2(Vector2(sheet.end.x - cs.x - 10, sheet.end.y - 26), cs + Vector2(0, 8))]


## The sheet's own labels, in the order they are placed: {text, at (screen), font, size, color, centred}.
func static_label_items() -> Array:
	var out: Array = []
	for bd in plan.get("buildings", []):
		if String(bd.get("label", "")) != "":
			out.append({"text": String(bd.label), "at": _centroid(_poly(bd.pts)), "font": UITheme.marker_label, "size": LABEL_SIZE, "color": UITheme.INK_BLACK, "centred": true})
	for rm in plan.get("rooms", []):
		var seen := String(rm.id) in _seen or (String(rm.id) == "accueil" and "volt_gf" in _seen)
		out.append({"text": String(rm.label) + ("" if seen else " ?"), "at": _centroid(_poly(rm.pts)), "font": UITheme.pen, "size": LABEL_SIZE,
			"color": UITheme.INK_BLUE if seen else PENCIL, "centred": true})
	for lb in plan.get("labels", []):
		out.append({"text": String(lb.text), "at": to_screen(float(lb.at[0]), float(lb.at[1])), "font": UITheme.pen, "size": LABEL_SIZE, "color": PENCIL, "centred": true})
	for st in plan.get("streets", []):
		var a := to_screen(float(st.a[0]), float(st.a[1]))
		var b := to_screen(float(st.b[0]), float(st.b[1]))
		out.append({"text": String(st.name) + ("  <-" if String(st.get("one_way", "")) == "west" else "  ->"), "at": a.lerp(b, 0.62), "font": UITheme.pen,
			"size": LABEL_SIZE - 1, "color": PENCIL, "centred": true})
	for op in plan.get("off_page", []):
		var at := to_screen(float(op.at[0]), float(op.at[1]))
		at.x = clampf(at.x, sheet.position.x + 8.0, sheet.end.x - 8.0)
		var sz := UITheme.pen.get_string_size(op.text, HORIZONTAL_ALIGNMENT_LEFT, -1, 17)
		var p := at + (Vector2(6 + sz.x * 0.5, -16) if float(op.dir[0]) < 0 else Vector2(-6 - sz.x * 0.5, -16))
		out.append({"text": String(op.text), "at": p, "font": UITheme.pen, "size": 17, "color": PENCIL, "centred": true})
	return out


func _poly(pts: Array) -> PackedVector2Array:
	var out := PackedVector2Array()
	for p in pts:
		out.append(to_screen(float(p[0]), float(p[1])))
	return out


static func _box(pts: PackedVector2Array) -> Rect2:
	var r := Rect2(pts[0], Vector2.ZERO)
	for p in pts:
		r = r.expand(p)
	return r


static func _centroid(pts: PackedVector2Array) -> Vector2:
	var c := Vector2.ZERO
	for p in pts:
		c += p
	return c / maxf(pts.size(), 1)


## A pencil line: drawn twice with a little seeded wobble, running on past its ends (the architect's overshoot).
func _pencil(c: Control, pts: Array, rng: RandomNumberGenerator, col: Color, w: float) -> void:
	for pass_i in 2:
		var line := PackedVector2Array()
		for i in pts.size():
			var p: Vector2 = to_screen(pts[i].x, pts[i].y)
			line.append(p + Vector2(rng.randf_range(-0.8, 0.8), rng.randf_range(-0.8, 0.8)))
		c.draw_polyline(line, Color(col, col.a * (1.0 if pass_i == 0 else 0.55)), w, true)


func _outline(c: Control, pts: PackedVector2Array, rng: RandomNumberGenerator, col: Color, w: float, dashed := false) -> void:
	if pts.size() < 2:
		return
	for i in pts.size():
		var a := pts[i]
		var b := pts[(i + 1) % pts.size()]
		var d := (b - a).normalized()
		var a2 := a - d * rng.randf_range(1.0, 4.0)
		var b2 := b + d * rng.randf_range(1.0, 4.0)
		if dashed:
			c.draw_dashed_line(a, b, col, w, 6.0)
		else:
			c.draw_line(a2 + Vector2(rng.randf_range(-0.6, 0.6), rng.randf_range(-0.6, 0.6)), b2, col, w, true)
			c.draw_line(a + d.orthogonal() * 0.8, b + d.orthogonal() * 0.8, Color(col, col.a * 0.45), w * 0.7, true)


## Hatching at `deg` degrees every `gap` pixels, clipped to the polygon.
func _hatch(c: Control, pts: PackedVector2Array, deg: float, gap: float, col: Color) -> void:
	if pts.size() < 3:
		return
	var box := _box(pts)
	var dir := Vector2.RIGHT.rotated(deg_to_rad(-deg))
	var nrm := dir.orthogonal()
	var reach := box.size.length()
	var centre := box.get_center()
	var k := -reach
	while k < reach:
		var o := centre + nrm * k
		var seg := PackedVector2Array([o - dir * reach, o + dir * reach])
		for piece in Geometry2D.intersect_polyline_with_polygon(seg, pts):
			if piece.size() >= 2:
				c.draw_line(piece[0], piece[piece.size() - 1], col, 1.0, true)
		k += gap


## Where a label of `size` goes near `at` (its anchor): the first of the places around it, ring after ring further
## out, that overlaps no rect in `taken` and stays on `inside`; else the least crowded of them. `centred` labels try
## their own middle first. A label pushed far from its point gets a pencil leader line back to it (the overlay).
static func place_label(at: Vector2, size: Vector2, taken: Array, inside: Rect2, centred := false) -> Rect2:
	var cands: Array = []
	if centred:
		cands.append(at - size * 0.5)
	cands.append(at + Vector2(12, -size.y * 0.5))
	cands.append(at + Vector2(-12 - size.x, -size.y * 0.5))
	for ring in [16.0, 30.0, 46.0, 64.0, 86.0, 112.0, 142.0, 176.0]:
		for k in 16:
			var a := k * TAU / 16.0
			var d := Vector2(cos(a), sin(a))
			# the label's nearest side toward the anchor sits `ring` away from it
			var c: Vector2 = at + d * float(ring) + Vector2(d.x * size.x * 0.5, d.y * size.y * 0.5)
			cands.append(c - size * 0.5)
	var best := Rect2(cands[0], size)
	var best_cost := INF
	for p in cands:
		var r := Rect2(p, size)
		if inside.size.x > 0.0 and not inside.encloses(r):
			continue
		var cost := 0.0
		for t in taken:
			cost += r.intersection(t as Rect2).get_area()
		if cost <= 0.0:
			return r
		if cost < best_cost:
			best_cost = cost
			best = r
	return best


## A pencil leader line from a point to its label when the label had to move away from it.
func _leader(c: Control, at: Vector2, r: Rect2) -> void:
	var near := Vector2(clampf(at.x, r.position.x, r.end.x), clampf(at.y, r.position.y, r.end.y))
	if at.distance_to(near) > 18.0:
		c.draw_line(at, near, Color(PENCIL, 0.8), 1.2, true)


# ------------------------------------------------------------------ the overlay (live)
func _process(dt: float) -> void:
	_t += dt
	_redraw -= dt
	if _redraw <= 0.0:
		_redraw = 1.0 / OVERLAY_HZ
		if _over:
			_over.queue_redraw()


func _draw_overlay(c: Control) -> void:
	if game == null or game.player == null or sheet.size.x <= 0.0:
		return
	overlay_rects.clear()
	var taken: Array = static_rects.duplicate()
	var pp: Vector3 = game.player.global_position
	var ps := to_screen(pp.x, pp.z)
	# the friends Mano knows, where they are now
	var friends: Array = []
	var met := {"ishita": "ishita_met", "joaquin": "joaquin_met", "cristina": "cristina_texted"}
	for id in ["toma", "anisha", "ian", "silvia", "ishita", "joaquin", "cristina", "karim", "madame", "madame2"]:
		if met.has(id) and not GameState.flags.get(met[id], false):
			continue
		if not game.npcs.has(id) or not game.npcs[id].visible or not game.npcs[id].is_present():
			continue
		friends.append(game.npcs[id])
	# the finder's pin (chapter 3 on)
	var pin_at := Vector2.INF
	var fp := String(GameState.flags.get("finder_place", ""))
	if bool(GameState.flags.get("found", false)) and int(GameState.flags.get("chapter", 1)) >= 4:
		fp = ""
	var where_pin: Dictionary = WorldData.finder_place(fp) if fp != "" else {}
	if not where_pin.is_empty():
		pin_at = to_screen(where_pin.pos.x, where_pin.pos.z)
	# the dots and the pin take their place before any live label, so no label is written over one
	overlay_dots = [Rect2(ps - Vector2(7, 7), Vector2(14, 14))]
	for n in friends:
		overlay_dots.append(Rect2(to_screen(n.global_position.x, n.global_position.z) - Vector2(7, 7), Vector2(14, 14)))
	if pin_at != Vector2.INF:
		overlay_dots.append(Rect2(pin_at + Vector2(-9, -29), Vector2(18, 30)))
	taken.append_array(overlay_dots)
	# the objective's loop too: "moi" and the names go outside it
	var t: Dictionary = game.story.target()
	var t_at := Vector2.INF
	if not t.is_empty():
		t_at = to_screen(t.pos.x, t.pos.z)
		taken.append(Rect2(t_at - Vector2(24, 24), Vector2(48, 48)))
	# the live labels are written last, each on a paper halo, so no dot, loop or leader line is drawn over one
	var texts: Array = []   # [font, baseline position, text, size, colour]
	# Mano: a red dot, his facing, "moi"
	var yaw: float = game.player.facing_yaw()
	var f := Vector2(sin(yaw), cos(yaw))
	c.draw_circle(ps, 6.0, UITheme.MARKER_RED)
	c.draw_line(ps, ps + f * 16.0, UITheme.MARKER_RED, 2.4, true)
	if _t < 1.0:
		c.draw_arc(ps, 14.0 + _t * 4.0, 0, TAU * minf(_t * 1.25, 1.0), 32, UITheme.MARKER_RED, 2.0, true)
	var moi := place_label(ps, UITheme.marker.get_string_size("moi", HORIZONTAL_ALIGNMENT_LEFT, -1, 20), taken, sheet)
	taken.append(moi)
	overlay_rects.append(moi)
	_leader(c, ps, moi)
	texts.append([UITheme.marker, moi.position + Vector2(0, UITheme.marker.get_ascent(20)), "moi", 20, UITheme.MARKER_RED])
	# the objective: a red marker loop, drawn on, and its note
	if t_at != Vector2.INF:
		var s := t_at
		var k := clampf(_t / 0.45, 0.0, 1.0)
		c.draw_arc(s, 22.0, -PI * 0.5, -PI * 0.5 + TAU * 1.25 * k, 48, UITheme.MARKER_RED, 3.0, true)
		var sz := UITheme.marker.get_string_size(String(t.label), HORIZONTAL_ALIGNMENT_LEFT, -1, 22)
		var r := place_label(s + Vector2(14, 0), sz, taken, sheet)
		taken.append(r)
		overlay_rects.append(r)
		_leader(c, s, r)
		texts.append([UITheme.marker, r.position + Vector2(0, UITheme.marker.get_ascent(22)), String(t.label), 22, UITheme.MARKER_RED])
	if pin_at != Vector2.INF:
		var s := pin_at
		var pin := PackedVector2Array([s, s + Vector2(-8, -16), s + Vector2(-6, -24), s + Vector2(0, -28), s + Vector2(6, -24), s + Vector2(8, -16)])
		c.draw_colored_polygon(pin, Color("#2b7de9"))
		c.draw_circle(s + Vector2(0, -19), 3.2, Color.WHITE)
		var txt := "AirPod, %s" % GameState.flags.get("finder_time", "")
		var r := place_label(s + Vector2(0, -19), UITheme.print_700.get_string_size(txt, HORIZONTAL_ALIGNMENT_LEFT, -1, NAME_SIZE), taken, sheet)
		taken.append(r)
		overlay_rects.append(r)
		texts.append([UITheme.print_700, r.position + Vector2(0, UITheme.print_700.get_ascent(NAME_SIZE)), txt, NAME_SIZE, Color("#2b7de9")])
	# the friends' dots in their colours, and their names (not one the objective's note already gives, in its loop)
	for n in friends:
		var s := to_screen(n.global_position.x, n.global_position.z)
		c.draw_circle(s, 5.0, n.color)
		c.draw_arc(s, 5.5, 0, TAU, 16, UITheme.INK_BLACK, 1.0, true)
		if t_at != Vector2.INF and s.distance_to(t_at) < 24.0 and String(t.label).contains(String(n.display_name).get_slice(" ", 0)):
			continue
		var sz := UITheme.print_700.get_string_size(String(n.display_name), HORIZONTAL_ALIGNMENT_LEFT, -1, NAME_SIZE)
		var r := place_label(s, sz, taken, sheet)
		taken.append(r)
		overlay_rects.append(r)
		_leader(c, s, r)
		texts.append([UITheme.print_700, r.position + Vector2(0, UITheme.print_700.get_ascent(NAME_SIZE)), String(n.display_name), NAME_SIZE, Color(n.color).darkened(0.35)])
	for tx in texts:
		c.draw_string_outline(tx[0], tx[1], tx[2], HORIZONTAL_ALIGNMENT_LEFT, -1, tx[3], 6, UITheme.PAPER)
		c.draw_string(tx[0], tx[1], tx[2], HORIZONTAL_ALIGNMENT_LEFT, -1, tx[3], tx[4])
	# the right page: where I am, the objective, the keys
	var rx := sheet.end.x + 48.0
	var ry := sheet.position.y + 30.0
	c.draw_string(UITheme.marker, Vector2(rx, ry), "around me", HORIZONTAL_ALIGNMENT_LEFT, -1, 26, UITheme.INK_RED)
	var zone: Dictionary = game._zone
	var where := String(zone.get("label", ""))
	if where == "":
		where = "the basement" if pp.y < -2.5 else ("the 1st floor" if pp.y > 3.0 else "campus")
	var floor_txt := ", 1st floor" if pp.y > 3.0 else (", basement" if pp.y < -3.0 else "")
	c.draw_string(UITheme.pen, Vector2(rx, ry + 34), "I'm in " + where + floor_txt, HORIZONTAL_ALIGNMENT_LEFT, sheet.position.x + get_viewport_rect().size.x - rx - 120.0, 23, UITheme.INK_BLUE)
	c.draw_string(UITheme.marker, Vector2(rx, ry + 90), "today", HORIZONTAL_ALIGNMENT_LEFT, -1, 26, UITheme.INK_RED)
	var obj: String = game.story.objective()
	var lines := _wrap_text(obj if obj != "" else "Nothing right now.", UITheme.pen, 23, get_viewport_rect().size.x - rx - 60.0)
	for i in lines.size():
		c.draw_string(UITheme.pen, Vector2(rx, ry + 124 + i * 28), lines[i], HORIZONTAL_ALIGNMENT_LEFT, -1, 23, UITheme.INK_BLUE)
	c.draw_string(UITheme.print_500, Vector2(rx, sheet.end.y - 4), "%s or %s to close" % [UITheme.action_key("map"), UITheme.action_key("back")], HORIZONTAL_ALIGNMENT_LEFT, -1, NAME_SIZE, PENCIL)


static func _wrap_text(text: String, font: Font, size: int, width: float) -> Array:
	var out: Array = []
	var line := ""
	for w in text.split(" "):
		var cand := w if line == "" else line + " " + w
		if font.get_string_size(cand, HORIZONTAL_ALIGNMENT_LEFT, -1, size).x > width and line != "":
			out.append(line)
			line = w
		else:
			line = cand
	if line != "":
		out.append(line)
	return out
