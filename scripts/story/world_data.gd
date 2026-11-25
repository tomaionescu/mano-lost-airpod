class_name WorldData
extends RefCounted
## Story positions and conditions as data (data/world.json): points, extra spots, the
## conditions for spots and characters that come and go with the story, and the names places go by on the area
## banner. Level markers (campus.glb) win; a world.json entry with "override": true replaces one. Positions are game
## metres; yaw is in degrees, 0 facing +Z (south).

const FILE := "res://data/world.json"
const WORDS := "res://data/words.json"

static var data := {}
static var words := {}


static func load_data(force := false) -> void:
	if not data.is_empty() and not force:
		return
	data = _read(FILE)
	words = _read(WORDS).get("words", {})


static func _read(path: String) -> Dictionary:
	if not FileAccess.file_exists(path):
		push_error("WorldData: %s is missing" % path)
		return {}
	var j := JSON.new()
	if j.parse(FileAccess.get_file_as_string(path)) != OK or not j.data is Dictionary:
		push_error("WorldData: %s does not parse: %s (line %d)" % [path, j.get_error_message(), j.get_error_line()])
		return {}
	return j.data


static func section(name: String) -> Dictionary:
	load_data()
	var s = data.get(name, {})
	return s if s is Dictionary else {}


## When a level spot (SPOT_<id>) can be used, as a condition; "" means always.
static func spot_when(id: String) -> String:
	return String(section("spot_when").get(id, ""))


## When a character is on campus (madame at the cafeteria until the coffee, madame2 at the accueil after it).
static func npc_when(id: String) -> String:
	return String(section("npc_when").get(id, ""))


## How a ZONE_ is named on the area banner's place line ("cour Pasteur"), or "".
static func zone_name(id: String) -> String:
	return String(section("zone_names").get(id, ""))


## A named point: {pos: Vector3, yaw: radians, via: [Vector3]} or {}. `via` is the way a character walks there
## (main.restage with `walk`: through the aisles, not across the desks).
static func point(id: String) -> Dictionary:
	var p = section("points").get(id, null)
	if not p is Dictionary or not p.has("pos"):
		return {}
	var via: Array = []
	for v in p.get("via", []):
		via.append(vec(v))
	return {"pos": vec(p.pos), "yaw": deg_to_rad(float(p.get("yaw", 0.0))), "via": via}


## The extra spots world.json adds: id -> {pos, label, range, kind, when}.
static func spots() -> Dictionary:
	var out := {}
	var s := section("spots")
	for id in s:
		var e: Dictionary = s[id]
		out[id] = {"pos": vec(e.get("pos", [0, 0, 0])), "label": String(e.get("label", String(id).capitalize())),
			"range": float(e.get("range", 1.8)), "kind": String(e.get("kind", "look")), "when": String(e.get("when", "")),
			"override": bool(e.get("override", false))}
	return out


## The sit-downs (V2-14, docs/DESIGN.md §4.1): data/world.json "sits", id -> {pos, yaw, stand, chapter, when, clock,
## label, cue, music, journal, cams, move, offer}. See sit().
static func sit_ids() -> Array:
	return section("sits").keys()


## One sit-down, resolved: {id, pos: Vector3, yaw: radians, stand: Vector3 (where Mano gets up to; INF: where he
## sat down from), spot: Vector3 (where the "Sit" prompt is), chapter: int, when: condition, clock: ["HH:MM",
## "HH:MM"] or [], label, cue (sit.<id>: the thought), music (a data/songs.json stem, or "@flag" for the stem a flag
## holds), journal (one line in Mano's voice), offer ("spot": a prompt in the world; "story": only `$ sit`),
## cams: {a, b, c: {from, look, fov}}, move: {orbit: deg/s, drift: [x, y, z] m/s}}, or {}.
static func sit(id: String) -> Dictionary:
	var e = section("sits").get(id, null)
	if not e is Dictionary or not e.has("pos"):
		return {}
	var pos := vec(e.pos)
	var yaw := deg_to_rad(float(e.get("yaw", 0.0)))
	var cams := {}
	for k in e.get("cams", {}):
		cams[k] = sit_cam(e.cams[k], pos, yaw)
	return {"id": id, "pos": pos, "yaw": yaw, "stand": vec(e.stand) if e.has("stand") else Vector3.INF,
		"spot": vec(e.spot) if e.has("spot") else pos, "chapter": int(e.get("chapter", 0)), "when": String(e.get("when", "")),
		"clock": e.get("clock", []), "label": String(e.get("label", "Sit down")), "cue": String(e.get("cue", "sit." + id)),
		"music": String(e.get("music", "")), "journal": String(e.get("journal", "")), "offer": String(e.get("offer", "spot")),
		"cams": cams, "move": e.get("move", {}), "range": float(e.get("range", 1.4))}


## A sit camera: absolute {from, look, fov}, or relative to the seat: {"rel": [degrees from where Mano faces, metres
## out, height], "look_h": height of the point looked at over the seat, "look_rel": [degrees, metres] to look at a
## point out in front of him instead, "fov"}.
static func sit_cam(c: Dictionary, pos: Vector3, yaw: float) -> Dictionary:
	var out := {"fov": float(c.get("fov", 40.0))}
	if c.has("rel"):
		var r: Array = c.rel
		var a := yaw + deg_to_rad(float(r[0]))
		out["from"] = pos + Vector3(sin(a), 0, cos(a)) * float(r[1]) + Vector3.UP * float(r[2])
	else:
		out["from"] = vec(c.get("from", [0, 0, 0]))
	if c.has("look"):
		out["look"] = vec(c.look)
	elif c.has("look_rel"):
		var lr: Array = c.look_rel
		var b := yaw + deg_to_rad(float(lr[0]))
		out["look"] = pos + Vector3(sin(b), 0, cos(b)) * float(lr[1]) + Vector3.UP * float(c.get("look_h", 0.9))
	else:
		out["look"] = pos + Vector3.UP * float(c.get("look_h", 0.95))
	return out


## Where the finder app saw the AirPod last (data/world.json "finder_places"): {pos, label} or {}.
static func finder_place(id: String) -> Dictionary:
	var e = section("finder_places").get(id, null)
	if not e is Dictionary:
		return {}
	return {"pos": vec(e.get("pos", [0, 0, 0])), "label": String(e.get("label", id))}


## A word or name from data/words.json ({{word.key}} in dialogue).
static func word(key: String) -> String:
	load_data()
	return String(words.get(key, ""))


static func vec(a) -> Vector3:
	if a is Vector3:
		return a
	if a is Array and a.size() >= 3:
		return Vector3(float(a[0]), float(a[1]), float(a[2]))
	return Vector3.ZERO
