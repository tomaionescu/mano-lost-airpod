extends Node
## Global state: input bindings, settings, story flags and save files.

signal settings_changed
signal flags_changed

## Where saves, settings, chapter snapshots, film and photo-mode pictures go (V2-33). A normal run uses user://
## and ~/Pictures. Autotests play the game too, so with `autotest` or `autotest=<plan>` on the command line (main.gd
## starts the basic plan for a bare `autotest`, and that plan's new_game() clears the save) every one of those paths
## gets ".autotest" (save_v1.autotest.json, user://film.autotest/...): a test run never overwrites the player's save
## or settings. Test scenes (anything run from res://tests/ or res://scenes/dev/, or after use_test_paths()) write
## ".test" files under res://tests/out/ instead, so they never touch the user folder at all.
const SAVE_VERSION := 2
const FLAGS_FILE := "res://data/flags.json"
const TEST_DIR := "res://tests/out/"
var suffix := ""                 # "", ".autotest" or ".test"
var base_dir := "user://"
var SAVE_PATH := ""
var SETTINGS_PATH := ""
var flag_defs: Dictionary = {}   # data/flags.json: name -> {default, doc}

const SETTINGS_VERSION := 2   # 2: the waypoint became opt-in

const DEFAULT_SETTINGS := {
	"mouse_sensitivity": 1.0,
	"invert_y": false,
	"pad_sensitivity": 1.0,
	"volume_master": 0.85,
	"volume_music": 0.6,
	"volume_sfx": 0.9,
	"volume_voice": 1.0,       # the NPCs' recorded lines (the Voice bus)
	"quality": "high", # low | medium | high | ultra
	"waypoint": false,         # the red-pen objective marker; off by default
	"subtitles_size": 1.0,     # S 0.84, M 1, L 1.2, XL 1.5 (Dialogue.subtitle_size)
	"film_grain": true,
	"fov": 52.0,
	"readable_fonts": false,   # Mano's handwriting roles drawn in the print face (UITheme.set_readable)
	"typewriter": false,       # subtitles appear whole with a short fade; true types them out
	"reduce_motion": false,    # no boil, overshoot or turn; write-ons and draw-ons appear at once (Ink.calm)
}

# Physical key codes, so WASD also covers ZQSD on AZERTY keyboards.
const BINDINGS := {
	"move_forward": [KEY_W, KEY_UP],
	"move_back": [KEY_S, KEY_DOWN],
	"move_left": [KEY_A, KEY_LEFT],
	"move_right": [KEY_D, KEY_RIGHT],
	"run": [KEY_SHIFT],
	"interact": [KEY_E, KEY_SPACE, KEY_ENTER],
	"confirm": [KEY_SPACE, KEY_ENTER, KEY_E],
	"back": [KEY_ESCAPE, KEY_BACKSPACE],
	"pause": [KEY_ESCAPE],
	"journal": [KEY_TAB, KEY_J],
	"map": [KEY_M],
	"wardrobe": [KEY_F],
	"photo_mode": [KEY_P],
	"photo_capture": [KEY_C],
	"phone": [KEY_Q],          # Mano's phone (V2-24); physical Q, the A key on AZERTY
	"ui_up_alt": [KEY_W, KEY_UP],
	"ui_down_alt": [KEY_S, KEY_DOWN],
}
const PAD_BUTTONS := {
	"interact": [JOY_BUTTON_A],
	"confirm": [JOY_BUTTON_A],
	"back": [JOY_BUTTON_B],
	"pause": [JOY_BUTTON_START],
	"journal": [JOY_BUTTON_BACK],
	"map": [JOY_BUTTON_Y],
	"wardrobe": [JOY_BUTTON_X],
	"run": [JOY_BUTTON_LEFT_STICK],
	"photo_mode": [JOY_BUTTON_DPAD_UP],
	"phone": [JOY_BUTTON_DPAD_DOWN],
	"ui_up_alt": [JOY_BUTTON_DPAD_UP],
	"ui_down_alt": [JOY_BUTTON_DPAD_DOWN],
}
const PAD_AXES := {
	"move_forward": [JOY_AXIS_LEFT_Y, -1.0],
	"move_back": [JOY_AXIS_LEFT_Y, 1.0],
	"move_left": [JOY_AXIS_LEFT_X, -1.0],
	"move_right": [JOY_AXIS_LEFT_X, 1.0],
	"look_up": [JOY_AXIS_RIGHT_Y, -1.0],
	"look_down": [JOY_AXIS_RIGHT_Y, 1.0],
	"look_left": [JOY_AXIS_RIGHT_X, -1.0],
	"look_right": [JOY_AXIS_RIGHT_X, 1.0],
}

