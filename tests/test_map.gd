extends RefCounted
## The M map (V2-09): assets/levels/campus_plan.json is there and whole (tools/map/export_plan.py),
## and no two labels overlap. The map is laid out headless at the 1600x900 base with its static labels, then with
## the busiest overlay the night has (all seven friends and Karim on or near the courtyard steps, Mano among them,
## the objective there and the finder's pin), and every pair of label rectangles is checked, and no live label is
## over a dot.

const Support := preload("res://tests/support.gd")


func run(t) -> void:
	UITheme.init()
	var plan := MapView.load_plan()
	if not t.ok(not plan.is_empty(), "assets/levels/campus_plan.json loads (python3 tools/map/export_plan.py writes it)"):
		return
	t.ok(plan.get("buildings", []).size() >= 4 and plan.get("court", []).size() >= 3 and plan.get("rooms", []).size() >= 4,
		"the plan has the buildings, the courtyard and the rooms")
	t.ok(absf(float(plan.get("north_deg", 0)) - 13.6) < 0.01 and float(plan.get("carreau_m", 0)) == 4.0, "north 13.6° clockwise of page-up, 1 carreau = 4 m")
	t.ok(String(plan.get("credit", "")).contains("OpenStreetMap"), "the OpenStreetMap credit is on the sheet")
	for b in plan.get("buildings", []) + plan.get("rooms", []):
		t.ok(b.get("pts", []).size() >= 3, "plan %s has a footprint" % b.get("id", "?"))
	# a map laid out at the base size, its static layer drawn into an image-less canvas: the label rects it placed
	var mv := MapView.new()
	mv.plan = plan
	mv.sheet = Rect2(Vector2(70, 98), Vector2(110.0 * 740.0 / 115.0, 740.0))
	mv.scale_px = 740.0 / 115.0
	var rects: Array = mv.fixed_rects()
	for it in mv.static_label_items():
		var f: Font = it.font
		rects.append(MapView.place_label(it.at, f.get_string_size(it.text, HORIZONTAL_ALIGNMENT_LEFT, -1, it.size), rects, mv.sheet, it.centred))
	# the busiest overlay: everyone at the steps (chapter 5), Mano too, the objective and a pin
	var crowd: Array = [["moi", Vector3(-4.47, 0, 22.74)], ["Give Toma the other AirPod", Vector3(-3.11, 0, 21.56)], ["AirPod, 20:31", Vector3(5.0, -3.6, 42.0)]]
	for id in ["toma", "anisha", "ian", "silvia", "ishita", "cristina", "joaquin"]:
		var p := WorldData.point("steps5_" + id)
		crowd.append([id.capitalize(), p.pos if not p.is_empty() else Vector3.ZERO])
	crowd.append(["Karim (BDE)", WorldData.point("under_bar_karim").pos])
	crowd.append(["Mme Dupont", Vector3(-11.29, 0, 45.44)])
	# the dots go down first (MapView._draw_overlay): no live label is placed over one
	var dots: Array = []
	for c in crowd:
		dots.append(Rect2(mv.to_screen(c[1].x, c[1].z) - Vector2(7, 7), Vector2(14, 14)))
	dots.append(Rect2(mv.to_screen(crowd[1][1].x, crowd[1][1].z) - Vector2(24, 24), Vector2(48, 48)))   # the objective's loop
	var n_static := rects.size()
	for c in crowd:
		var sz := UITheme.print_700.get_string_size(c[0], HORIZONTAL_ALIGNMENT_LEFT, -1, MapView.NAME_SIZE)
		rects.append(MapView.place_label(mv.to_screen(c[1].x, c[1].z), sz, rects + dots, mv.sheet))
	var on_dots := 0
	for r in rects.slice(n_static):
		for d in dots:
			if (r as Rect2).intersects(d as Rect2):
				on_dots += 1
				t.fail("a live map label %s is over a dot %s" % [r, d])
	t.ok(on_dots == 0, "no live map label is written over a dot (%d dots)" % dots.size())
	var overlaps := 0
	for i in rects.size():
		for j in range(i + 1, rects.size()):
			if (rects[i] as Rect2).intersects(rects[j] as Rect2):
				overlaps += 1
				t.fail("map labels overlap: %s and %s" % [rects[i], rects[j]])
	t.ok(rects.size() >= 20, "the busy map has its labels (%d)" % rects.size())
	t.ok(overlaps == 0, "no two of the map's %d labels overlap (static ones and the busiest overlay)" % rects.size())
	for r in rects:
		t.ok(mv.sheet.encloses(r), "map label %s stays on the sheet" % r)
	mv.free()
