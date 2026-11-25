extends Node
## Audio director: buses, music with crossfades, ambience per zone, footsteps, one-shots.
## Sound files live in res://assets/audio/<group>/<name>[_N].ogg; missing files are skipped silently,
## so the game runs before every sound exists.
## Every track resumes where it was left (docs/DESIGN.md §9: exploration resumes from its position after a puzzle; a
## second sit-down resumes its song, §4.1): a track faded out keeps its playback position. song() is a sit-down's
## or a preview's track, rising from silence; duck_ambience() lowers the room under it (V2-14).

signal music_started(stem: String)

const BUSES := ["Music", "SFX", "Ambience", "UI", "Voice"]

# zone -> ambience loops (file stems under assets/audio/amb) and indoor reverb amount
const ZONES := {
	"street": {"amb": ["city_traffic", "wind_light"], "reverb": 0.0},
	"court": {"amb": ["courtyard_crowd", "birds_evening", "wind_light"], "reverb": 0.0},
	"amphi": {"amb": ["room_tone_large", "hvac"], "reverb": 0.55},
	"volt_gf": {"amb": ["room_tone", "lobby_murmur"], "reverb": 0.35},
	"volt_f1": {"amb": ["room_tone", "hvac"], "reverb": 0.3},
	"sm14": {"amb": ["computer_room", "keyboards"], "reverb": 0.25},
	"sm15": {"amb": ["computer_room", "keyboards"], "reverb": 0.25},
	"cafe": {"amb": ["cafeteria", "fridge_hum"], "reverb": 0.4},
	"under": {"amb": ["basement_tone"], "reverb": 0.5},
	"passage": {"amb": ["city_traffic", "wind_light"], "reverb": 0.2},
}

var _music: Array[AudioStreamPlayer] = []
var _music_idx := 0
var _music_name := ""
var _amb_players := {} # stem -> AudioStreamPlayer
var _zone := ""
var _reverb: AudioEffectReverb
var _cache := {}
var _duck := 1.0
var _duck_target := 1.0
var _vduck := 1.0          # a further dip while a recorded line plays (duck_voice)
var _vduck_target := 1.0
var _positions := {}       # stem -> seconds into it when it was last faded out (a track resumes from there)
var _amb_db := 0.0         # duck_ambience: the ambience's offset now, moving to _amb_db_target at _amb_rate dB/s
var _amb_db_target := 0.0
var _amb_rate := 6.0


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	for b in BUSES:
		if AudioServer.get_bus_index(b) == -1:
			AudioServer.add_bus()
			var i := AudioServer.bus_count - 1
			AudioServer.set_bus_name(i, b)
			AudioServer.set_bus_send(i, "Master")
	_reverb = AudioEffectReverb.new()
	_reverb.room_size = 0.55
	_reverb.damping = 0.6
	_reverb.wet = 0.0
	_reverb.dry = 1.0
	AudioServer.add_bus_effect(AudioServer.get_bus_index("SFX"), _reverb)
	var comp := AudioEffectCompressor.new()
	comp.threshold = -10.0
	comp.ratio = 3.0
	AudioServer.add_bus_effect(AudioServer.get_bus_index("Master"), comp)
	for i in 2:
		var p := AudioStreamPlayer.new()
		p.bus = "Music"
		p.volume_db = -80.0
		add_child(p)
		_music.append(p)
	GameState.settings_changed.connect(apply_volumes)
	apply_volumes()


func apply_volumes() -> void:
	var s := GameState.settings
	AudioServer.set_bus_volume_db(0, linear_to_db(maxf(s.volume_master, 0.0001)))
	AudioServer.set_bus_volume_db(AudioServer.get_bus_index("Music"), linear_to_db(maxf(s.volume_music * 0.8, 0.0001)))
	AudioServer.set_bus_volume_db(AudioServer.get_bus_index("SFX"), linear_to_db(maxf(s.volume_sfx, 0.0001)))
	AudioServer.set_bus_volume_db(AudioServer.get_bus_index("Ambience"), linear_to_db(maxf(s.volume_sfx * 0.7, 0.0001)))
	AudioServer.set_bus_volume_db(AudioServer.get_bus_index("UI"), linear_to_db(maxf(s.volume_sfx * 0.8, 0.0001)))
	AudioServer.set_bus_volume_db(AudioServer.get_bus_index("Voice"), linear_to_db(maxf(s.volume_voice, 0.0001)))


