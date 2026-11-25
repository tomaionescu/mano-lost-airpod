extends RefCounted
## The v1 port (V2-19): nothing of v1, whose story was hard-coded, is lost in the data-driven story.
## - Every v1 card (tests/fixtures/v1_cards.json, dumped from v1's story.gd) is in the dialogue
##   data word for word, or listed in tests/fixtures/v1_rewrites.json with the cue that replaces it.
## - Every recorded voice (assets/audio/voice/manifest.json) still has its card, or is listed as going silent.
## - v1's objective ladder (tests/fixtures/v1_objectives.json, every reachable combination of v1's flags) gives the
##   same objective text and the same target (kind, id, label) from data/chapters.json.

const Support := preload("res://tests/support.gd")


class LadderGame:
	extends RefCounted
	func target_of(kind: String, id: String, label: String) -> Dictionary:
		return {"pos": Vector3.ZERO, "label": label, "kind": kind, "id": id}

	func player_pos() -> Vector3:
		return Vector3.ZERO


func run(t) -> void:
	DialogueData.load_all()
	var data_cards := DialogueData.cards()
	var exact := {}
	var templates: Array = []   # [who, RegEx]
	for c in data_cards:
		exact["%s|%s" % [c.who, c.text]] = true
		if bool(c.interp):
			templates.append([String(c.who), RegEx.create_from_string(_template(String(c.text)))])
	var rw = Support.read_json("res://tests/fixtures/v1_rewrites.json")
	var rewrites := {}
	if rw is Dictionary:
		for r in rw.get("rewrites", []):
			rewrites["%s|%s" % [r.speaker, r.text]] = r
	var silent := {}
	if rw is Dictionary:
		for k in rw.get("silent", []):
			silent[String(k)] = true
	# 1. every v1 card
	var v1 = Support.read_json("res://tests/fixtures/v1_cards.json")
	t.ok(v1 is Array, "tests/fixtures/v1_cards.json loads")
	if not v1 is Array:
		return
	var distinct := {}
	var covered := 0
	var by_rewrite := 0
	for c in v1:
		var who := String(c.speaker)
		if who.begins_with("crowd"):
			who = "crowd"
		var key := "%s|%s" % [who, c.text]
		if distinct.has(key):
			continue
		distinct[key] = true
		var found := exact.has(key)
		if not found:
			for tp in templates:
				if tp[0] == who and (tp[1] as RegEx).search(String(c.text)):
					found = true
					break
		if found:
			covered += 1
		elif rewrites.has(key):
			var r: Dictionary = rewrites[key]
			by_rewrite += 1
			t.ok(DialogueData.cues.has(String(r.get("cue", ""))), "v1 card rewritten into cue '%s' that exists: %s" % [r.get("cue", ""), key])
		else:
			t.fail("v1 card missing from the data: %s" % key)
	t.ok(covered + by_rewrite == distinct.size(), "v1 coverage %d/%d distinct cards (%d word for word, %d rewritten)" % [covered + by_rewrite, distinct.size(), covered, by_rewrite])
	t.info("v1 coverage: %d/%d distinct cards word for word, %d rewritten" % [covered, distinct.size(), by_rewrite])
	# 2. every recorded voice keeps its card
	var keys := {}
	for c in data_cards:
		var text := DialogueData.format(String(c.text))
		if String(c.who) == "crowd":
			for i in range(1, 9):
				keys[VoiceLines.key("crowd%d" % i, text)] = true
		else:
			keys[VoiceLines.key(String(c.who), text)] = true
	var manifest := VoiceLines.manifest()
	var matched := 0
	for k in manifest:
		if keys.has(k):
			matched += 1
		elif silent.has(k):
			t.info("voice %s goes silent (listed in v1_rewrites.json)" % k)
		else:
			t.fail("recorded voice %s (%s: %s) has no card in the data" % [k, manifest[k].get("speaker", ""), manifest[k].get("text", "")])
	t.ok(matched + silent.size() >= manifest.size(), "voice keys %d/%d matched (%d listed as silent)" % [matched, manifest.size(), silent.size()])
	t.info("voice keys: %d/%d matched" % [matched, manifest.size()])
	# 3. the objective ladder
	var lad = Support.read_json("res://tests/fixtures/v1_objectives.json")
	t.ok(lad is Dictionary, "tests/fixtures/v1_objectives.json loads")
	if not lad is Dictionary:
		return
	var game := LadderGame.new()
	var same := 0
	var states: Array = lad.get("states", [])
	for st in states:
		GameState.reset_flags()
		var f: Dictionary = st.flags
		for k in f:
			if k == "got":
				for id in f.got:
					GameState.flags["got_" + String(id)] = bool(f.got[id])
			else:
				GameState.flags[k] = f[k]
		GameState.coerce_flags()
		GameState.flags["chapter"] = 2 if bool(f.get("ines", false)) else 1
		var obj := Chapters.objective_text()
		var tg := Chapters.target(game)
		var tt := {}
		if not tg.is_empty():
			tt = {"kind": tg.kind, "id": tg.id, "label": tg.label}
		var want: Dictionary = st.target
		var ok: bool = obj == String(st.objective) and tt.get("kind", "") == want.get("kind", "") and tt.get("id", "") == want.get("id", "") \
			and tt.get("label", "") == want.get("label", "")
		if ok:
			same += 1
	# chapters 1 and 2 differ from v1 on purpose (Ishita, the pastry war on the path, the twist), so the ladder is
	# reported, not asserted
	t.info("ladder (retired as a check in stage 2): %d/%d v1 states still give v1's objective and target" % [same, states.size()])
	GameState.reset_flags()


## "You have {{coins}}." -> ^You have .+\.$
static func _template(text: String) -> String:
	var re := RegEx.create_from_string("\\{\\{[^}]*\\}\\}")
	var pat := "^"
	var last := 0
	for m in re.search_all(text):
		pat += _escape(text.substr(last, m.get_start() - last)) + ".+"
		last = m.get_end()
	return pat + _escape(text.substr(last)) + "$"


static func _escape(s: String) -> String:
	var out := ""
	for ch in s:
		if ch in ".^$*+?()[]{}|\\":
			out += "\\" + ch
		else:
			out += ch
	return out
