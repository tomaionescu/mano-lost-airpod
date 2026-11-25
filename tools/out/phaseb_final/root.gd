extends SceneTree
# Review launcher: the game's main scene with walk.gd instead of autotest.gd.
# A -s run: GameState uses the test paths (res://tests/out/), never the user's save.
func _initialize() -> void:
	print("[walk] save path ", root.get_node("GameState").SAVE_PATH)
	var main = load("res://scenes/main.tscn").instantiate()
	root.add_child(main)
	current_scene = main
	var d = load("res://tools/out/phaseb_final/walk.gd").new()
	d.game = main
	d.plan = "walk"
	main.add_child(d)
