extends RefCounted
## Every GDScript in the project loads and compiles, autoloads and class names included (what `--check-only -s`
## cannot do for scripts that use GameState or Sfx).

const ROOTS := ["res://scripts", "res://tests"]


func run(t) -> void:
	var paths: Array = []
	for r in ROOTS:
		_walk(r, paths)
	var bad := 0
	for p in paths:
		var sc = load(p)
		var ok: bool = sc != null and (sc as GDScript).can_instantiate()
		if not ok:
			bad += 1
		t.ok(ok, "%s compiles" % p)
	t.info("%d scripts loaded, %d failed" % [paths.size(), bad])


func _walk(dir: String, out: Array) -> void:
	var d := DirAccess.open(dir)
	if d == null:
		return
	for f in d.get_files():
		if f.ends_with(".gd"):
			out.append(dir.path_join(f))
	for sub in d.get_directories():
		if not sub.begins_with("."):
			_walk(dir.path_join(sub), out)
