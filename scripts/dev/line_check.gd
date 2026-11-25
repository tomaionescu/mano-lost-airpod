extends Node
## Dev check (docs/DESIGN.md V2-03): every subtitle card the dialogue data can show (res://dialogue/*.dlg, every
## branch, every response, every line of a random group: DialogueData.cards()) fits two lines of about 40
## characters at size M, laid out in a real subtitle label (Dialogue.make_label / fill_line) with the speaker's
## name and the continue mark. A card with {{…}} is measured filled in with the flags' defaults.
##   Godot --headless --path . res://scenes/dev/line_check.tscn      exit code 1 when a card is too long

var _names := {}
var _seen := {}   # "who|text" -> [who, name, text]
var _bad: Array = []


func _ready() -> void:
	GameState.use_test_paths()
	UITheme.init()
	var label := Dialogue.make_label()
	add_child(label)
	var mark := Dialogue.arrow_texture(0)
	_load_names()
	GameState.reset_flags()
	for c in DialogueData.cards():
		_check(String(c.who), DialogueData.format(String(c.text)))
	# the label lays a card out on the next frame; counting earlier reads the previous card
	for card in _seen.values():
		Dialogue.fill_line(label, card[0], card[1], Color.WHITE, card[2], Dialogue.SIZE_M, mark)
		await get_tree().process_frame
		if label.get_line_count() > 2:
			_bad.append([label.get_line_count(), "%s: %s" % [card[0], card[2]]])
	for line in _bad:
		print("[test] TOO LONG (%d lines) %s" % [line[0], line[1]])
	print("[test] line_check: %d cards checked, %d over two lines" % [_seen.size(), _bad.size()])
	get_tree().quit(1 if not _bad.is_empty() else 0)


func _load_names() -> void:
	for d in CastDefs.npc_defs():
		_names[d.id] = d.name
	for id in CastDefs.SPEAKERS:
		_names[id] = CastDefs.SPEAKERS[id].name
	_names["crowd"] = "Student"


func _check(who: String, text: String) -> void:
	var key := who + "|" + text
	if _seen.has(key):
		return
	# measured with the speaker's name, the longest way the card can show
	var who_name: String = "" if who in ["nar", "think"] else _names.get(who, "Student" if who.begins_with("crowd") else who.capitalize())
	_seen[key] = [who, who_name, text]
