extends RefCounted
## Saves (V2-33): a round trip; a version 1 save migrates (got.* to got_*, the chapter, ints); a truncated save
## falls back to its .bak; a crash between the two renames still leaves a readable save; chapter snapshots and
## clearing them; which runs are sandboxed (a bare `autotest` too); and test runs write only under
## res://tests/out/, never to the player's own files (the sha1s of the developer's are checked).

const Support := preload("res://tests/support.gd")
## A test run must leave the player's real save and settings byte for byte as they are.
const REAL_FILES := ["save_v1.json", "settings_v1.json"]


func _real_sha1(name: String) -> String:
	var p := OS.get_user_data_dir().path_join(name)
	if not FileAccess.file_exists(p):
		return ""
	var h := HashingContext.new()
	h.start(HashingContext.HASH_SHA1)
	h.update(FileAccess.get_file_as_bytes(p))
	return h.finish().hex_encode()


func run(t) -> void:
	var before := {}
	for name in REAL_FILES:
		before[name] = _real_sha1(name)
	t.ok(GameState.sandboxed(), "test paths are on (GameState.use_test_paths)")
	t.ok(GameState.SAVE_PATH.begins_with(GameState.TEST_DIR) and GameState.SAVE_PATH.ends_with(".test.json"), "the save goes to %s" % GameState.SAVE_PATH)
	t.ok(GameState.SETTINGS_PATH.begins_with(GameState.TEST_DIR), "settings go to %s" % GameState.SETTINGS_PATH)
	t.ok(not GameState.photos_dir().contains("Pictures"), "photo mode writes to %s, not ~/Pictures" % GameState.photos_dir())
	t.ok(GameState.chapter_save_path(2).begins_with(GameState.TEST_DIR), "snapshots go to %s" % GameState.chapter_save_path(2))
	# which runs get sandboxed paths: every autotest form main.gd starts a plan for, and test scenes
	for c in [[["--path", ".", "autotest"], "autotest"], [["autotest=basic"], "autotest"], [["autotest=story", "chapter=2"], "autotest"],
			[["res://tests/test_runner.tscn"], "test"], [["res://scenes/dev/line_check.tscn", "autotest=x"], "test"],
			[["--path", ".", "-s", "tools/out/toma_like4/scripts/ig7.gd", "--", "out=x"], "test"],
			[["--path", ".", "res://tools/out/phaseb_verify/s3/root.tscn"], "test"],
			[["--path", ".", "--resolution", "1600x900"], ""], [["vplan=saves"], ""]]:
		t.ok(GameState.run_kind(c[0]) == c[1], "run_kind(%s) is '%s' (%s)" % [" ".join(c[0]), c[1], GameState.run_kind(c[0])])
	GameState.clear_save()
	t.ok(not GameState.has_save(), "no save after clear_save")
	# round trip
	GameState.reset_flags()
	GameState.flags["toma"] = true
	GameState.flags["coins"] = 2
	GameState.flags["got_sofa"] = true
	GameState.flags["chapter"] = 2
	GameState.flags["clock"] = 1115
	GameState.flags["clues"] = ["one", "two"]
	GameState.outfit = "classic"
	var xf := Transform3D(Basis(Vector3.UP, 1.2), Vector3(1.5, -3.6, 42.0))
	GameState.write_save(xf)
	var d = GameState.read_save()
	t.ok(d is Dictionary and int(d.get("version", 0)) == 2, "a saved game reads back as version 2")
	GameState.reset_flags()
	GameState.apply_save(d)
	t.ok(GameState.flags.coins is int and GameState.flags.coins == 2, "coins come back as the int 2 (%s)" % type_string(typeof(GameState.flags.coins)))
	t.ok(GameState.flags.chapter is int and GameState.flags.chapter == 2, "the chapter comes back as an int")
	t.ok(GameState.flags.clock is int and GameState.flags.clock == 1115, "the clock comes back as an int")
	t.ok(GameState.flags.got_sofa == true and GameState.flags.toma == true, "flags survive the round trip")
	t.ok(GameState.flags.clues == ["one", "two"], "clues survive the round trip")
	t.ok(GameState.outfit == "classic", "the outfit survives the round trip")
	t.ok(Vector3(d.pos[0], d.pos[1], d.pos[2]).is_equal_approx(xf.origin), "the position survives the round trip")
	# a second save keeps the first as .bak; a truncated main file falls back to it
	GameState.flags["coins"] = 5
	GameState.write_save(xf)
	t.ok(FileAccess.file_exists(GameState.SAVE_PATH + ".bak"), "the previous save is kept as .bak")
	var f := FileAccess.open(GameState.SAVE_PATH, FileAccess.WRITE)
	f.store_string("{\"version\": 2, \"flags\": {\"coins\": 5")
	f.close()
	d = GameState.read_save()
	t.ok(d is Dictionary and int(d.flags.coins) == 2, "a truncated save falls back to its .bak (coins %s)" % (d.flags.coins if d is Dictionary else "-"))
	t.ok(GameState.has_save(), "has_save() with only a good .bak")
	# a crash between the renames: no main file, the .bak and a .tmp
	DirAccess.remove_absolute(ProjectSettings.globalize_path(GameState.SAVE_PATH))
	d = GameState.read_save()
	t.ok(d is Dictionary, "a missing save file falls back to its .bak")
	# a .tmp that cannot be written (here a folder is in its place): the save and its .bak stay as they were
	GameState.flags["coins"] = 2
	GameState.write_save(xf)
	GameState.flags["coins"] = 5
	GameState.write_save(xf)
	var tmp_dir := ProjectSettings.globalize_path(GameState.SAVE_PATH + ".tmp")
	DirAccess.make_dir_absolute(tmp_dir)
	GameState.flags["coins"] = 9
	GameState.write_save(xf)
	DirAccess.remove_absolute(tmp_dir)
	d = GameState.read_save()
	var bak = Support.read_json(GameState.SAVE_PATH + ".bak")
	t.ok(d is Dictionary and int(d.flags.coins) == 5, "a save that cannot write its .tmp leaves the save in place (coins %s)" % (d.flags.coins if d is Dictionary else "-"))
	t.ok(bak is Dictionary and int(bak.flags.coins) == 2, "and does not move it over the .bak (coins %s)" % (bak.flags.coins if bak is Dictionary else "-"))
	GameState.write_save(xf)
	d = GameState.read_save()
	t.ok(d is Dictionary and int(d.flags.coins) == 9 and not FileAccess.file_exists(GameState.SAVE_PATH + ".tmp"), "the next save goes through and leaves no .tmp")
	GameState.clear_save()
	t.ok(not FileAccess.file_exists(GameState.SAVE_PATH + ".bak") and not GameState.has_save(), "clear_save removes the save and its .bak")
	# a version 1 save
	var v1 = Support.read_json("res://tests/fixtures/save_v1_sample.json")
	t.ok(v1 is Dictionary, "tests/fixtures/save_v1_sample.json loads")
	if v1 is Dictionary:
		var m := GameState.migrate(v1)
		t.ok(int(m.version) == 2 and int(m.get("migrated_from", 0)) == 1, "a v1 save migrates to version 2")
		t.ok(not m.flags.has("got") and m.flags.get("got_sofa", false) == true, "got.sofa becomes got_sofa")
		t.ok(int(m.flags.chapter) == 2, "a v1 save past Anisha is chapter 2")
		t.ok(String(m.flags.time) == "late_gold", "its light moves to chapter 2's first preset (%s)" % m.flags.time)
		var ch2_clock := Conditions.minutes(String(Chapters.get_chapter(2).get("clock", "")))
		t.ok(int(m.flags.clock) == maxi(ch2_clock, Conditions.minutes(String(WorldEnv.TIMES.late_gold.clock))),
			"its clock is chapter 2's (%s), not before its card (late_gold alone says %s)" % [Conditions.clock_text(int(m.flags.clock)), WorldEnv.TIMES.late_gold.clock])
		t.ok(m.flags.has("old_key_nobody_knows"), "keys nobody knows are kept")
		t.ok(m.flags.get("phone_dead", false) == true and m.flags.get("promise", false) == true,
			"past Toma: the phone died at 17:43 and the promise is open, as the v2 wake-up leaves them")
		t.ok(m.flags.get("phone_charging", false) == true, "past Karim: the phone is on the BDE strip (no 'Charge my phone' left open)")
		t.ok(m.flags.get("c1_done", false) == true, "past Anisha: chapter 1 is done")
		var fresh: Dictionary = v1.duplicate(true)
		fresh.flags.toma = false
		fresh.flags.karim = false
		fresh.flags.ines = false
		var mf := GameState.migrate(fresh)
		t.ok(not mf.flags.has("phone_dead") and not mf.flags.has("phone_charging") and not mf.flags.has("c1_done"),
			"a v1 save before Toma gets none of them")
		GameState.apply_save(v1)
		t.ok(GameState.flags.coins is int and GameState.flags.coins == 2, "v1's float coins become an int")
		t.ok(GameState.flags.foot_losses is int, "v1's float foot_losses become an int")
		t.ok(GameState.flags.choco == "pac" and GameState.flags.karim == true, "v1's story flags come through")
		t.ok(GameState.flags.has("todos_done") and GameState.flags.has("banners"), "flags v1 did not have get their defaults")
		t.ok(GameState.outfit == "classic" and is_equal_approx(GameState.play_time, 312.5), "outfit and play time come through")
		var early: Dictionary = v1.duplicate(true)
		early.flags.ines = false
		t.ok(int(GameState.migrate(early).flags.chapter) == 1, "a v1 save before Anisha is chapter 1")
		t.ok(String(GameState.migrate(early).flags.time) == "golden", "and keeps its golden light")
		t.ok(int(GameState.migrate(early).flags.clock) == Conditions.minutes(String(Chapters.get_chapter(1).get("clock", ""))), "and chapter 1's clock (%s)" % Conditions.clock_text(int(GameState.migrate(early).flags.clock)))
	# chapter snapshots
	GameState.reset_flags()
	GameState.flags["chapter"] = 2
	GameState.flags["ines"] = true
	GameState.write_chapter_save(2, xf)
	var s = GameState.read_chapter_save(2)
	t.ok(s is Dictionary and int(s.chapter) == 2 and s.flags.ines == true, "a chapter snapshot reads back")
	t.ok(2 in GameState.chapter_saves(), "chapter_saves() lists it")
	GameState.write_chapter_save(1, xf)
	GameState.write_chapter_save(2, xf)   # a second write leaves a .bak beside it
	GameState.clear_chapter_saves()
	t.ok(GameState.chapter_saves().is_empty(), "clear_chapter_saves() removes every snapshot")
	t.ok(not FileAccess.file_exists(GameState.chapter_save_path(2) + ".bak"), "and their .bak")
	# the player's own files, read only
	for name in REAL_FILES:
		if before[name] == "":
			t.info("no %s on this machine" % name)
		else:
			t.ok(_real_sha1(name) == before[name], "the real %s is unchanged by the tests" % name)
	GameState.reset_flags()