func _process(dt: float) -> void:
	_duck = move_toward(_duck, _duck_target, dt * 1.5)
	_vduck = move_toward(_vduck, _vduck_target, dt * (4.0 if _vduck_target < _vduck else 1.2))
	var cur := _music[_music_idx]
	if cur.playing and cur.has_meta("target_db"):
		var rate := 5.0 / maxf(float(cur.get_meta("fade", 2.5)), 0.1)
		cur.volume_db = lerpf(cur.volume_db, float(cur.get_meta("target_db")) + linear_to_db(_duck * _vduck), 1.0 - exp(-dt * rate))
	var other := _music[1 - _music_idx]
	if other.playing:
		other.volume_db = move_toward(other.volume_db, -60.0, dt * float(other.get_meta("out_rate", 30.0)))
		if other.volume_db <= -59.0:
			_remember(other)
			other.stop()
	_amb_db = move_toward(_amb_db, _amb_db_target, dt * _amb_rate)
	for stem in _amb_players:
		var p: AudioStreamPlayer = _amb_players[stem]
		var target: float = p.get_meta("target_db", -60.0)
		if target > -59.0:
			target += _amb_db
		p.volume_db = move_toward(p.volume_db, target, dt * 18.0)
		if target <= -59.0 and p.volume_db <= -59.0 and p.playing:
			p.stop()


# ------------------------------------------------------------------ loading helpers
func _load(group: String, stem: String) -> AudioStream:
	var key := group + "/" + stem
	if _cache.has(key):
		return _cache[key]
	var found: Array = []
	for ext in ["ogg", "wav", "mp3"]:
		var single := "res://assets/audio/%s/%s.%s" % [group, stem, ext]
		if ResourceLoader.exists(single):
			found.append(load(single))
		for i in range(1, 13):
			var p := "res://assets/audio/%s/%s_%d.%s" % [group, stem, i, ext]
			if ResourceLoader.exists(p):
				found.append(load(p))
	var stream: AudioStream = null
	if found.size() == 1:
		stream = found[0]
	elif found.size() > 1:
		var r := AudioStreamRandomizer.new()
		for s in found:
			r.add_stream(-1, s)
		r.random_pitch = 1.06
		r.random_volume_offset_db = 2.0
		stream = r
	_cache[key] = stream
	return stream


# ------------------------------------------------------------------ one-shots
func play(stem: String, volume_db := 0.0, bus := "SFX", pitch := 1.0) -> void:
	var s := _load("sfx", stem)
	if s == null:
		return
	var p := AudioStreamPlayer.new()
	p.stream = s
	p.bus = bus
	p.volume_db = volume_db
	p.pitch_scale = pitch
	add_child(p)
	p.play()
	p.finished.connect(p.queue_free)


func ui(stem: String, volume_db := -4.0) -> void:
	play(stem, volume_db, "UI")


func play_at(stem: String, pos: Vector3, volume_db := 0.0, max_distance := 25.0) -> void:
	var s := _load("sfx", stem)
	if s == null or get_tree().current_scene == null:
		return
	var p := AudioStreamPlayer3D.new()
	p.stream = s
	p.bus = "SFX"
	p.volume_db = volume_db
	p.max_distance = max_distance
	p.unit_size = 3.0
	get_tree().current_scene.add_child(p)
	p.global_position = pos
	p.play()
	p.finished.connect(p.queue_free)


func footstep(surface: String, pos: Vector3, running: bool) -> void:
	var s := _load("footsteps", surface)
	if s == null:
		s = _load("footsteps", "concrete")
	if s == null or get_tree().current_scene == null:
		return
	var p := AudioStreamPlayer3D.new()
	p.stream = s
	p.bus = "SFX"
	p.volume_db = -6.0 if running else -11.0
	p.pitch_scale = randf_range(0.94, 1.06)
	p.unit_size = 4.0
	get_tree().current_scene.add_child(p)
	p.global_position = pos
	p.play()
	p.finished.connect(p.queue_free)


