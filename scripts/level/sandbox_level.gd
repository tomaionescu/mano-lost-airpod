class_name SandboxLevel
extends RefCounted
## Fallback level, used when assets/levels/campus.glb is missing or with `sandbox` on the command line: a
## courtyard-sized test ground with a few walls, benches and the same marker names the real level exports.

static func build() -> Node3D:
	var root := Node3D.new()
	root.name = "Sandbox"
	var ground := _box(root, Vector3(-40, -0.2, -30), Vector3(46, 0.0, 54), Color(0.52, 0.5, 0.47), 0.9)
	ground.name = "Ground"
	# a few walls and blocks so the camera, shadows and GI have something to work with
	for b in [[Vector3(-12, 0, 13), Vector3(-4, 9, 30)], [Vector3(9.5, 0, 6), Vector3(28, 8, 18.5)], [Vector3(-25, 0, -26), Vector3(20, 14, -5.3)],
			[Vector3(5.5, 0, 39.2), Vector3(28.5, 12, 50)], [Vector3(29.5, 0, 18.5), Vector3(40, 8, 37)]]:
		_box(root, b[0], b[1], Color(0.78, 0.74, 0.68), 0.85)
	for c in [Vector3(8.5, 0, 23), Vector3(14, 0, 33), Vector3(-1, 0, 32)]:
		_box(root, c + Vector3(-1.2, 0, -0.6), c + Vector3(1.2, 0.75, 0.6), Color(0.45, 0.33, 0.22), 0.8)
	for p in [[Vector3(6, 0, 27), 0.0], [Vector3(12.5, 0, 28.5), 0.3], [Vector3(18, 0, 30.5), 0.0]]:
		_box(root, p[0] + Vector3(-1, 0.72, -0.4), p[0] + Vector3(1, 0.78, 0.4), Color(0.6, 0.46, 0.32), 0.7)
	_marker(root, "SPAWN_player", Vector3(10, 0.05, 24), PI * 0.8)
	_marker(root, "NPC_toma", Vector3(12.5, 0.0, 27.8), PI)
	_marker(root, "NPC_ian", Vector3(5.0, 0.0, 28.0), PI / 2)
	_marker(root, "NPC_silvia", Vector3(7.0, 0.0, 28.0), -PI / 2)
	_marker(root, "NPC_anisha", Vector3(16, 0.0, 22), PI)
	_marker(root, "NPC_karim", Vector3(20, 0.0, 26), -PI / 2)
	_marker(root, "NPC_madame", Vector3(2, 0.0, 22), PI / 2)
	_marker(root, "NPC_prof", Vector3(22, 0.0, 33), PI)
	_marker(root, "NPC_theo", Vector3(-2.5, 0.0, 22), 2.6)
	for id in ["sleeper", "acu", "student2", "ines", "chloe", "madame2", "student3", "waiting"]:
		_marker(root, "NPC_" + id, Vector3(-30, -50, -30), 0.0)
	_marker(root, "SPOT_coin_planter", Vector3(14, 0, 34.2), 0.0, {"label": "Planter", "range": 1.7})
	_marker(root, "SPOT_coffee", Vector3(24, 0, 22), 0.0, {"label": "Coffee machine", "range": 1.6})
	_marker(root, "DUCK_test", Vector3(9, 0.075, 30), 0.0)
	return root


static func _box(root: Node3D, a: Vector3, b: Vector3, color: Color, rough: float) -> MeshInstance3D:
	var size := (b - a).abs()
	var mi := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = size
	mi.mesh = bm
	var m := StandardMaterial3D.new()
	m.albedo_color = color
	m.roughness = rough
	mi.material_override = m
	mi.position = (a + b) * 0.5
	root.add_child(mi)
	var body := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = size
	cs.shape = shape
	body.add_child(cs)
	mi.add_child(body)
	return mi


static func _marker(root: Node3D, name: String, pos: Vector3, yaw: float, extras := {}) -> void:
	var n := Node3D.new()
	n.name = name
	n.position = pos
	n.rotation.y = yaw
	if not extras.is_empty():
		n.set_meta("extras", extras)
	root.add_child(n)


## Room detection by fixed coordinates, for levels without ZONE_ markers.
static func zone_fallback(p: Vector3) -> Dictionary:
	if p.y < -2.0 and p.z > 39.3:
		return {"id": "under", "label": "The Under", "sub": "BDE - basement of cour Pasteur", "surface": "rubber"}
	if p.x > 9.5 and p.x < 28 and p.z > 6 and p.z < 18.4 and p.y < 1:
		return {"id": "amphi", "label": "Amphi 4", "sub": "cour Pasteur - east building", "surface": "wood"}
	if p.y > 3 and p.x < -4 and p.z < -16:
		return {"id": "sm14", "label": "SM14", "sub": "Bâtiment Voltaire - 1st floor", "surface": "carpet"}
	if p.y > 3 and p.x > -4 and p.x < 8 and p.z < -16:
		return {"id": "sm15", "label": "SM15", "sub": "Bâtiment Voltaire - 1st floor", "surface": "carpet"}
	if p.y > 3 and p.z < -5.3:
		return {"id": "volt_f1", "label": "Bâtiment Voltaire", "sub": "1st floor", "surface": "carpet"}
	if p.y < 3 and p.z < -5.4:
		return {"id": "volt_gf", "label": "Bâtiment Voltaire", "sub": "ground floor - accueil", "surface": "tile"}
	if p.z > -5.3 and p.z < 5.3:
		return {"id": "street", "label": "Rue Pasteur", "sub": "Le Kremlin-Bicêtre", "surface": "concrete"}
	if p.z >= 5.3 and p.z < 14.5 and p.x > 0 and p.x < 6.5:
		return {"id": "passage", "label": "", "sub": "", "surface": "concrete"}
	return {"id": "court", "label": "Cour Pasteur", "sub": "EPITA Paris - KB campus", "surface": "concrete"}
