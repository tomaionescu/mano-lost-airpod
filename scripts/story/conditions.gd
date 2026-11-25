class_name Conditions
extends RefCounted
## The story's conditions (docs/ARCHITECTURE.md): `if`/`elif` in the .dlg files, `[if …]` on lines
## and responses, and the `when`/`done` of chapters.json and world.json. An expression reads story flags by name
## and may use `and or not`, `== != < <= > >=`, `in`, numbers, "double-quoted strings", true, false, arrays, and two
## helpers: clock_after("18:50") and night() (the blue, night and late presets).
##   Conditions.eval("karim and madame_met and coins < 2")
## A flag that is not set yet reads as its default from data/flags.json. Godot's Expression does the work; every
## flag name is renamed to f_<name> first, so a flag may share a name with a built-in function (`sign`).

const KEYWORDS := ["and", "or", "not", "in", "true", "false", "null"]
const HELPERS := ["clock_after", "clock_before", "night"]
const NIGHT_TIMES := ["blue", "night", "late"]

static var _cache := {}          # expression text -> {"expr": Expression, "names": [flag names]} or {"error": msg}
static var _re: RegEx = null
static var _helper: Helper = null


## The helper functions an expression can call.
class Helper:
	extends RefCounted

	func clock_after(hhmm: String) -> bool:
		return int(GameState.flags.get("clock", 0)) >= Conditions.minutes(hhmm)

	func clock_before(hhmm: String) -> bool:
		return int(GameState.flags.get("clock", 0)) < Conditions.minutes(hhmm)

	func night() -> bool:
		return String(GameState.flags.get("time", "golden")) in Conditions.NIGHT_TIMES


## True or false; an empty expression is true. A bad expression is false (and an error, once per expression).
static func eval(text: String) -> bool:
	text = text.strip_edges()
	if text == "" or text == "true":
		return true
	if text == "false":
		return false
	var c := _compiled(text)
	if c.has("error"):
		return false
	var inputs: Array = []
	for n in c.names:
		inputs.append(GameState.flags.get(n, GameState.flag_default(n)))
	if _helper == null:
		_helper = Helper.new()
	var v = (c.expr as Expression).execute(inputs, _helper, false)
	if (c.expr as Expression).has_execute_failed():
		push_error("Conditions: cannot evaluate '%s': %s" % [text, (c.expr as Expression).get_error_text()])
		return false
	return bool(v) if v != null else false


## Why `text` does not parse, or "" when it does (the validator).
static func error_of(text: String) -> String:
	text = text.strip_edges()
	if text == "" or text == "true" or text == "false":
		return ""
	return String(_compiled(text).get("error", ""))


## The flag names an expression reads (not keywords, helpers or strings).
static func identifiers(text: String) -> Array:
	return _rewrite(text)[1]


## "18:50" -> 1130 minutes after midnight; past midnight the clock counts on ("00:10" is not used: write 24:10).
static func minutes(hhmm: String) -> int:
	var p := hhmm.strip_edges().split(":")
	if p.size() != 2 or not p[0].is_valid_int() or not p[1].is_valid_int():
		return -1
	return int(p[0]) * 60 + int(p[1])


## 1130 -> "18:50"; 1450 -> "00:10".
static func clock_text(m: int) -> String:
	return "%02d:%02d" % [(m / 60) % 24, m % 60]


static func _compiled(text: String) -> Dictionary:
	if _cache.has(text):
		return _cache[text]
	var rw := _rewrite(text)
	var names: Array = rw[1]
	var inputs := PackedStringArray()
	for n in names:
		inputs.append("f_" + n)
	var e := Expression.new()
	var c := {}
	if e.parse(rw[0], inputs) != OK:
		c = {"error": e.get_error_text()}
		push_error("Conditions: cannot parse '%s': %s" % [text, e.get_error_text()])
	else:
		c = {"expr": e, "names": names}
	_cache[text] = c
	return c


## [rewritten text, flag names]: every bare identifier that is not a keyword, a helper call or inside a string
## becomes f_<name>.
static func _rewrite(text: String) -> Array:
	if _re == null:
		_re = RegEx.create_from_string("\"(?:[^\"\\\\]|\\\\.)*\"|[A-Za-z_][A-Za-z0-9_]*|\\s+|.")
	var out := ""
	var names: Array = []
	var ms := _re.search_all(text)
	for i in ms.size():
		var tok := ms[i].get_string()
		var c0 := tok.substr(0, 1)
		if (c0 >= "a" and c0 <= "z") or (c0 >= "A" and c0 <= "Z") or c0 == "_":
			if tok in KEYWORDS:
				out += tok
				continue
			# a call: the next token that is not blank is "("
			var j := i + 1
			while j < ms.size() and ms[j].get_string().strip_edges() == "":
				j += 1
			if j < ms.size() and ms[j].get_string() == "(":
				out += tok
				continue
			out += "f_" + tok
			if not tok in names:
				names.append(tok)
		else:
			out += tok
	return [out, names]