var settings: Dictionary = DEFAULT_SETTINGS.duplicate(true)
var flags: Dictionary = {}
var play_time := 0.0
var outfit := "street"
var ducks_found: Array = []
var using_pad := false


func _init() -> void:
	match run_kind(OS.get_cmdline_args() + OS.get_cmdline_user_args()):
		"test":
			use_test_paths()
		"autotest":
			suffix = ".autotest"
			_set_paths()
		_:
			_set_paths()


## "test" when a test scene runs (res://tests/, res://scenes/dev/, res://tools/) or any script run with `-s` (a
## tool script would otherwise load and rewrite the player's settings), "autotest" for any argument that begins
## with "autotest" (`autotest` alone or `autotest=<plan>`: the test main.gd uses to start one), else "" (a normal
## run: the player's).
static func run_kind(args: Array) -> String:
	var kind := ""
	for a in args:
		var s := String(a)
		if s.begins_with("res://tests/") or s.begins_with("res://scenes/dev/") or s.begins_with("res://tools/") or s in ["-s", "--script"]:
			return "test"
		if s.begins_with("autotest"):
			kind = "autotest"
	return kind


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	_register_inputs()
	load_settings()
	reset_flags()


## Test scenes call this first (it is also automatic for res://tests/ and res://scenes/dev/ scenes): every save,
## setting, snapshot and picture goes to res://tests/out/*.test.*, never the user folder.
func use_test_paths() -> void:
	suffix = ".test"
	base_dir = TEST_DIR
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(TEST_DIR))
	_set_paths()


func _set_paths() -> void:
	SAVE_PATH = user_file("save_v1")
	SETTINGS_PATH = user_file("settings_v1")


## True in autotests and test scenes: nothing they write can reach the player's own files.
func sandboxed() -> bool:
	return suffix != ""


## "save_v1" -> user://save_v1.json, user://save_v1.autotest.json or res://tests/out/save_v1.test.json
func user_file(stem: String) -> String:
	return "%s%s%s.json" % [base_dir, stem, suffix]


## Ishita's film and the copies of photo-mode shots for the credits: user://film/ in a normal run.
func film_dir() -> String:
	return "%sfilm%s/" % [base_dir, suffix]


## Where photo mode saves: ~/Pictures/Mano & the lost AirPod in a normal run, user://photos.autotest/ in an
## autotest, res://tests/out/photos.test/ in a test (never the Pictures folder).
func photos_dir() -> String:
	if not sandboxed():
		return OS.get_system_dir(OS.SYSTEM_DIR_PICTURES).path_join("Mano & the lost AirPod")
	return ProjectSettings.globalize_path("%sphotos%s/" % [base_dir, suffix])


func _input(event: InputEvent) -> void:
	if event is InputEventJoypadButton or (event is InputEventJoypadMotion and absf(event.axis_value) > 0.4):
		using_pad = true
	elif event is InputEventKey or event is InputEventMouseButton:
		using_pad = false


func _register_inputs() -> void:
	for action in BINDINGS:
		if not InputMap.has_action(action):
			InputMap.add_action(action, 0.25)
		for code in BINDINGS[action]:
			var ev := InputEventKey.new()
			ev.physical_keycode = code
			InputMap.action_add_event(action, ev)
	for action in PAD_BUTTONS:
		if not InputMap.has_action(action):
			InputMap.add_action(action, 0.25)
		for b in PAD_BUTTONS[action]:
			var ev := InputEventJoypadButton.new()
			ev.button_index = b
			InputMap.action_add_event(action, ev)
	for action in PAD_AXES:
		if not InputMap.has_action(action):
			InputMap.add_action(action, 0.2)
		var ev := InputEventJoypadMotion.new()
		ev.axis = PAD_AXES[action][0]
		ev.axis_value = PAD_AXES[action][1]
		InputMap.action_add_event(action, ev)


# ------------------------------------------------------------------ story flags
## Every flag from data/flags.json at its default (V2-19: the flags are declared there, with what they mean).
func reset_flags() -> void:
	_load_flag_defs()
	flags = {}
	for k in flag_defs:
		flags[k] = _copy(flag_defs[k].get("default", false))
	play_time = 0.0
	outfit = "street"
	ducks_found = []


func flag(key: String, default_value = false):
	return flags.get(key, default_value)


func set_flag(key: String, value) -> void:
	flags[key] = value
	flags_changed.emit()


## A flag's declared default (data/flags.json), or false for a flag nobody declared.
func flag_default(key: String):
	_load_flag_defs()
	return _copy(flag_defs[key].get("default", false)) if flag_defs.has(key) else false


func is_declared(key: String) -> bool:
	_load_flag_defs()
	return flag_defs.has(key)


