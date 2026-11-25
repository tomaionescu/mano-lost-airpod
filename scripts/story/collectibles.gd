class_name Collectibles
extends RefCounted
## The night's three kinds of collectible (V2-30, docs/DESIGN.md §3.8): the twelve golden ducks (data/world.json ducks,
## GameState.ducks_found), Ishita's film (world.json photos, flags.photos_taken) and the six moments (world.json
## sits, flags.moments). Chapter select keeps them: a replay starts from the chapter's snapshot, with that night's
## choices, and everything found so far that night (best_known, merge). Counts by the chapter each one opens in.


## Everything found so far: the union of the save, every chapter snapshot and what is in memory now.
## {ducks: [ids], photos: {id: chapter}, moments: [ids]}
static func best_known() -> Dictionary:
	var out := {"ducks": GameState.ducks_found.duplicate(), "photos": _dict(GameState.flags.get("photos_taken", {})).duplicate(),
		"moments": Array(GameState.flags.get("moments", [])).duplicate()}
	var saves: Array = [GameState.read_save()]
	for n in GameState.chapter_saves():
		saves.append(GameState.read_chapter_save(n))
	for d in saves:
		if d is Dictionary:
			_add(out, d.get("ducks", []), _dict(d.get("flags", {}).get("photos_taken", {})), d.get("flags", {}).get("moments", []))
	return out


static func _add(out: Dictionary, ducks: Array, photos: Dictionary, moments: Array) -> void:
	for id in ducks:
		if not id in out.ducks:
			out.ducks.append(id)
	for id in photos:
		if not out.photos.has(id) or int(photos[id]) < int(out.photos[id]):
			out.photos[id] = int(photos[id])
	for id in moments:
		if not id in out.moments:
			out.moments.append(id)


static func _dict(v) -> Dictionary:
	return v if v is Dictionary else {}


## Puts `finds` (best_known) into the state being played, and what follows from them: the duck count, the merch
## fit at eight, all twelve, the film's exposures, all six moments.
static func merge(finds: Dictionary) -> void:
	if finds.is_empty():
		return
	var cur := {"ducks": GameState.ducks_found.duplicate(), "photos": _dict(GameState.flags.get("photos_taken", {})).duplicate(),
		"moments": Array(GameState.flags.get("moments", [])).duplicate()}
	_add(cur, finds.get("ducks", []), finds.get("photos", {}), finds.get("moments", []))
	GameState.ducks_found = cur.ducks
	GameState.flags["photos_taken"] = cur.photos
	GameState.flags["film_shots"] = maxi(int(GameState.flags.get("film_shots", 0)), cur.photos.size())
	GameState.flags["moments"] = cur.moments
	GameState.flags["duck_count"] = cur.ducks.size()
	if cur.ducks.size() >= Ducks.MERCH_AT:
		GameState.flags["merch"] = true
	if cur.ducks.size() >= WorldData.section("ducks").size():
		GameState.flags["ducks_all"] = true
	if cur.moments.size() >= WorldData.sit_ids().size():
		GameState.flags["moments_all"] = true


## For chapter `n`: how many of the ducks, photo spots and moments that open in it are found in `finds`.
## {ducks: Vector2i(found, of), film: Vector2i, moments: Vector2i}
static func in_chapter(n: int, finds: Dictionary) -> Dictionary:
	var ducks := Vector2i.ZERO
	var dsec := WorldData.section("ducks")
	for id in dsec:
		if int(dsec[id].get("chapter", 1)) == n:
			ducks += Vector2i(1 if id in finds.get("ducks", []) else 0, 1)
	var film := Vector2i.ZERO
	var psec := WorldData.section("photos")
	for id in psec:
		if int(psec[id].get("chapter", 1)) == n:
			film += Vector2i(1 if finds.get("photos", {}).has(id) else 0, 1)
	var moments := Vector2i.ZERO
	for id in WorldData.sit_ids():
		if int(WorldData.sit(String(id)).get("chapter", 0)) == n:
			moments += Vector2i(1 if id in finds.get("moments", []) else 0, 1)
	return {"ducks": ducks, "film": film, "moments": moments}
