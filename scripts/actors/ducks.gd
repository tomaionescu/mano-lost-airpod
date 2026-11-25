class_name Ducks
extends Node3D
## Twelve golden rubber ducks hidden around campus (V2-30, docs/DESIGN.md §3.8): the level's eight DUCK_ markers and the
## four data/world.json "ducks" adds, each out from its chapter on (3/3/2/2/2). Walk into one to collect it. Eight
## unlock the merch fit (MERCH_AT); all twelve the journal's duck page and a line on the steps (flags.ducks_all).
## The two night ones glow brighter. The ducks bob and turn, so their meshes stay out of the GI (GI_MODE_DISABLED).

const MERCH_AT := 8

var game
var _items: Array = []     # [{id, node, base_y, chapter, hint, glow}]
var _found := {}
var _gold: StandardMaterial3D
var _gold_night: StandardMaterial3D
var _beak: StandardMaterial3D
var _t := 0.0
var _shown_chapter := -99


func setup(g, level_ducks: Array) -> void:
	game = g
	_gold = StandardMaterial3D.new()
	_gold.albedo_color = Color(1.0, 0.78, 0.22)
	_gold.metallic = 1.0
	_gold.roughness = 0.22
	_gold.emission_enabled = true
	_gold.emission = Color(1.0, 0.7, 0.2)
	_gold.emission_energy_multiplier = 0.35
	_gold_night = _gold.duplicate()
	_gold_night.emission_energy_multiplier = 1.6
	_beak = StandardMaterial3D.new()
	_beak.albedo_color = Color(1.0, 0.45, 0.1)
	_beak.roughness = 0.4
	var data := WorldData.section("ducks")
	var at := {}
	for d in level_ducks:
		at[String(d.id)] = d.pos
	for id in data:
		var e: Dictionary = data[id]
		var pos: Vector3
		if e.has("pos"):
			pos = WorldData.vec(e.pos)
		elif at.has(String(id)):
			pos = at[String(id)]
		else:
			push_warning("ducks: '%s' has no DUCK_ marker and no pos in data/world.json" % id)
			continue
		var glow := bool(e.get("glow", false))
		var n := _make_duck(glow)
		add_child(n)
		n.global_position = pos
		_items.append({"id": String(id), "node": n, "base_y": pos.y, "chapter": int(e.get("chapter", 1)),
			"hint": String(e.get("hint", "")), "glow": glow, "snap": bool(e.get("snap", false))})
	# a level duck the data does not know is still a duck (chapter 1)
	for id in at:
		if not data.has(id):
			var n := _make_duck(false)
			add_child(n)
			n.global_position = at[id]
			_items.append({"id": String(id), "node": n, "base_y": at[id].y, "chapter": 1, "hint": "", "glow": false})
	_show_chapter()
	# the new ones sit on whatever floor is under them, once the level's colliders are in the physics space
	get_tree().create_timer(0.5).timeout.connect(_snap)


func _snap() -> void:
	for it in _items:
		if bool(it.get("snap", false)):
			var n: Node3D = it.node
			it.base_y = _floor_y(n.global_position) + 0.07
			n.position.y = it.base_y


func _floor_y(p: Vector3) -> float:
	var space := get_world_3d().direct_space_state
	var q := PhysicsRayQueryParameters3D.create(p + Vector3.UP * 1.0, p - Vector3.UP * 1.5, 1)
	var hit := space.intersect_ray(q)
	return hit.position.y if not hit.is_empty() else p.y


func _make_duck(glow: bool) -> Node3D:
	var root := Node3D.new()
	var gold := _gold_night if glow else _gold
	var body := MeshInstance3D.new()
	var sm := SphereMesh.new()
	sm.radius = 0.07
	sm.height = 0.12
	body.mesh = sm
	body.scale = Vector3(1.0, 0.85, 1.25)
	body.material_override = gold
	root.add_child(body)
	var head := MeshInstance3D.new()
	var hm := SphereMesh.new()
	hm.radius = 0.045
	hm.height = 0.09
	head.mesh = hm
	head.position = Vector3(0, 0.07, 0.05)
	head.material_override = gold
	root.add_child(head)
	var beak := MeshInstance3D.new()
	var bm := CylinderMesh.new()
	bm.top_radius = 0.0
	bm.bottom_radius = 0.022
	bm.height = 0.04
	beak.mesh = bm
	beak.rotation_degrees = Vector3(90, 0, 0)
	beak.position = Vector3(0, 0.065, 0.1)
	beak.material_override = _beak
	root.add_child(beak)
	for mi: MeshInstance3D in [body, head, beak]:
		mi.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
	var light := OmniLight3D.new()
	light.light_bake_mode = Light3D.BAKE_DISABLED
	light.light_color = Color(1.0, 0.8, 0.35)
	light.light_energy = 0.9 if glow else 0.35
	light.omni_range = 1.4 if glow else 0.9
	light.position.y = 0.12
	root.add_child(light)
	return root


