class_name Film
extends RefCounted
## Ishita's disposable camera (V2-30): ten exposures for ten photo spots (data/world.json
## "photos"), then the group photo on the steps, the eleventh and last. A spot is taken in photo mode when the
## camera stands within its `range` of the spot's `pos` and looks within `tol` degrees of its `look` (a spot with no
## `look` only needs the range: the tour's stops), or by the story's `$ photo film` where Mano stands (Ishita's tour,
## the sunset). flags.photos_taken maps each spot taken to the chapter it was taken in; flags.film_shots counts the
## exposures. A spot already on the film is not taken twice ("dup"), so the film always has room for the spots left.

const EXPOSURES := 10


## Every photo spot, resolved: id -> {pos, look (Vector3 or null), range, tol (degrees), chapter, when, label, think}.
static func spots() -> Dictionary:
	var out := {}
	var sec := WorldData.section("photos")
	for id in sec:
		var e: Dictionary = sec[id]
		out[id] = {"id": String(id), "pos": WorldData.vec(e.get("pos", [0, 0, 0])), "look": WorldData.vec(e.look) if e.has("look") else null,
			"range": float(e.get("range", 4.0)), "tol": float(e.get("tol", 35.0)), "chapter": int(e.get("chapter", 1)),
			"when": String(e.get("when", "")), "label": String(e.get("label", id)), "think": String(e.get("think", ""))}
	return out


static func taken() -> Dictionary:
	var t = GameState.flags.get("photos_taken", {})
	return t if t is Dictionary else {}


static func left() -> int:
	return maxi(0, EXPOSURES - int(GameState.flags.get("film_shots", 0)))


## The camera is Mano's tonight (lent in SM14, chapter 1), the spot's chapter has come and its `when` holds.
static func open_now(s: Dictionary) -> bool:
	return bool(GameState.flags.get("camera", false)) and Chapters.current() >= int(s.chapter) \
		and (String(s.when) == "" or Conditions.eval(String(s.when)))


## The nearest spot whose range takes in `p` (taken or not), or {}.
static func near(p: Vector3) -> Dictionary:
	var best := {}
	var best_d := INF
	var all := spots()
	for id in all:
		var s: Dictionary = all[id]
		var d: float = s.pos.distance_to(p)
		if d <= float(s.range) and d < best_d:
			best_d = d
			best = s
	return best


## The open, untaken spot a camera at `from` looking at `look` frames, or {}.
static func framed(from: Vector3, look: Vector3) -> Dictionary:
	var all := spots()
	var t := taken()
	var aim := (look - from).normalized()
	for id in all:
		var s: Dictionary = all[id]
		if t.has(id) or not open_now(s) or s.pos.distance_to(from) > float(s.range):
			continue
		if s.look == null:
			return s
		var want: Vector3 = ((s.look as Vector3) - from).normalized()
		if rad_to_deg(aim.angle_to(want)) <= float(s.tol):
			return s
	return {}


## Marks spot `id` as on the film (in this chapter) and spends one exposure; "dup" when it was already taken.
static func take(id: String) -> String:
	var t := taken().duplicate()
	if t.has(id):
		return "dup"
	t[id] = Chapters.current()
	GameState.flags["photos_taken"] = t
	GameState.flags["film_shots"] = int(GameState.flags.get("film_shots", 0)) + 1
	return id


## `$ photo film` where Mano stands: the spot he is at goes on the film ("dup" if it is already on it; "" when no
## spot is near, an exposure all the same). Sets flags.last_photo.
static func take_at(p: Vector3) -> String:
	var s := near(p)
	var r := ""
	if s.is_empty():
		GameState.flags["film_shots"] = int(GameState.flags.get("film_shots", 0)) + 1
	else:
		r = take(String(s.id))
	GameState.flags["last_photo"] = r
	return r


## How many spots a chapter has (by the chapter they open in) and how many of those are on the film.
static func count_in(chapter: int) -> Vector2i:
	var all := spots()
	var t := taken()
	var n := 0
	var got := 0
	for id in all:
		if int(all[id].chapter) == chapter:
			n += 1
			if t.has(id):
				got += 1
	return Vector2i(got, n)