func _load_flag_defs() -> void:
	if not flag_defs.is_empty():
		return
	var d = _read_json(FLAGS_FILE)
	if d is Dictionary and d.get("flags") is Dictionary:
		flag_defs = d.flags
		# JSON reads every number as a float: whole-number defaults (coins, chapter, clock) are ints
		for k in flag_defs:
			var v = flag_defs[k].get("default", false)
			if v is float and v == floorf(v):
				flag_defs[k]["default"] = int(v)
	else:
		push_error("GameState: %s is missing or broken; falling back to v1's flags" % FLAGS_FILE)
		for k in ["toma", "ines", "karim", "sign", "madame_met", "coffee", "paid", "coffee_given", "found", "merch",
				"got_planter", "got_sofa"]:
			flag_defs[k] = {"default": false}
		for k in ["coins", "foot_losses"]:
			flag_defs[k] = {"default": 0}
		for k in ["clues", "hints", "todos_done", "banners", "triggers_fired"]:
			flag_defs[k] = {"default": []}
		flag_defs["choco"] = {"default": ""}
		flag_defs["time"] = {"default": "golden"}
		flag_defs["chapter"] = {"default": 1}
		flag_defs["clock"] = {"default": 1062}


static func _copy(v):
	return v.duplicate(true) if v is Array or v is Dictionary else v


# ------------------------------------------------------------------ settings
func load_settings() -> void:
	var data = _read_json(SETTINGS_PATH)
	if data is Dictionary:
		# version 1 wrote every default to disk, so its "waypoint": true was nobody's choice
		if int(data.get("version", 1)) < 2:
			data.erase("waypoint")
		for k in data:
			if DEFAULT_SETTINGS.has(k):
				settings[k] = data[k]
	settings_changed.emit()


func set_setting(key: String, value) -> void:
	settings[key] = value
	_save_settings()
	settings_changed.emit()


func reset_settings() -> void:
	settings = DEFAULT_SETTINGS.duplicate(true)
	_save_settings()
	settings_changed.emit()


func _save_settings() -> void:
	var data := settings.duplicate()
	data["version"] = SETTINGS_VERSION
	_write_json(SETTINGS_PATH, data)


# ------------------------------------------------------------------ saves
## The save (V2-33): user://save_v1.json with "version": 2 inside, written atomically (a
## .tmp file, then the old save becomes .bak and the .tmp takes its place), read back from the .bak when the main
## file is missing or broken; version 1 saves are migrated on load. Chapter snapshots: user://save_ch<n>.json.
func has_save() -> bool:
	return read_save() != null


## The save as a Dictionary (migrated to version 2), or null.
func read_save():
	return _read_save_file(SAVE_PATH)


func write_save(player_xform: Transform3D) -> void:
	_write_atomic(SAVE_PATH, save_data(player_xform))


## The saved state: version, chapter, flags (with clock and time), outfit, ducks, play_time, pos, yaw, saved_at.
func save_data(player_xform: Transform3D) -> Dictionary:
	var o := player_xform.origin
	return {
		"version": SAVE_VERSION,
		"chapter": int(flags.get("chapter", 1)),
		"flags": flags.duplicate(true),
		"outfit": outfit,
		"ducks": ducks_found.duplicate(),
		"play_time": play_time,
		"pos": [o.x, o.y, o.z],
		"yaw": player_xform.basis.get_euler().y,
		"saved_at": Time.get_datetime_string_from_system(),
	}


func apply_save(data: Dictionary) -> void:
	data = migrate(data)
	reset_flags()
	var f: Dictionary = data.get("flags", {})
	for k in f:
		flags[k] = f[k]
	coerce_flags()
	outfit = data.get("outfit", "street")
	ducks_found = data.get("ducks", [])
	play_time = float(data.get("play_time", 0.0))
	flags_changed.emit()


