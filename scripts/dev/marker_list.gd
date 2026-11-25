extends Node
## Dev: every gameplay marker in assets/levels/campus.glb with its position, written to
## tests/fixtures/markers.json so the headless tests can check story references (npc:, spot:, anchors) and walk
## the quest without loading the level. Ids are read the way LevelBinder reads them. Re-run after a level build:
##   Godot --headless --path . res://scenes/dev/marker_list.tscn -- out=tests/fixtures/markers.json

const LEVEL := "res://assets/levels/campus.glb"
const PREFIXES := ["SPAWN_", "NPC_", "SPOT_", "ANCHOR_", "DUCK_", "ZONE_", "PATH_", "PORTAL_", "CAM_"]


func _ready() -> void:
	var out := "tests/fixtures/markers.json"
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("out="):
			out = arg.substr(4)
	var root := (load(LEVEL) as PackedScene).instantiate() as Node3D
	add_child(root)
	var found: Array = []
	_collect(root, found)
	var data := {"version": 1, "source": LEVEL, "spawn": [], "npcs": {}, "spots": {}, "anchors": {}, "ducks": {},
		"zones": {}, "paths": {}, "portals": {}, "cams": {}}
	for n: Node3D in found:
		var nm := String(n.name)
		var xf := n.global_transform
		var p := _v(xf.origin)
		var f := xf.basis.z
		var yaw := snappedf(rad_to_deg(atan2(f.x, f.z)), 0.1)
		var ex: Dictionary = n.get_meta("extras", {}) if n.has_meta("extras") else {}
		if nm == "SPAWN_player":
			data.spawn = p
		elif nm.begins_with("NPC_"):
			data.npcs[nm.substr(4)] = {"pos": p, "yaw": yaw, "extras": ex}
		elif nm.begins_with("SPOT_"):
			data.spots[nm.substr(5)] = {"pos": p, "label": ex.get("label", nm.substr(5).capitalize()), "range": float(ex.get("range", 1.8))}
		elif nm.begins_with("ANCHOR_"):
			data.anchors[nm.substr(7)] = {"pos": p, "yaw": yaw}
		elif nm.begins_with("DUCK_"):
			data.ducks[nm.substr(5)] = {"pos": p}
		elif nm.begins_with("ZONE_"):
			var id := nm.substr(5).get_slice(".", 0)
			data.zones[id] = {"pos": p, "half": _v(xf.basis.get_scale().abs()), "label": ex.get("label", ""), "sub": ex.get("sub", ""),
				"surface": ex.get("surface", "concrete")}
		elif nm.begins_with("PATH_"):
			var key := nm.substr(5).rsplit("_", true, 1)[0]
			if not data.paths.has(key):
				data.paths[key] = []
			data.paths[key].append(p)
		elif nm.begins_with("PORTAL_"):
			var body := nm.substr(7)
			var key := body.rsplit("_", true, 1)[0].replace("__", "|")
			if not data.portals.has(key):
				data.portals[key] = []
			data.portals[key].append(p)
		elif nm.begins_with("CAM_"):
			data.cams[nm.substr(4)] = {"pos": p, "yaw": yaw}
	var file := FileAccess.open(ProjectSettings.globalize_path("res://" + out), FileAccess.WRITE)
	file.store_string(JSON.stringify(data, " ", true))
	file.close()
	print("[test] marker_list: %d npcs, %d spots, %d anchors, %d ducks, %d zones -> %s" % [data.npcs.size(), data.spots.size(),
		data.anchors.size(), data.ducks.size(), data.zones.size(), out])
	get_tree().quit(0)


static func _v(v: Vector3) -> Array:
	return [snappedf(v.x, 0.001), snappedf(v.y, 0.001), snappedf(v.z, 0.001)]


func _collect(n: Node, out: Array) -> void:
	var nm := String(n.name)
	for p in PREFIXES:
		if nm.begins_with(p) and n is Node3D:
			out.append(n)
			break
	for c in n.get_children():
		_collect(c, out)
