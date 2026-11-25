extends Node
## Dev: the objective ladder of v1, whose story was hard-coded in story.gd, as a fixture. Evaluates
## Story.objective() and Story.target() (its kind, id and label) over every reachable combination of v1's quest
## flags and writes them to tests/fixtures/v1_objectives.json; tests/test_port.gd checks that the data-driven
## Chapters give the same text and target in every one of these states. Reproducing it needs v1's story.gd:
##   Godot --headless --path . res://scenes/dev/v1_ladder.tscn -- out=tests/fixtures/v1_objectives.json


## Stands in for main.gd: every target resolves to the same point, so the nearest-coin rule falls back to the
## list order (planter before sofa), as the data's `targets` list does.
class FakeGame:
	extends RefCounted
	func target_of(kind: String, id: String, label: String) -> Dictionary:
		return {"pos": Vector3.ZERO, "label": label, "kind": kind, "id": id}

	func player_pos() -> Vector3:
		return Vector3.ZERO


func _ready() -> void:
	var out := "tests/fixtures/v1_objectives.json"
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("out="):
			out = arg.substr(4)
	var story = Story.new(FakeGame.new())
	var states: Array = []
	# quest progress is monotone (toma, then ines, then karim); everything else can happen at any point: the sign,
	# Mme Dupont at the cafeteria, coins, the coffee and giving it, in any order
	for level in 4:
		for bits in 32:
			for coins in 3:
				for got in [{}, {"planter": true}, {"sofa": true}, {"planter": true, "sofa": true}]:
					for found in [false, true]:
						var f := {"toma": level >= 1, "ines": level >= 2, "karim": level >= 3,
							"sign": bool(bits & 1), "madame_met": bool(bits & 2), "coffee": bool(bits & 4),
							"paid": bool(bits & 8), "coffee_given": bool(bits & 16), "coins": coins, "got": got, "found": found}
						if found and not (level == 3 and f.coffee_given):
							continue   # found needs Karim's admission and the coffee given
						states.append(f)
	var rows: Array = []
	for f in states:
		GameState.reset_flags()
		for k in f:
			GameState.flags[k] = f[k]
		var t: Dictionary = story.target()
		var tt := {}
		if not t.is_empty():
			tt = {"kind": t.kind, "id": t.id, "label": t.label}
		rows.append({"flags": f, "objective": story.objective(), "target": tt})
	var file := FileAccess.open(ProjectSettings.globalize_path("res://" + out), FileAccess.WRITE)
	file.store_string(JSON.stringify({"version": 1, "source": "scripts/story/story.gd (v1)", "states": rows}, " "))
	file.close()
	print("[test] v1_ladder: %d states -> %s" % [rows.size(), out])
	get_tree().quit(0)