func found_ids() -> Array:
	return _found.keys()


func count() -> int:
	return _found.size()


func total() -> int:
	return _items.size()


## The ducks out by chapter `n` (theirs or an earlier one), and how many of those `n` brought out.
func by_chapter() -> Dictionary:
	var out := {}
	for it in _items:
		var c := int(it.chapter)
		if not out.has(c):
			out[c] = Vector2i(0, 0)
		out[c] += Vector2i(1 if _found.has(it.id) else 0, 1)
	return out


## The found ducks are exactly `ids` (a Continue, a chapter replay); the others show from their chapter on.
func restore(ids: Array) -> void:
	_found.clear()
	for it in _items:
		if it.id in ids:
			_found[it.id] = true
		(it.node as Node3D).scale = Vector3.ONE   # a duck found earlier this session shrank to 0.01 flying away (_collect)
	_shown_chapter = -99
	_show_chapter()
	_sync_flags()


## The first duck still out there, from this chapter or an earlier one, for the duck whisperer: {id, hint} or {}.
func next_hint() -> Dictionary:
	var ch := Chapters.current()
	for it in _items:
		if not _found.has(it.id) and int(it.chapter) <= ch and String(it.hint) != "":
			return {"id": it.id, "hint": it.hint}
	return {}


func _show_chapter() -> void:
	var ch := Chapters.current() if game else 1
	if ch == _shown_chapter:
		return
	_shown_chapter = ch
	for it in _items:
		var n: Node3D = it.node
		n.visible = not _found.has(it.id) and int(it.chapter) <= ch and ch >= 1
		n.process_mode = Node.PROCESS_MODE_INHERIT if n.visible else Node.PROCESS_MODE_DISABLED


func _sync_flags() -> void:
	GameState.flags["duck_count"] = count()
	if count() >= total() and total() > 0:
		GameState.flags["ducks_all"] = true
	if count() >= MERCH_AT:
		GameState.flags["merch"] = true


func _process(dt: float) -> void:
	_t += dt
	if game == null or game.player == null:
		return
	_show_chapter()
	var me: Vector3 = game.player.global_position
	for it in _items:
		var n: Node3D = it.node
		if not n.visible or _found.has(it.id):
			continue   # a found one is still visible while it flies up and shrinks (its tween), and must not count twice
		n.position.y = it.base_y + sin(_t * 2.0 + it.base_y * 5.0) * 0.025 + 0.02
		n.rotation.y += dt * 0.9
		if game.mode != "play":
			continue
		var d := n.global_position - me
		if Vector2(d.x, d.z).length() < 1.0 and absf(d.y - 0.6) < 1.4:
			_collect(it)


func _collect(it: Dictionary) -> void:
	_found[it.id] = true
	var n: Node3D = it.node
	var tw := n.create_tween()
	tw.tween_property(n, "position:y", n.position.y + 0.5, 0.35).set_ease(Tween.EASE_OUT)
	tw.parallel().tween_property(n, "scale", Vector3.ONE * 0.01, 0.35)
	tw.tween_callback(func(): n.visible = false)
	Sfx.play("duck")
	GameState.ducks_found = found_ids()
	var had_merch := bool(GameState.flags.get("merch", false))
	var had_all := bool(GameState.flags.get("ducks_all", false))
	_sync_flags()
	game.toast("Golden rubber duck %d/%d" % [count(), total()], "duck")
	game.hud.hint("wardrobe")   # the ducks unlock a fit: the first one is when the fits matter
	if bool(GameState.flags.get("merch", false)) and not had_merch:
		Sfx.play("fanfare")
		game.hud.show_banner("Eight ducks", "new fit unlocked: EPITA merch")
	elif bool(GameState.flags.get("ducks_all", false)) and not had_all:
		Sfx.play("fanfare")
		game.hud.show_banner("All twelve ducks", "a new page in the notebook")
	GameState.flags_changed.emit()
	print("[ducks] %s found: %d of %d (chapter %d)" % [it.id, count(), total(), Chapters.current()])
	game.save()
