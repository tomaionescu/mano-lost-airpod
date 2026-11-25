extends Node
## The headless test suite (V2-36): every test in TESTS, then a summary; exit code 1 on any failure.
##   Godot --headless --path . res://tests/test_runner.tscn [-- only=port,quest]
## Test scenes write nothing to the user folder: GameState sends saves, settings and snapshots to res://tests/out/
## (*.test.json). Each test is a script with `func run(t)`, where t is a Report (tests/support.gd).

const TESTS := {
	"compile": "res://tests/compile_check.gd",
	"validate": "res://tests/validate_dialogue.gd",
	"port": "res://tests/test_port.gd",
	"quest": "res://tests/test_quest.gd",
	"saves": "res://tests/test_saves.gd",
	"map": "res://tests/test_map.gd",
}
const Support := preload("res://tests/support.gd")


func _ready() -> void:
	GameState.use_test_paths()
	var only: Array = []
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("only="):
			only = Array(arg.substr(5).split(","))
	var total_fail := 0
	var total_pass := 0
	var lines: Array = []
	for key in TESTS:
		if not only.is_empty() and not key in only:
			continue
		var t := Support.Report.new()
		t.name = key
		print("[test] == %s" % key)
		var sc = load(TESTS[key])
		if sc == null or not (sc as Script).can_instantiate():
			t.fail("%s does not load" % TESTS[key])
		else:
			var inst = sc.new()
			await inst.run(t)
		GameState.reset_flags()
		total_fail += t.failed
		total_pass += t.passed
		lines.append("[test] %s: %d passed, %d failed, %d warnings" % [key, t.passed, t.failed, t.warned])
	for l in lines:
		print(l)
	print("[test] test_runner: %d passed, %d failed" % [total_pass, total_fail])
	get_tree().quit(1 if total_fail > 0 else 0)