## A version 1 save brought up to version 2: got.{sofa, planter} become got_sofa / got_planter, the chapter is 2
## once Anisha's moulinette passed (else 1), the time goes to the chapter's first preset if the saved one is not
## among its presets, and the clock comes from that preset, never earlier than the chapter's own clock (late_gold's
## 18:15 is before chapter 2's card says 18:30). Keys nobody knows are kept.
func migrate(data: Dictionary) -> Dictionary:
	data = data.duplicate(true)
	if int(data.get("version", 1)) >= SAVE_VERSION:
		return data
	var f: Dictionary = data.get("flags", {})
	var got = f.get("got", {})
	if got is Dictionary:
		for id in got:
			if bool(got[id]):
				f["got_" + String(id)] = true
	f.erase("got")
	# what v2 sets in the same beat as a v1 flag: the wake-up (toma) kills the phone at 17:43 and leaves the promise
	# open; Karim's admission (karim) puts the phone on the BDE strip; the moulinette (ines) ends chapter 1. Without
	# them a v1 night went on into chapter 2 with Mano saying "It died at 17:43" of a phone that never died.
	for pair in [["toma", ["phone_dead", "promise"]], ["karim", ["phone_charging"]], ["ines", ["c1_done"]]]:
		if bool(f.get(pair[0], false)):
			for k in pair[1]:
				if not f.has(k):
					f[k] = true
	var ch := 2 if bool(f.get("ines", false)) else 1
	f["chapter"] = ch
	var info: Dictionary = Chapters.get_chapter(ch)
	var times: Array = info.get("times", [])
	if not times.is_empty() and not String(f.get("time", "")) in times:
		f["time"] = String(info.get("time", times[0]))
	var preset: Dictionary = WorldEnv.TIMES.get(String(f.get("time", WorldEnv.DEFAULT_TIME)), {})
	if not f.has("clock"):
		var m := maxi(Conditions.minutes(String(preset.get("clock", ""))), Conditions.minutes(String(info.get("clock", ""))))
		f["clock"] = m if m >= 0 else 1062
	data["flags"] = f
	data["chapter"] = ch
	data["version"] = SAVE_VERSION
	data["migrated_from"] = 1
	return data


## JSON brings every number back as a float: the flags declared as whole numbers become ints again.
func coerce_flags() -> void:
	_load_flag_defs()
	for k in flags:
		var d = flag_defs.get(k, {}).get("default", null)
		var v = flags[k]
		if d is int and v is float:
			flags[k] = int(v)
		elif d is bool and (v is float or v is int):
			flags[k] = v != 0


func clear_save() -> void:
	for p in [SAVE_PATH, SAVE_PATH + ".bak", SAVE_PATH + ".tmp"]:
		if FileAccess.file_exists(p):
			DirAccess.remove_absolute(ProjectSettings.globalize_path(p))


# ------------------------------------------------------------------ chapter snapshots
func chapter_save_path(n: int) -> String:
	return user_file("save_ch%d" % n)


## Written right after a chapter's card (main.begin_chapter): what chapter select and a replay start from.
func write_chapter_save(n: int, player_xform: Transform3D) -> void:
	var d := save_data(player_xform)
	d["chapter"] = n
	_write_atomic(chapter_save_path(n), d)


func read_chapter_save(n: int):
	return _read_save_file(chapter_save_path(n))


## Every chapter snapshot gone ("Start again" over a night in progress: main.new_game(true)).
func clear_chapter_saves() -> void:
	for n in range(0, 10):
		var path := chapter_save_path(n)
		for p in [path, path + ".bak", path + ".tmp"]:
			if FileAccess.file_exists(p):
				DirAccess.remove_absolute(ProjectSettings.globalize_path(p))


## The chapters that have a snapshot, in order.
func chapter_saves() -> Array:
	var out: Array = []
	for n in range(0, 10):
		if read_chapter_save(n) != null:
			out.append(n)
	return out


# ------------------------------------------------------------------ files
func _read_save_file(path: String):
	for p in [path, path + ".bak"]:
		var d = _read_json(p)
		if d is Dictionary and d.has("flags"):
			return migrate(d)
		if FileAccess.file_exists(p):
			push_warning("GameState: %s is not a readable save, trying the backup" % p)
	return null


## .tmp first, checked for its full length, then the current file becomes .bak and the .tmp takes its place: a crash
## or a failed write at any point leaves either the old save, or the .bak, readable.
func _write_atomic(path: String, data) -> bool:
	var tmp := path + ".tmp"
	var f := FileAccess.open(tmp, FileAccess.WRITE)
	if f == null:
		push_warning("GameState: cannot write %s (%s)" % [tmp, error_string(FileAccess.get_open_error())])
		return false
	var text := JSON.stringify(data, "\t")
	var stored := f.store_string(text)
	f.close()
	# a full disk leaves a short or empty .tmp: the save in place stays where it is
	if not stored or FileAccess.get_file_as_bytes(tmp).size() != text.to_utf8_buffer().size():
		push_warning("GameState: %s was not written in full, %s is kept" % [tmp, path])
		return false
	var abs_path := ProjectSettings.globalize_path(path)
	if FileAccess.file_exists(path):
		var bak := abs_path + ".bak"
		if FileAccess.file_exists(path + ".bak"):
			DirAccess.remove_absolute(bak)
		DirAccess.rename_absolute(abs_path, bak)
	return DirAccess.rename_absolute(ProjectSettings.globalize_path(tmp), abs_path) == OK


func _read_json(path: String):
	if not FileAccess.file_exists(path):
		return null
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		return null
	var j := JSON.new()
	if j.parse(f.get_as_text()) != OK:
		return null
	return j.data


func _write_json(path: String, data) -> void:
	var f := FileAccess.open(path, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify(data, "\t"))