# ------------------------------------------------------------------ music
## Crossfades to a track (or to silence with ""), from where that track was last left. `fade` is how long the new
## one takes to rise; `out` how long the old one takes to go (2 s, or a sit-down's 3 s).
func music(stem: String, volume_db := -6.0, fade := 2.5, out := 2.0) -> void:
	if stem == _music_name:
		return
	_music_name = stem
	var s := _load("music", stem) if stem != "" else null
	var old := _music[_music_idx]
	old.set_meta("out_rate", 60.0 / maxf(out, 0.1))
	_music_idx = 1 - _music_idx
	var p := _music[_music_idx]
	if p.playing:
		_remember(p)
		p.stop()
	if s == null:
		return
	p.stream = s
	p.volume_db = -40.0
	p.set_meta("target_db", volume_db)
	p.set_meta("fade", fade)
	p.set_meta("stem", stem)
	p.set_meta("out_rate", 30.0)
	var at: float = _positions.get(stem, 0.0)
	p.play(at if at < s.get_length() - 1.0 else 0.0)
	music_started.emit(stem)


## The track playing now moves to `volume_db` over `fade` seconds (music() does nothing for the same track).
func music_level(volume_db: float, fade := 2.5) -> void:
	var p := _music[_music_idx]
	if _music_name != "" and p.has_meta("target_db"):
		p.set_meta("target_db", volume_db)
		p.set_meta("fade", fade)


## The track playing now ("" for none).
func music_now() -> String:
	return _music_name


## Seconds into the track (playing now or still fading out; its saved position when it is not).
func position_of(stem: String) -> float:
	for p: AudioStreamPlayer in [_music[_music_idx], _music[1 - _music_idx]]:
		if p.playing and p.has_meta("stem") and String(p.get_meta("stem")) == stem:
			return p.get_playback_position()
	return float(_positions.get(stem, 0.0))


func _remember(p: AudioStreamPlayer) -> void:
	if p.has_meta("stem") and p.playing:
		_positions[String(p.get_meta("stem"))] = p.get_playback_position()


## A sit-down's or a preview's song (V2-14, docs/DESIGN.md §4.1): from silence up to `volume_db` over `fade` seconds,
## from where it was last left; the track before it goes over `out` seconds.
func song(stem: String, volume_db := -8.0, fade := 3.5, out := 2.0) -> void:
	music(stem, volume_db, fade, out)


## The ambience `db` lower (0: back to normal), over `seconds`.
func duck_ambience(db: float, seconds := 3.0) -> void:
	_amb_db_target = db
	_amb_rate = maxf(absf(_amb_db_target - _amb_db) / maxf(seconds, 0.05), 0.5)


func duck_music(on: bool) -> void:
	_duck_target = 0.45 if on else 1.0


## Music dips a further 6 dB under a recorded voice line (Dialogue), on top of duck_music.
func duck_voice(on: bool) -> void:
	_vduck_target = 0.5 if on else 1.0


# ------------------------------------------------------------------ ambience
func set_zone(zone: String) -> void:
	if zone == _zone:
		return
	_zone = zone
	var cfg: Dictionary = ZONES.get(zone, {"amb": [], "reverb": 0.0})
	var wanted: Array = cfg.amb
	for stem in _amb_players:
		_amb_players[stem].set_meta("target_db", -60.0)
	for stem in wanted:
		var p: AudioStreamPlayer = _amb_players.get(stem)
		if p == null:
			var s := _load("amb", stem)
			if s == null:
				continue
			p = AudioStreamPlayer.new()
			p.stream = s
			p.bus = "Ambience"
			p.volume_db = -60.0
			add_child(p)
			_amb_players[stem] = p
		if not p.playing:
			p.play(randf() * maxf(p.stream.get_length() - 1.0, 0.0))
		p.set_meta("target_db", -8.0)
	var tw := create_tween()
	tw.tween_property(_reverb, "wet", float(cfg.reverb) * 0.35, 1.2)
