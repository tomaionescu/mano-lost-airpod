extends "res://scripts/dev/line_check.gd"
## Dev: every subtitle card the dialogue data can show (DialogueData.cards(): every branch, response and random
## line), written as JSON for the voice pipeline (tools/py/voice_build.py). Each card: speaker id, display name,
## exact text, and its voice key (VoiceLines.key, the one the game looks up). A `crowd` line is written once per
## background student model (crowd1..crowd8), whose voices are aliased by build (VoiceLines.ALIAS).
##   Godot --headless --path . res://scenes/dev/voice_lines.tscn -- out=tools/out/voices/cards.json


func _ready() -> void:
	GameState.use_test_paths()
	_load_names()
	GameState.reset_flags()
	for c in DialogueData.cards():
		var text := DialogueData.format(String(c.text))
		if String(c.who) == "crowd":
			for i in range(1, 9):
				_check("crowd%d" % i, text)
		else:
			_check(String(c.who), text)
	var out := "tools/out/voices/cards.json"
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("out="):
			out = arg.substr(4)
	var cards: Array = []
	for card in _seen.values():
		cards.append({"speaker": card[0], "name": card[1], "text": card[2], "key": VoiceLines.key(card[0], card[2])})
	var f := FileAccess.open(ProjectSettings.globalize_path("res://" + out), FileAccess.WRITE)
	f.store_string(JSON.stringify(cards, "  "))
	f.close()
	print("[test] voice_lines: %d cards -> %s" % [cards.size(), out])
	get_tree().quit(0)
