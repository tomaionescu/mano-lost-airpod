extends Node3D
## Game root: loads the campus and the cast, runs the modes (title, play, dialogue, menus,
## minigames, photo, ending), the conversation camera, zones, waypoint and autosave, and the chapters
## (V2-20): begin_chapter() plays a chapter's card and sets its light, clock and staging from data/chapters.json.
## Also here: Mano's phone in his hand (mode "phone", V2-24: open_phone, phone_cmd) and the sit-downs (mode "sit",
## V2-14: begin_sit / end_sit, data/world.json "sits").
## V2-26, V2-27: the cold open (chapter 0: _cold_open, then "Six hours earlier." and chapter 1's dream and
## wake-up), the finale's photos (take_photo), the AirPods in their case (set_airpods), the score (set_score), the
## credits (mode "credits": roll_credits, then the post-credits) and the recap (show_recap).

const LEVEL := "res://assets/levels/campus.glb"
const JOURNAL_HOLD := 0.3   # held longer than this, the journal key peeks at the objective instead
const TITLE_DRIFT := 75.0   # seconds for the title camera's 40° drift one way
const TITLE_LEAN := 22.0    # degrees Mano slumps forward, asleep on the title
const TITLE_SETTLE := 1.2   # seconds of black behind the first title before the amphi fades up
# the opening's dream and wake-up (docs/DESIGN.md §7; the clip's frames and record: autotest=dream, assets/video/CREDITS.md)
const DREAM := "res://assets/video/dream.ogv"
const DREAM_IN := 0.4       # seconds the clip takes to come up out of the black as the chapter card turns away (short, so the earbud's tip-over is seen)
const DREAM_OUT := 0.3      # seconds its last frames dissolve into the same shot rendered live
const NOTEBOOK_AT := Vector3(20.08, -0.12, 13.86)   # Mano's algo notebook, on the desk across the aisle from him
const NOTEBOOK_YAW := -0.12
const WAKE_DESK_FROM := Vector3(19.55, 0.22, 14.70)   # the wake-up's first shot: the notebook, him out of frame
const WAKE_DESK_LOOK := Vector3(20.08, -0.11, 13.86)
const WAKE_DESK_FOV := 28.0
const WAKE_DESK_BLUR := 0.55   # how soft that shot is (set_wake_blur); the clip ends on it as soft
const WAKE_HOLD := 1.1      # seconds on the desk (drifting WAKE_DRIFT metres closer) before the cut to his face
const WAKE_DRIFT := 0.08
const OUTFITS := {
	"street": {"name": "Streetwear", "desc": "Black zip hoodie, olive cargos, white sneakers.", "model": "mano_street"},
	"classic": {"name": "Mano classic", "desc": "Red polo and dark jeans, from the real photos.", "model": "mano_classic"},
	"merch": {"name": "EPITA merch", "desc": "Navy EPITA hoodie and grey joggers.", "model": "mano_merch", "locked": "Find all 8 golden rubber ducks hidden on campus."},
}

var world_env: WorldEnv
var level_root: Node3D
var binder := LevelBinder.new()
var player: Player
var camera_rig: CameraRig
var hud: HUD
var dialogue: Dialogue
var story: Story
var menus: Menus
var npcs := {}
var crowd: Array = []
var interactables: Array = []
var ducks: Ducks
var mode := "loading"
var minigame: Node = null

var _zone := {}
var _save_clock := 30.0
var _conv := {}
var _speaker_rig: CharacterRig = null
var _loading: Array = []
var _load_total := 0
var _graph := {}
var _post: CanvasLayer
var _title_from := Vector3.ZERO   # Mano's head on the title, which the camera drifts round
var _title_t := 0.0
var _title_seated := false        # Mano asleep in the amphi for the title (_title_pose)
var _title_return := [Vector3.ZERO, 0.0]   # where he stood before it, and his yaw
var _title_fade: Tween                     # the first title's fade-up, stopped if a game starts during it
var _journal_hold := -1.0
var _notebook: AlgoNotebook = null         # on the desk beside Mano from the wake-up on (_wake_pose)
var dream_player: VideoStreamPlayer = null  # the opening's dream clip while it plays (autotests watch it)
## Where the opening or a chapter card is ("card", "dream", "wake", "talk", "chapter_card", ""), for autotests.
var opening_phase := ""
var _chapter_t := 0.0     # seconds of play since the chapter began (trigger `after`)
var _trigger_t := 0.0     # the trigger poll runs every 0.25 s
var _clock_acc := 0.0     # game minutes owed to the story clock
var _world_spots := {}    # data/world.json spots: id -> {pos, label, range, kind, when}
var phone: Phone          # Mano's phone on the HUD (V2-24's lock screen: previews, dies at 17:43)
var _bark_cue := ""       # the look-at whose thought is showing (pressing E again does not repeat it)
var _bark_until := 0.0
var _sit := {}            # the sit-down in progress (mode "sit"): {id, s: WorldData.sit(), t, phase, from, ...}
var overheard: Overheard  # two people talking near Mano, bottom left (V2-31)
var _idle_t := 0.0        # seconds Mano has stood still in play (idle life after IDLE_AFTER)
var _idle_next := 0.0
var idle_beats: Array = []   # what the idle life did, for the autotests: [{kind, thought, at}]
var _photo_poll := 0.0
## When the last sit-down ended and how long after its input (autotest=sit reads it: within 0.5 s, docs/DESIGN.md §4.1).
var sit_stood := {}


func _ready() -> void:
	UITheme.init()
	world_env = WorldEnv.new()
	add_child(world_env)
	world_env.time_changed.connect(func(_n: String): _show_lights())   # the story's lights follow the preset
	var post := preload("res://scripts/fx/post_layer.gd").new()
	post.world_env = world_env   # the lens finish follows the time of day and the letterbox
	_post = post
	add_child(_post)
	hud = HUD.new()
	add_child(hud)
	post.hud = hud
	dialogue = Dialogue.new()
	add_child(dialogue)
	dialogue.build_ui(hud.root)
	dialogue.speaker_info = _speaker_info
	dialogue.line_shown.connect(_on_line)
	dialogue.finished.connect(_on_dialogue_finished)
	menus = Menus.new()
	menus.game = self
	add_child(menus)
	phone = Phone.new()
	phone.hud = hud
	add_child(phone)
	Sfx.music_started.connect(func(stem: String): Chat.heard(stem))   # the phone's Music list
	story = Story.new(self)
	GameState.flags_changed.connect(on_flags_changed)
	camera_rig = CameraRig.new()
	camera_rig.world_env = world_env
	add_child(camera_rig)
	hud.camera = camera_rig.cam
	menus.show_loading()
	_begin_loading()
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("autotest"):
			var t = load("res://scripts/dev/autotest.gd").new()
			t.game = self
			t.plan = arg.get_slice("=", 1) if "=" in arg else "basic"
			add_child(t)


# ------------------------------------------------------------------ loading
func _use_level() -> bool:
	return ResourceLoader.exists(LEVEL) and not "sandbox" in OS.get_cmdline_user_args()


func _begin_loading() -> void:
	var paths: Array = []
	if _use_level():
		paths.append(LEVEL)
	paths.append("res://assets/characters/mano_street.glb")
	for d in CastDefs.npc_defs():
		paths.append("res://assets/characters/%s.glb" % d.model)
	for m in CastDefs.crowd_models():
		paths.append("res://assets/characters/%s.glb" % m)
	var seen := {}
	for p in paths:
		if seen.has(p) or not ResourceLoader.exists(p):
			continue
		seen[p] = true
		ResourceLoader.load_threaded_request(p, "", true)
		_loading.append(p)
	_load_total = _loading.size()


func _poll_loading() -> void:
	var done := 0.0
	var all := true
	for p in _loading:
		var prog := []
		var st := ResourceLoader.load_threaded_get_status(p, prog)
		if st == ResourceLoader.THREAD_LOAD_LOADED:
			done += 1.0
		else:
			all = false
			done += prog[0] if prog.size() > 0 else 0.0
	menus.set_loading_progress(done / maxf(_load_total, 1))
	if all:
		for p in _loading:
			ResourceLoader.load_threaded_get(p)
		_loading.clear()
		_build_world()


func _build_world() -> void:
	if _use_level():
		level_root = (load(LEVEL) as PackedScene).instantiate()
	else:
		level_root = SandboxLevel.build()
	add_child(level_root)
	binder.bind(level_root)
	world_env.bind_level(binder)
	_build_graph()
	player = Player.new()
	player.name = "Mano"
	add_child(player)
	player.camera_rig = camera_rig
	player.set_model("res://assets/characters/%s.glb" % OUTFITS[GameState.outfit].model)
	player.teleport(binder.spawn.origin, _yaw_from(binder.spawn))
	camera_rig.target = player
	camera_rig.snap_behind(player.facing_yaw())
	_spawn_npcs()
	_spawn_spots()
	_spawn_notes()
	_spawn_lights()
	_spawn_cam_occluders()
	ducks = Ducks.new()
	add_child(ducks)
	ducks.setup(self, binder.ducks)
	overheard = Overheard.new()
	add_child(overheard)
	overheard.setup(self)
	player.register_interactables(interactables)
	show_title()


static func _yaw_from(xf: Transform3D) -> float:
	var f := xf.basis.z
	return atan2(f.x, f.z)


var _homes := {}   # id -> {pos, yaw}: where each character stands when no chapter stages them


func _spawn_npcs() -> void:
	for d in CastDefs.npc_defs():
		var def: Dictionary = d.duplicate()
		var m: Dictionary = binder.npcs.get(d.id, {})
		if not m.is_empty():
			def.pos = m.pos
			def.yaw = m.yaw
			for k in ["sit", "sleep"]:
				if m.extras.has(k):
					def[k] = bool(m.extras[k])
			if m.extras.has("talk") and bool(m.extras.talk):
				def["chatting"] = true
		# who is on campus when: the chapter's staging, then world.json npc_when (Mme Dupont's two spots); a
		# staged_only character (the new friends) only where a chapter puts them (Chapters.on_stage)
		var nid := String(def.id)
		var staged := bool(def.get("staged_only", false))
		def["when"] = func(): return Chapters.on_stage(nid, staged)
		if not ResourceLoader.exists("res://assets/characters/%s.glb" % def.model):
			continue
		var n := NPC.new()
		n.name = "NPC_" + def.id
		add_child(n)
		n.setup(def, player)
		_homes[def.id] = {"pos": def.pos, "yaw": def.yaw}
		if def.get("sit", false):
			# the seat centre sits ~0.2 m behind the marker (front edge of the seat)
			var seat: Vector3 = def.pos - Vector3(sin(def.yaw), 0, cos(def.yaw)) * 0.2
			n.swivel_chair = binder.nearest_prop("office_chair", seat, 0.6)
		npcs[def.id] = n
		var it := Interactable.new()
		it.id = def.id
		it.kind = "npc"
		it.npc = n
		it.label = "Talk to %s" % def.name
		it.range = def.get("range", 1.9)
		n.interact = it
		interactables.append(it)
	# background students: walkers on PATH_crowd* markers, sitters/standers on NPC_crowd* markers
	var models := CastDefs.crowd_models()
	var i := 0
	for key in binder.paths:
		if not String(key).begins_with("crowd") and not String(key).begins_with("walker"):
			continue
		var pts: Array = binder.paths[key]
		if pts.size() < 2:
			continue
		var pex: Dictionary = binder.path_extras.get(key, {})
		var def := {"id": "crowd_%s" % key, "model": String(pex.get("model", models[i % models.size()])).replace("npc_", ""),
			"pos": pts[0], "yaw": 0.0, "path": pts, "loop": bool(pex.get("loop", pts[0].distance_to(pts[-1]) < 3.0)), "crowd": true}
		if pex.has("speed"):
			def["speed"] = float(pex.speed)
		_spawn_crowd(def)
		i += 1
	for id in binder.npcs:
		if String(id).begins_with("crowd"):
			var m: Dictionary = binder.npcs[id]
			_spawn_crowd({"id": id, "model": String(m.extras.get("model", models[i % models.size()])).replace("npc_", ""), "pos": m.pos, "yaw": m.yaw,
				"sit": bool(m.extras.get("sit", false)), "crowd": true, "chatting": bool(m.extras.get("talk", false))})
			i += 1
	_refresh_presence()


func _spawn_crowd(def: Dictionary) -> void:
	if not ResourceLoader.exists("res://assets/characters/%s.glb" % def.model):
		def.model = CastDefs.crowd_models()[randi() % 8]
	var n := NPC.new()
	add_child(n)
	n.setup(def, player)
	crowd.append(n)
	var it := Interactable.new()
	it.id = String(def.model)
	it.kind = "npc"
	it.npc = n
	it.label = "Say hi"
	it.range = 1.6
	n.interact = it
	interactables.append(it)


## The level's SPOT_ markers, plus the spots data/world.json adds (an entry with "override" replaces a marker);
## when each can be used is data too (world.json spot_when, or the entry's own `when`).
func _spawn_spots() -> void:
	_world_spots = WorldData.spots()
	var all := {}
	for id in binder.spots:
		all[id] = binder.spots[id].duplicate()
		all[id]["when"] = WorldData.spot_when(id)
	for id in _world_spots:
		if all.has(id) and not _world_spots[id].override:
			continue
		all[id] = _world_spots[id]
	for id in all:
		var s: Dictionary = all[id]
		var it := Interactable.new()
		it.id = id
		it.kind = "spot"
		it.pos = s.pos
		it.label = s.label
		it.range = s.range
		var when := String(s.get("when", ""))
		if when != "":
			it.condition = func(): return Conditions.eval(when)
		interactables.append(it)
	# the sit-downs offered in the world (V2-14): a "Sit" prompt where their chapter, condition and clock allow
	for id in WorldData.sit_ids():
		var st := WorldData.sit(String(id))
		if st.is_empty() or st.offer != "spot":
			continue
		var it := Interactable.new()
		it.id = String(id)
		it.kind = "sit"
		it.pos = st.spot
		it.label = st.label
		it.range = st.range
		var sid := String(id)
		it.condition = func(): return sit_available(sid)
		interactables.append(it)


var _notes: Array = []   # [Node3D, when]: the sticky notes data/world.json spots leave in the world


## A spot with a "note" (data/world.json: {pos, yaw, text, ink}) gets a sticky note lying there, its text in Mano's
## pen font in the writer's ink (Cristina's note by the cafeteria till, chapter 3); shown while the spot's `when`
## holds (_refresh_presence). A flat quad and a Label3D: nothing generated, nothing heavy.
func _spawn_notes() -> void:
	var sec := WorldData.section("spots")
	for id in sec:
		var e: Dictionary = sec[id]
		if not e.get("note") is Dictionary:
			continue
		var nd: Dictionary = e.note
		var root := Node3D.new()
		root.name = "Note_" + String(id)
		add_child(root)
		root.global_position = WorldData.vec(nd.get("pos", e.get("pos", [0, 0, 0])))
		root.rotation.y = deg_to_rad(float(nd.get("yaw", 0.0)))
		var paper := MeshInstance3D.new()
		var q := BoxMesh.new()
		q.size = Vector3(0.085, 0.002, 0.085)
		paper.mesh = q
		var m := StandardMaterial3D.new()
		m.albedo_color = Color(nd.get("paper", "#fff07a"))
		m.roughness = 0.9
		paper.material_override = m
		paper.position = Vector3(0, 0.001, 0)
		paper.rotation.y = deg_to_rad(4.0)
		paper.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		root.add_child(paper)
		var l := Label3D.new()
		l.text = String(nd.get("text", ""))
		l.font = UITheme.pen
		l.font_size = 44
		l.pixel_size = 0.00028
		l.modulate = Color(nd.get("ink", "#233e94"))
		l.outline_size = 0
		l.horizontal_alignment = HORIZONTAL_ALIGNMENT_LEFT
		l.width = 270.0
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		l.double_sided = false
		l.shaded = true
		# lying on the note, read from the note's -Z side (where Mano stands): the text's up runs away from him
		l.basis = Basis(Vector3(-1, 0, 0), Vector3(0, 0, 1), Vector3(0, 1, 0)).rotated(Vector3.UP, deg_to_rad(4.0))
		l.position = Vector3(0, 0.0025, 0)
		root.add_child(l)
		_notes.append([root, String(e.get("when", ""))])
	_show_notes()


func _show_notes() -> void:
	for n in _notes:
		(n[0] as Node3D).visible = String(n[1]) == "" or Conditions.eval(String(n[1]))


## The story's own lights (data/world.json "lights"): Toma's fairy lights on the courtyard steps from chapter 3 on.
## Each is one unshadowed omni light, on while its `when` holds and the preset is one of its `times`, with its bulbs
## as a string of small glowing beads (one MultiMesh) sagging between `bulbs` [from, to]. Nothing baked.
func _spawn_lights() -> void:
	var sec := WorldData.section("lights")
	for id in sec:
		var e: Dictionary = sec[id]
		var root := Node3D.new()
		root.name = "StoryLight_" + String(id)
		add_child(root)
		var col := Color(String(e.get("color", "#ffa65c")))
		var l := OmniLight3D.new()
		l.shadow_enabled = false
		l.light_bake_mode = Light3D.BAKE_DISABLED
		l.light_color = col
		l.light_energy = float(e.get("energy", 1.0))
		l.omni_range = float(e.get("range", 8.0))
		l.light_specular = 0.3
		root.add_child(l)
		l.global_position = WorldData.vec(e.get("pos", [0, 0, 0]))
		var b = e.get("bulbs", [])
		if b is Array and b.size() >= 2:
			var a := WorldData.vec(b[0])
			var z := WorldData.vec(b[1])
			var n := int(e.get("count", 24))
			var sag := float(e.get("sag", 0.25))
			var mm := MultiMesh.new()
			mm.transform_format = MultiMesh.TRANSFORM_3D
			var bead := SphereMesh.new()
			bead.radius = 0.035
			bead.height = 0.07
			bead.radial_segments = 8
			bead.rings = 4
			var m := StandardMaterial3D.new()
			m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
			m.albedo_color = col.lightened(0.35)
			m.emission_enabled = true
			m.emission = col
			m.emission_energy_multiplier = 3.0
			bead.material = m
			mm.mesh = bead
			mm.instance_count = n
			for i in n:
				var k := float(i) / maxf(n - 1, 1)
				var p := a.lerp(z, k) - Vector3.UP * sag * 4.0 * k * (1.0 - k)
				mm.set_instance_transform(i, Transform3D(Basis(), p))
			var mi := MultiMeshInstance3D.new()
			mi.multimesh = mm
			mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			root.add_child(mi)
		_story_lights.append([root, String(e.get("when", "")), e.get("times", [])])
	_show_lights()


var _story_lights: Array = []   # [Node3D, when, times]


## data/world.json "cam_occluders": boxes only the camera checks see (LevelBinder.CAMERA_OCCLUDERS: conversation
## shots, sit cameras), for level meshes with no collider (the Under's entrance door leaf, standing open by the bar:
## a conversation there is otherwise filmed from behind it, the frame flat teal). Nothing walks into them and
## nothing is drawn.
func _spawn_cam_occluders() -> void:
	var sec := WorldData.section("cam_occluders")
	for id in sec:
		var e: Dictionary = sec[id]
		var body := StaticBody3D.new()
		body.name = "CamOccluder_" + String(id)
		body.collision_layer = LevelBinder.CAMERA_OCCLUDERS
		body.collision_mask = 0
		var cs := CollisionShape3D.new()
		var box := BoxShape3D.new()
		box.size = WorldData.vec(e.get("size", [0.1, 2.0, 1.0]))
		cs.shape = box
		body.add_child(cs)
		add_child(body)
		body.global_transform = Transform3D(Basis(Vector3.UP, deg_to_rad(float(e.get("yaw", 0.0)))), WorldData.vec(e.get("pos", [0, 0, 0])))


func _show_lights() -> void:
	for sl in _story_lights:
		var times: Array = sl[2]
		(sl[0] as Node3D).visible = (String(sl[1]) == "" or Conditions.eval(String(sl[1]))) \
			and (times.is_empty() or world_env.time_of_day in times)


# ------------------------------------------------------------------ title / start
## The title is the live Amphi 4 at 17:41 (docs/DESIGN.md §7): Mano asleep in the seat by the aisle where Toma will
## wake him a minute later (Toma is not back yet), the Dijkstra slide glowing in the low sun, and the camera
## drifting slowly through 40° round him behind the menu (_update_title_camera).
func show_title() -> void:
	var first := mode == "loading"
	mode = "title"
	get_tree().paused = false
	hud.set_hud_visible(false)
	hud.set_letterbox(false)
	if world_env.time_of_day != WorldEnv.DEFAULT_TIME:
		hud.fade.color.a = 1.0   # back from later in the evening: the light goes back to 17:41 under black
		world_env.apply_time(WorldEnv.DEFAULT_TIME)
	player.frozen = true
	camera_rig.input_enabled = false
	phone.close(false)
	phone.hide_card()
	dialogue.clear_barks()
	hud.clear_freeze()
	_score = ""
	if _credits:
		_credits.queue_free()
		_credits = null
	if get_node_or_null("DrainGrate"):
		get_node("DrainGrate").queue_free()   # the post-credits' drain, on the pavement until the title
	_title_pose(true)
	_title_t = 0.0
	_update_title_camera(true)
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	Sfx.music("title", -8.0)
	Sfx.set_zone("amphi")
	if first:
		# the first time, the logo and the menu land on black and the amphi fades up behind them, so its
		# light and bounce (SDFGI, built as the level arrives) have settled by the time it shows
		_title_fade = create_tween()
		_title_fade.tween_interval(TITLE_SETTLE)
		_title_fade.tween_property(hud.fade, "color:a", 0.0, 1.8).set_trans(Tween.TRANS_SINE)
	else:
		hud.fade_to(0.0, 1.2)
	menus.show_title(GameState.has_save())


## Mano asleep for the title, in Toma's seat with his head down over the writing tablet, or back on his feet
## where he stood before (and Toma back in that seat) when the game starts. His body neither moves nor collides
## meanwhile.
func _title_pose(on: bool) -> void:
	if on == _title_seated:
		return
	_title_seated = on
	var toma: NPC = npcs.get("toma")
	if toma:
		toma.set_present(not on and toma.is_present())
	player.set_physics_process(not on)
	player.set_process(not on)
	player.rig.sitting = on
	player.rig.eyes_closed = 1.0 if on else 0.0
	player.rig.set_expression("tired" if on else "neutral")
	player.rig.look_at_point = null
	# slumped forward onto the tablet and a little to his left: the seated idle turned about the seat's front
	# edge (his legs go under the desk), which reads as asleep even from behind
	player.rig.rotation.x = deg_to_rad(TITLE_LEAN) if on else 0.0
	player.rig.rotation.z = deg_to_rad(-4.0) if on else 0.0
	if on:
		_title_return = [player.global_position, player.facing_yaw()]
		var seat: Vector3 = toma.def.get("pos", toma.global_position) if toma else binder.spawn.origin
		player.teleport(seat, PI)
		_title_from = seat + Vector3(0, 1.1, -0.28)   # his head, seated and slumped
		player.rig.look_at_point = seat + Vector3(0, -0.1, -0.6)   # the writing tablet under his nose
	else:
		player.teleport(_title_return[0], _title_return[1])


## New game or Continue picked while the first title is still fading up: that fade would fight the one to
## black and show Mano being moved out of the seat.
func _stop_title_fade() -> void:
	if _title_fade and _title_fade.is_valid():
		_title_fade.kill()
	_title_fade = null


## The title camera orbits Mano's head at 2.2 m, a seated eye height above it, from -2.4° to 37.6° off straight
## behind him (toward the wall), there and back every 2 × TITLE_DRIFT seconds; the look turns with it, so he stays
## put a little right of centre while the room and the slide drift behind him.
func _update_title_camera(cut := false) -> void:
	var k := 0.5 - 0.5 * cos(_title_t * PI / TITLE_DRIFT)
	var a := deg_to_rad(lerpf(-2.4, 37.6, k))
	var from := _title_from + Vector3(-sin(a) * 2.2, 0.6, cos(a) * 2.2)
	var look := _title_from + Vector3(-0.7, -0.08, -2.51).rotated(Vector3.UP, -(a - deg_to_rad(17.6)))
	# the sit-down lens: the desks right under the camera go soft, the slide stays readable
	camera_rig.set_shot(from, look, 50.0, from.distance_to(_title_from), cut, "sit")


## The title's "New game": with a save, a confirm page first (menus.confirm_new_game: "Start again" / "Keep my
## night"; Esc or B keeps it), V2-33.
func request_new_game() -> void:
	if GameState.has_save():
		menus.confirm_new_game()
	else:
		new_game()


## `forget_chapters` ("Start again" over a night in progress): the chapter snapshots go with the save. A new game
## with no night in progress keeps them: they are the last finished night's, for chapter select (V2-30).
func new_game(forget_chapters := false) -> void:
	GameState.reset_flags()
	GameState.clear_save()
	if forget_chapters:
		GameState.clear_chapter_saves()
	_clear_film()
	ducks.restore([])
	GameState.flags["chapter"] = Chapters.first()
	_apply_chapter_clock(Chapters.first())
	Chapters.reset_tracking()
	phone.restore(false)
	# the first to-do, quietly: the intro strikes it through and writes the next one
	hud.reset_objective(story.objective())
	menus.close()
	_stop_title_fade()
	var tw := hud.fade_to(1.0, 0.5)
	tw.tween_callback(func():
		# under black: Mano gets up from the title's seat and Toma is back in it; everyone goes where chapter 1
		# stages them (Karim by the seats, Ian and Silvia by the door, Ishita in the passage)
		_title_pose(false)
		_refresh_presence()
		_set_outfit(GameState.outfit)
		player.teleport(binder.spawn.origin, _yaw_from(binder.spawn))
		camera_rig.snap_behind(player.facing_yaw())
		_start_opening())


## A new game opens on its first chapter's opening: the cold open (chapter 0, "cold_open") or the dream and the
## wake-up (chapter 1, "wake").
func _start_opening() -> void:
	if String(Chapters.info().get("opening", "")) == "cold_open":
		_cold_open()
	else:
		_opening()


## Black card, the dream (docs/DESIGN.md §7: an 8.67 s clip, the engine's tumble joined to a Wan 3.0 drift, ending on the
## desk beside Mano; assets/video/CREDITS.md), then the wake-up: a beat on
## his algo notebook on the soft desk, then the blurry close-up of his face that sharpens as his eyelids flutter
## open, then Toma talks. With dream = false (nothing passes it at present), or
## without the clip file, the desk fades straight up out of the black.
func _opening(dream := true) -> void:
	mode = "cutscene"
	opening_phase = "card"
	hud.clear_freeze()
	player.frozen = true
	camera_rig.input_enabled = false
	hud.set_hud_visible(false)
	hud.set_letterbox(true)
	Input.mouse_mode = Input.MOUSE_MODE_HIDDEN
	Sfx.music("", -10.0)
	Sfx.set_zone("amphi")
	var ch: Dictionary = Chapters.info()
	world_env.apply_time(String(ch.get("time", WorldEnv.DEFAULT_TIME)))   # under the black card
	_show_card(ch)
	_chapter_t = 0.0
	_wake_pose()
	await get_tree().create_timer(3.2).timeout
	var shots := wake_shots()
	var desk: Array = shots[0]
	var close: Array = shots[1]
	camera_rig.set_shot(desk[0], desk[1], desk[2], -1.0, true)
	world_env.set_wake_blur(WAKE_DESK_BLUR, desk[3])
	var dreamt := false
	if dream:
		opening_phase = "dream"
		dreamt = await _play_dream()
	opening_phase = "wake"
	if not dreamt:
		await hud.fade_to(0.0, 1.2).finished
	# a beat on the soft desk, the camera drifting toward the notebook, then a cut to the close-up (Mano stands
	# between the two: a camera move from one to the other would pass through him)
	var t := 0.0
	while t < WAKE_HOLD:
		await get_tree().process_frame
		t += get_process_delta_time()
		var d := smoothstep(0.0, WAKE_HOLD, t) * WAKE_DRIFT
		camera_rig.set_shot(desk[0].move_toward(desk[1], d), desk[1], desk[2], -1.0, true)
		world_env.set_wake_blur(WAKE_DESK_BLUR, desk[3] - d)
	# his face, blurred, the focus racking in as his eyelids flutter open
	camera_rig.set_shot(close[0], close[1], close[2], -1.0, true)
	world_env.set_wake_blur(1.0, close[3])
	t = 0.0
	while t < 3.0:
		await get_tree().process_frame
		t += get_process_delta_time()
		var k := clampf(t / 3.0, 0.0, 1.0)
		world_env.set_wake_blur(1.0 - k * k, close[3])
		player.rig.eyes_closed = clampf(1.0 - k * 1.4 + (0.35 if (t > 1.2 and t < 1.45) else 0.0), 0.0, 1.0)
	world_env.set_focus(0.0, false)
	player.rig.eyes_closed = 0.0
	opening_phase = "talk"
	var with_id := String(ch.get("start_with", "toma"))
	var who: NPC = npcs.get(with_id)
	if who and String(ch.get("start_cue", "")) != "":
		talk_to(who.interact, story.intro())
	else:
		resume()
	_write_chapter_snapshot(Chapters.current())
	opening_phase = ""


## The cold open (chapter 0, docs/DESIGN.md §3.5 "23:41", V2-27): the steps at night, everyone on them, under the black a
## card with only the time and the place; then c0.open plays its three shots (world.json cold_wide, cold_hand,
## cold_face), "Want one?", the freeze and "Okay. How did I get here?", then "Six hours earlier." over black, and its
## `$ chapter 1` hands over to chapter 1's own opening (_wake_chapter). Nothing here is saved: a quit before chapter
## 1 starts a new game again.
func _cold_open() -> void:
	mode = "cutscene"
	opening_phase = "cold_open"
	player.frozen = true
	camera_rig.input_enabled = false
	hud.set_hud_visible(false)
	hud.fade.color.a = 1.0
	hud.set_letterbox(true, true)
	Input.mouse_mode = Input.MOUSE_MODE_HIDDEN
	dialogue.clear_barks()
	var n := 0
	var ch: Dictionary = Chapters.get_chapter(n)
	GameState.flags["chapter"] = n
	GameState.flags["banners"] = []
	GameState.flags["stage_over"] = {}
	_apply_chapter_clock(n)
	world_env.apply_time(String(ch.get("time", "late")))
	var at := String(ch.get("start_at", ""))
	var tp: Dictionary = target_of(at.get_slice(":", 0), at.get_slice(":", 1), "") if at != "" else {}
	if not tp.is_empty():
		player.teleport(tp.pos, float(tp.get("yaw", player.facing_yaw())))
	camera_rig.snap_behind(player.facing_yaw())
	_apply_stage(ch)
	_show_lights()
	# Mano holding his phone low, his face down to it (the third shot lights his face with its glow: world.json lights)
	player.rig.set_expression("neutral")
	player.rig.look_at_point = player.global_position + Vector3(sin(player.facing_yaw()), 0, cos(player.facing_yaw())) * 0.5 + Vector3.UP * 1.05
	Sfx.set_zone("court")
	Sfx.music("ending", -20.0, 3.0)   # tiny, from an AirPod held out at arm's length
	print("[chapter] 0 cold open: time %s, clock %s, Mano at %s" % [world_env.time_of_day, Chapters.clock_text(), player.global_position.snapped(Vector3.ONE * 0.01)])
	_show_card(ch)
	await get_tree().create_timer(3.4).timeout
	if mode != "cutscene":
		return
	camera_shot("cold_wide")
	hud.fade_to(0.0, 1.2)
	say(story.steps(String(ch.get("start_cue", "c0.open"))))
	opening_phase = "cold_open_shots"


## Chapter 1 reached from the cold open: the caption has left the screen black; under it Mano is back in Amphi 4 at
## 17:42, everyone where chapter 1 stages them, and its own opening plays (the card, the dream, the wake-up).
func _wake_chapter(n: int) -> void:
	var ch: Dictionary = Chapters.get_chapter(n)
	print("[chapter] %d %s from the cold open: the dream and the wake-up" % [n, ch.get("title", "")])
	mode = "cutscene"
	hud.fade.color.a = 1.0
	hud.clear_freeze()
	_set_reach(false)
	camera_rig.clear_shot(true)
	_hold_shot = false
	set_score("")
	GameState.flags["chapter"] = n
	GameState.flags["banners"] = []
	GameState.flags["stage_over"] = {}
	_apply_chapter_clock(n)
	player.rig.look_at_point = null
	player.teleport(binder.spawn.origin, _yaw_from(binder.spawn))
	camera_rig.snap_behind(player.facing_yaw())
	_apply_stage(ch)
	_show_lights()
	Chapters.reset_tracking()
	hud.reset_objective(story.objective())
	GameState.flags_changed.emit()
	_opening()


## The chapter's card (data/chapters.json "card"): time, date, place and the chapter's number and name.
func _show_card(ch: Dictionary) -> ChapterCard:
	var c: Dictionary = ch.get("card", {})
	return hud.title_card(String(c.get("time", Conditions.clock_text(Chapters.clock()))),
		"%s\n%s" % [c.get("date", "jeudi 15 octobre"), c.get("place", "")], ChapterCard.HOLD, String(c.get("chapter", "")))


func _apply_chapter_clock(n: int) -> void:
	var m := Conditions.minutes(String(Chapters.get_chapter(n).get("clock", "")))
	if m >= 0:
		GameState.flags["clock"] = m
	_clock_acc = 0.0


## A chapter begins (V2-20): to black, the card, and under it the chapter's light preset, clock and staging; the
## chapter snapshot (user://save_ch<n>.json) is written; then its start cue plays, or play resumes. A chapter the
## data does not have yet plays bridge.end (the "à suivre…" page). `replay` (chapter select, autotest chapter=<n>)
## starts from the card with no fade from the scene.
func begin_chapter(n: int, replay := false) -> void:
	if not Chapters.has(n):
		say(story.steps("bridge.end"))
		return
	var ch: Dictionary = Chapters.get_chapter(n)
	# the cold open is chapter 0 itself (a replay too); chapter 1 reached from it plays its own opening, the dream and
	# the wake-up, under the black the cold open's caption left (a chapter-select replay of chapter 1 skips both)
	if String(ch.get("opening", "")) == "cold_open":
		_cold_open()
		return
	if String(ch.get("opening", "")) == "wake" and not replay:
		_wake_chapter(n)
		return
	print("[chapter] %d %s: card %s, time %s, clock %s" % [n, ch.get("title", ""), ch.get("card", {}).get("chapter", ""), ch.get("time", ""), ch.get("clock", "")])
	mode = "cutscene"
	opening_phase = "chapter_card"
	player.frozen = true
	camera_rig.input_enabled = false
	hud.set_hud_visible(false)
	Input.mouse_mode = Input.MOUSE_MODE_HIDDEN
	Sfx.duck_music(true)
	if not replay:
		await hud.fade_to(1.0, 0.6).finished
	else:
		hud.fade.color.a = 1.0
	hud.set_letterbox(false, true)
	camera_rig.clear_shot(true)
	# the phone's lock screen goes under the black: a chapter's last line can leave it up (c3.end's "21:00. Memory
	# on." at 20:40), and `$ chapter` skips the conversation's end, which puts it away: it stayed over the whole of
	# chapter 4's meeting with Cristina, still showing 20:40
	phone.hide_card()
	# a chapter that opens somewhere else than the last one ended (chapters.json card_at: chapter 3 in the Under,
	# after chapter 2's sunset on rue Pasteur) puts Mano there under the card
	var at := String(ch.get("card_at", ""))
	if at != "" and not replay:
		var tp: Dictionary = target_of(at.get_slice(":", 0), at.get_slice(":", 1), "")
		if not tp.is_empty():
			player.teleport(tp.pos, float(tp.get("yaw", player.facing_yaw())))
	# the chapter opens behind Mano, as start_chapter and Continue do (not wherever the camera was before the
	# conversation that ended the last chapter)
	camera_rig.snap_behind(player.facing_yaw())
	GameState.flags["chapter"] = n
	GameState.flags["banners"] = []
	GameState.flags["stage_over"] = {}   # a `$ stage` lasts until the chapter's own staging takes over
	_apply_chapter_clock(n)
	world_env.apply_time(String(ch.get("time", world_env.time_of_day)))   # under the black and the card
	_apply_stage(ch)
	_show_lights()
	Chapters.reset_tracking()
	GameState.flags_changed.emit()
	_chapter_t = 0.0
	_show_card(ch)
	_write_chapter_snapshot(n)
	# the save follows the chapter at once, under the card: a quit before the next autosave (30 s of play) or the
	# next conversation's end must not bring the night back in the last chapter's light and clock
	save()
	await get_tree().create_timer(3.2).timeout
	await hud.fade_to(0.0, 1.0).finished
	opening_phase = ""
	Sfx.duck_music(false)
	var cue := String(ch.get("start_cue", ""))
	var with_id := String(ch.get("start_with", ""))
	if cue != "" and story.has_cue(cue):
		say(story.steps(cue), with_id)
	else:
		camera_rig.clear_shot(true)
		resume()
		hud.show_objective()


## Starts chapter `n` straight from the title (autotest chapter=<n>, the title's Chapters page): its snapshot when there
## is one, else its start_flags; Mano at its start_at; no dream.
func start_chapter(n: int, keep_finds := false) -> void:
	_refresh_presence.call_deferred()
	_score = ""
	hud.clear_freeze()
	menus.close()
	_stop_title_fade()
	_title_pose(false)
	var finds := Collectibles.best_known() if keep_finds else {}
	var snap = GameState.read_chapter_save(n)
	if snap is Dictionary:
		GameState.apply_save(snap)
	else:
		GameState.reset_flags()
		var sf: Dictionary = Chapters.get_chapter(n).get("start_flags", {})
		for k in sf:
			GameState.flags[k] = GameState._copy(sf[k])
		GameState.coerce_flags()
	GameState.flags["chapter"] = n
	if keep_finds:
		# chapter select (V2-30): the night's choices are the snapshot's, the ducks, photos and moments found so far stay
		Collectibles.merge(finds)
	Chapters.reset_tracking()
	phone.restore(bool(GameState.flags.get("phone_charged", false)))
	hud.reset_objective(story.objective())   # a start from the title strikes nothing through
	_set_outfit(GameState.outfit)
	ducks.restore(GameState.ducks_found)
	var at := String(Chapters.get_chapter(n).get("start_at", ""))
	var t: Dictionary = target_of(at.get_slice(":", 0), at.get_slice(":", 1), "") if at != "" else {}
	if snap is Dictionary and snap.has("pos"):
		player.teleport(Vector3(snap.pos[0], snap.pos[1], snap.pos[2]), float(snap.get("yaw", 0.0)))
	elif not t.is_empty():
		player.teleport(t.pos, float(t.get("yaw", 0.0)))
	camera_rig.snap_behind(player.facing_yaw())
	await begin_chapter(n, true)


## The chapter's staging (chapters.json "stage", V2-21): everyone is put where the chapter wants them, under the
## card. Staging is re-read whenever presence is (the end of a conversation or a minigame), so an entry's `when`
## can move someone between beats (Karim leaves the amphi once Toma has talked).
func _apply_stage(_ch: Dictionary) -> void:
	for id in npcs:
		npcs[id].stage_key = "-"   # forget the last chapter's staging: everyone is placed afresh
	_refresh_presence()


## One character to their staging now (Chapters.stage_of): shown or hidden, at their point or home, following
## Mano or not. Nothing moves while the staging is the one already applied.
func restage(id: String) -> void:
	var n: NPC = npcs.get(id)
	if n == null:
		return
	var present := n.is_present()
	n.set_present(present)
	var st := Chapters.stage_of(id)
	var follow: bool = id in GameState.flags.get("following", []) or bool(st.get("follow", false))
	var key := String(st.get("key", ""))
	if n.following and not (follow and present):
		# just stopped following: they stay where they stand, under whatever staging holds now (or, staged with
		# "leave", walk off to it)
		n.unfollow()
		if not bool(st.get("leave", false)):
			n.stage_key = key
	if present and key != n.stage_key and not follow:
		n.stage_key = key
		if st.has("point"):
			var p := WorldData.point(String(st.point))
			if not p.is_empty():
				var yaw: float = deg_to_rad(float(st.yaw)) if st.has("yaw") else p.yaw
				if bool(st.get("walk", false)) and n.visible and n.global_position.distance_to(p.pos) < 30.0:
					n.walk_to(p.via + [p.pos], yaw)   # on foot, through the aisles: nobody pops into place in view
				elif bool(st.get("leave", false)) and n.visible and n.global_position.distance_to(player.global_position) < 20.0 \
						and n.global_position.distance_to(p.pos) > 6.0 and mode != "cutscene":
					n.leave_to(p.pos, yaw, player.global_position, st)   # off out of view first, then there
				else:
					n.apply_stage(p.pos, yaw, st)
			else:
				push_warning("staging: %s's point '%s' is not in data/world.json" % [id, st.point])
		elif not bool(n.def.get("staged_only", false)):
			var home: Dictionary = _homes.get(id, {"pos": n.global_position, "yaw": n.def.get("yaw", 0.0)})
			n.apply_stage(home.pos, home.yaw, st, true)
	if follow and present:
		n.stage_key = key
		n.follow(player)


## `$ place who point`: Mano or a character straight to a world.json point (the cut hides it).
func place_at(who: String, point: String) -> void:
	var p := WorldData.point(point)
	if p.is_empty():
		push_warning("place: no point '%s' in data/world.json" % point)
		return
	if who == "mano":
		player.teleport(p.pos, p.yaw)
		camera_rig.snap_behind(player.facing_yaw())
	elif npcs.has(who):
		npcs[who].apply_stage(p.pos, p.yaw, {})
		npcs[who].reset_trail()   # a follower set down elsewhere: the trail behind their old place leads nowhere


## `$ shot name` (data/world.json "shots": {from, look, fov}): a framed camera for a beat; "clear" hands the
## camera back.
func camera_shot(name: String, cut := true) -> void:
	if name == "clear":
		_set_reach(false)
		camera_rig.clear_shot(cut)
		return
	var sh: Dictionary = WorldData.section("shots").get(name, {})
	if sh.is_empty():
		push_warning("shot: no shot '%s' in data/world.json" % name)
		return
	var from := WorldData.vec(sh.get("from", [0, 0, 0]))
	var look := WorldData.vec(sh.get("look", [0, 0, 0]))
	_set_reach(bool(sh.get("reach", false)), WorldData.vec(sh.get("reach_bud", [-0.01, 0.035, 0.09])))
	if String(sh.get("on", "")) == "mano":
		# a shot relative to where Mano stands and faces (as a sit camera: rel [degrees, metres, height], look_h,
		# look_rel), so it frames him wherever the scene put him (the cold open's close shots); `head` [degrees,
		# metres, height] frames his face from his head bone instead (whatever his height)
		if sh.get("head") is Array:
			var hd: Array = sh.head
			var head := player.rig.head_position() - Vector3.UP * 0.07
			var a := player.facing_yaw() + deg_to_rad(float(hd[0]))
			from = head + Vector3(sin(a), 0, cos(a)) * float(hd[1]) + Vector3.UP * float(hd[2])
			look = head
		else:
			var c := WorldData.sit_cam(sh, player.global_position, player.facing_yaw())
			from = c.from
			look = c.look
		from = _unblock(look, from)
	_hold_shot = true
	hud.set_letterbox(true)
	camera_rig.set_shot(from, look, float(sh.get("fov", 40.0)), from.distance_to(look), cut)


## The cold open's "Want one?" (a world.json shot with "reach": true): Mano's right arm held out in front of him, an
## AirPod in his hand. Two look-at modifiers on his upper and lower arm (their bones run along +Y) aim them at a point
## in front of his chest, and a small AirPod rides his hand bone; off again with the next shot.
var _reach: Array = []


func _set_reach(on: bool, bud_at := Vector3(-0.01, 0.035, 0.09)) -> void:
	for n in _reach:
		if is_instance_valid(n):
			n.queue_free()
	_reach.clear()
	if not on or player == null or player.rig == null or player.rig.skeleton == null:
		return
	var sk: Skeleton3D = player.rig.skeleton
	if sk.find_bone("upperarm_r") == -1 or sk.find_bone("lowerarm_r") == -1 or sk.find_bone("hand_r") == -1:
		return
	var yaw := player.facing_yaw()
	var fwd := Vector3(sin(yaw), 0, cos(yaw))
	var right := Vector3(-cos(yaw), 0, sin(yaw))
	var target := Node3D.new()
	target.name = "ReachTarget"
	add_child(target)
	target.global_position = player.global_position + fwd * 0.62 + right * 0.16 + Vector3.UP * 1.12
	_reach.append(target)
	for bone in ["upperarm_r", "lowerarm_r"]:
		var m := LookAtModifier3D.new()
		sk.add_child(m)
		m.bone_name = bone
		m.forward_axis = SkeletonModifier3D.BONE_AXIS_PLUS_Y
		m.target_node = m.get_path_to(target)
		m.use_angle_limitation = false
		m.duration = 0.0
		m.influence = 1.0
		_reach.append(m)
	var att := BoneAttachment3D.new()
	att.bone_name = "hand_r"
	sk.add_child(att)
	var white := StandardMaterial3D.new()
	white.albedo_color = Color(0.97, 0.97, 0.96)
	white.roughness = 0.18
	white.clearcoat_enabled = true
	# the AirPod: a bud and its stem on a pivot that rides the hand bone
	var pod := Node3D.new()
	att.add_child(pod)
	var bud := MeshInstance3D.new()
	var sm := SphereMesh.new()
	sm.radius = 0.0105
	sm.height = 0.021
	bud.mesh = sm
	bud.material_override = white
	pod.add_child(bud)
	var stem := MeshInstance3D.new()
	var cm := CapsuleMesh.new()
	cm.radius = 0.0034
	cm.height = 0.034
	stem.mesh = cm
	stem.material_override = white
	stem.position = Vector3(0.012, -0.004, 0.0)
	stem.rotation.z = 1.2
	pod.add_child(stem)
	_reach.append(att)
	_seat_pod(att, pod, right * bud_at.x + Vector3.UP * bud_at.y + fwd * bud_at.z)


## Once the arm has reached out (the look-at modifiers run with the skeleton's next update), the AirPod is put on
## the palm: `offset` from the wrist in Mano's own frame (world.json shot "reach_bud": [right, up, forward]), which
## the hand bone's frame (different in each model) cannot say directly. It keeps that place on the hand from then on.
func _seat_pod(att: BoneAttachment3D, pod: Node3D, offset: Vector3) -> void:
	for i in 2:
		await get_tree().process_frame
	if is_instance_valid(att) and is_instance_valid(pod):
		pod.global_position = att.global_position + offset
		pod.global_rotation = Vector3.ZERO


## `$ phone action [arg] ["text"]` (Phone, V2-24). Returns how long the conversation waits on it: seconds, or -1
## for "until Mano puts the phone away" (open).
func phone_cmd(action: String, who := "", text := "") -> float:
	match action:
		"show":
			phone.show_lock(Chapters.clock_text())
			return 0.6
		"preview":
			var info := _speaker_info(who)
			phone.preview(String(info.get("name", who)), text)
			return 1.6
		"die":
			phone.set_time(Chapters.clock_text())
			phone.die()
			return 2.2
		"hide":
			phone.hide_card()
			return 0.0
		"charge":
			GameState.flags["phone_charged"] = true
			GameState.flags_changed.emit()
			phone.charge(Chapters.clock_text())
			hud.hint("phone")
			return 1.2
		"flood":
			# `who` is the batch: it lands (with any earlier one not delivered yet), buzzing on the lock screen
			var fresh := Chat.deliver(who)
			GameState.flags_changed.emit()
			print("[phone] %d messages land (batch %s), %d unread" % [fresh.size(), who, Chat.total_unread()])
			return phone.flood(fresh, Chapters.clock_text())
		"open":
			phone.open_app(who if who != "" else "home")
			return -1.0
		"finder":
			GameState.flags["finder_place"] = who
			GameState.flags["finder_time"] = text
			GameState.flags_changed.emit()
			toast("On my map", "pin")
			return 0.3
	push_warning("phone: unknown action '%s'" % action)
	return 0.0


## The phone key in play (V2-24): the phone up in his hand once it is charged (chapter 3); before that his dead
## phone, a moment, and a thought (phone.dead).
func open_phone(which := "home") -> void:
	if not bool(GameState.flags.get("phone_charged", false)):
		phone.show_dead()
		if story.has_cue("phone.dead"):
			dialogue.clear_barks()
			for l in story.bark_cue("phone.dead"):
				dialogue.bark(l[0], l[1])
		return
	enter_menu("phone")
	phone.open_app(which)
	if not phone.closed.is_connected(_on_phone_closed):
		phone.closed.connect(_on_phone_closed, CONNECT_ONE_SHOT)


func _on_phone_closed() -> void:
	if mode == "phone":
		resume()


## `$ song stem [seconds]`: a track previewed from the phone (the playlist pick), then the place's music again.
func preview_song(stem: String, seconds := 10.0) -> void:
	Sfx.song(stem, -8.0, 0.8, 1.0)
	get_tree().create_timer(seconds).timeout.connect(func():
		if Sfx.music_now() == stem and mode != "sit":
			var m: Array = place_music()
			Sfx.music(m[0], m[1], 2.0, 1.5))


## The track for here and now: the story's score while one holds (`$ score`, the finale's song), else the place's
## music (chapters.json "music").
func place_music() -> Array:
	if _score != "":
		return [_score, SCORE_DB]
	return Chapters.music_for(world_env.time_of_day, zone_id())


## `$ score stem`: a track as the score from now on, until the credits are over ("" hands back to the places' music).
func set_score(stem: String) -> void:
	_score = stem
	if stem != "":
		print("[music] score: %s" % stem)
		Sfx.music(stem, SCORE_DB, 3.0, 2.0)
		Chat.heard(stem)


const SCORE_DB := -7.0
var _score := ""


func _write_chapter_snapshot(n: int) -> void:
	if player == null:
		return
	GameState.ducks_found = ducks.found_ids() if ducks else []
	GameState.write_chapter_save(n, player.global_transform.rotated_local(Vector3.UP, player.facing_yaw()))


## Mano as the wake-up finds him (eyes shut, tired, turned toward Toma's seat) and his algo notebook open on the
## desk beside him. autotest=dream renders the dream clip's end frame from the same state.
func _wake_pose() -> void:
	player.rig.eyes_closed = 1.0
	player.rig.set_expression("tired")
	var toma: NPC = npcs.get("toma")
	if toma:
		player.face_towards(toma.global_position)
	if _notebook == null:
		_notebook = AlgoNotebook.new()
		add_child(_notebook)
		_notebook.global_position = NOTEBOOK_AT
		_notebook.rotation.y = NOTEBOOK_YAW


## The wake-up's two shots, [from, look, fov, focus distance] each: the desk beside Mano with his notebook in the
## low sun and him just out of frame (the dream clip's last frame), then the close-up of his face.
func wake_shots() -> Array:
	var face := player.rig.bone_global("head") + Vector3.UP * 0.045
	var fwd := Vector3(sin(player.facing_yaw()), 0, cos(player.facing_yaw()))
	var side := Vector3(fwd.z, 0, -fwd.x)
	var from := face + fwd * 0.78 + side * 0.22 + Vector3.UP * 0.03
	return [[WAKE_DESK_FROM, WAKE_DESK_LOOK, WAKE_DESK_FOV, WAKE_DESK_FROM.distance_to(NOTEBOOK_AT)], [from, face, 30.0, 0.62]]


## The dream clip under the lens finish (the post layer's grain and vignette run over it, as on the 3D): it comes
## up out of the black as the chapter card turns away, and its last frames dissolve into the desk shot, already
## live behind it, on which it ends. The letterbox leaves under the black so the frame shows whole, the slide at
## its top too, and closes in again over the dissolve for the wake-up. False (and nothing shown) if the clip
## can't be loaded.
func _play_dream() -> bool:
	var stream := load(DREAM) as VideoStream if ResourceLoader.exists(DREAM) else null
	if stream == null:
		return false
	var layer := CanvasLayer.new()
	layer.name = "Dream"
	layer.layer = _post.layer - 1
	var black := ColorRect.new()   # a window wider than 16:9 has black at the clip's sides
	black.color = Color.BLACK
	black.set_anchors_preset(Control.PRESET_FULL_RECT)
	black.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layer.add_child(black)
	# the window's full height, as the 3D camera keeps it: never cropped top or bottom; a 16:10 window crops the
	# sides as the 3D camera does, so the last frames still line up with the live shot
	var box := AspectRatioContainer.new()
	box.set_anchors_preset(Control.PRESET_FULL_RECT)
	box.ratio = 16.0 / 9.0
	box.stretch_mode = AspectRatioContainer.STRETCH_HEIGHT_CONTROLS_WIDTH
	box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layer.add_child(box)
	var vp := VideoStreamPlayer.new()
	vp.stream = stream
	vp.expand = true
	vp.mouse_filter = Control.MOUSE_FILTER_IGNORE
	box.add_child(vp)
	_post.get_parent().add_child(layer)   # on HiDPI the lens finish runs inside the WorldView: the clip goes there too
	dream_player = vp
	hud.set_letterbox(false, true)   # still under the black
	_post.set("cinematic", true)     # the vignette stays closed in without the bars
	vp.play()
	hud.fade_to(0.0, DREAM_IN)
	var length := vp.get_stream_length()
	while vp.is_playing() and (length <= 0.0 or vp.stream_position < length - DREAM_OUT):
		await get_tree().process_frame
	hud.set_letterbox(true)
	var tw := create_tween().set_parallel()
	tw.tween_property(box, "modulate:a", 0.0, DREAM_OUT)
	tw.tween_property(black, "modulate:a", 0.0, DREAM_OUT)
	await tw.finished
	_post.set("cinematic", false)
	dream_player = null
	layer.queue_free()
	return true


func continue_game() -> void:
	_refresh_presence.call_deferred()
	_score = ""
	var data = GameState.read_save()
	if data == null:
		new_game()
		return
	GameState.apply_save(data)
	Chapters.reset_tracking()
	phone.restore(bool(GameState.flags.get("phone_charged", false)))
	# the saved objective replaces whatever the strip held before (another save, an earlier night) outright: a
	# load is not a change, so nothing is struck through
	hud.reset_objective(story.objective())
	menus.close()
	ducks.restore(GameState.ducks_found)
	_stop_title_fade()
	var tw := hud.fade_to(1.0, 0.4)
	tw.tween_callback(func():
		_title_pose(false)
		_set_outfit(GameState.outfit)
		var p: Array = data.get("pos", [binder.spawn.origin.x, binder.spawn.origin.y, binder.spawn.origin.z])
		player.teleport(Vector3(p[0], p[1], p[2]), data.get("yaw", 0.0))
		camera_rig.snap_behind(player.facing_yaw())
		world_env.apply_time(GameState.flags.get("time", WorldEnv.DEFAULT_TIME))
		camera_rig.clear_shot(true)
		hud.fade_to(0.0, 0.8)
		resume()
		# saved between a chapter's last beat and its card (a sit-down at the sunset, a quit under it): the card
		# plays now, or the night would wait in a finished chapter with nothing left to do
		var ends := String(Chapters.info().get("ends_with", ""))
		if ends != "" and bool(GameState.flags.get(ends, false)):
			if Chapters.has(Chapters.current() + 1):
				begin_chapter(Chapters.current() + 1)
				return
			if not bool(GameState.flags.get("credits_done", false)):
				# saved after the last chapter's last beat, before the credits had played (a quit during them)
				roll_credits()
				return
		# saved under the card, before the chapter's first scene had played through (a quit during chapter 3's phone
		# scene with Karim): that scene plays again, or the chapter goes on with no objective and a dead phone
		if Chapters.start_pending():
			_replay_start_cue()
			return
		hud.show_objective()   # where was I: once after loading, not after every conversation
		toast("Welcome back", "smile"))


## Continue on a save whose chapter's start cue never played through (Chapters.start_pending): the cue again from
## its start, with whoever it starts with, once the picture is back. Its steps are safe to play twice (the phone's
## charge and its flood deliver only what has not landed, the clock never goes back).
func _replay_start_cue() -> void:
	var ch: Dictionary = Chapters.info()
	var cue := String(ch.get("start_cue", ""))
	print("[chapter] Continue in chapter %d before its start cue ended: %s again" % [Chapters.current(), cue])
	mode = "cutscene"
	player.frozen = true
	await get_tree().create_timer(0.9).timeout
	if mode != "cutscene":
		return
	if story.has_cue(cue):
		say(story.steps(cue), String(ch.get("start_with", "")))
	else:
		resume()


func resume() -> void:
	mode = "play"
	get_tree().paused = false
	_title_pose(false)   # straight from the title (dev plans do): Mano gets up where he stood
	menus.close()
	hud.set_hud_visible(true)
	hud.set_letterbox(false)
	player.frozen = false
	camera_rig.input_enabled = true
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	_zone_music()
	Sfx.duck_music(false)
	# the objective shows itself only when it changes (on_flags_changed), never again after every conversation
	hud.set_objective(story.objective(), false)
	hud.hint("move")
	if phone.is_open():
		phone.close(false)
	if phone.state == "lock":
		phone.hide_card()


func _set_outfit(key: String) -> void:
	GameState.outfit = key
	if player:
		player.set_model("res://assets/characters/%s.glb" % OUTFITS[key].model)
		_sync_airpods()


## The AirPods as the story has them: one in his left ear; from chapter 4's sound search both (flags.found); then
## both in their case (flags.airpods_case, Anisha's SOS); after the post-credits (flags.credits_done) the right one is
## down the drain on rue Pasteur again. A new model (an outfit, a load) starts with the left one.
func _sync_airpods() -> void:
	if player == null:
		return
	player.stowed = false
	if bool(GameState.flags.get("found", false)) and int(GameState.flags.get("chapter", 1)) >= 4 \
			and not bool(GameState.flags.get("credits_done", false)):
		player.give_second_airpod()
	player.stow_airpods(bool(GameState.flags.get("airpods_case", false)))


func outfit_unlocked(key: String) -> bool:
	return not OUTFITS[key].has("locked") or GameState.flags.get("merch", false)


func wear(key: String) -> void:
	if outfit_unlocked(key) and key != GameState.outfit:
		_set_outfit(key)
		save()


# ------------------------------------------------------------------ main loop
func _process(dt: float) -> void:
	if mode == "loading":
		if not _loading.is_empty():
			_poll_loading()
		return
	if player == null:
		return
	if mode == "title":
		_title_t += dt
		_update_title_camera(true)
	# the conversation fill (one unshadowed light by the lens): conversations, a story's framed shot (`$ shot`: chapter 3's
	# last beat on rue Pasteur at night), and the sit-downs' faces at blue hour
	world_env.set_convo_fill((mode == "dialogue" and (not _conv.is_empty() or (_hold_shot and camera_rig.has_shot())))
		or (mode == "sit" and camera_rig.has_shot()), camera_rig.cam, dt, camera_rig.shot_look())
	if mode != "title":
		GameState.play_time += dt   # the recap's "minutes on campus": talks, minigames and cutscenes count too
	if mode == "sit":
		_tick_clock(dt)
		_update_sit(dt)
	if mode == "play":
		_tick_clock(dt)
		_chapter_t += dt
		_trigger_t -= dt
		if _trigger_t <= 0.0:
			_trigger_t = 0.25
			_poll_triggers()
			if mode != "play":
				return
		var target = player.find_interactable()
		player.interact_target = target
		hud.set_prompt(target)
		hud.mano_pos = player.global_position
		_update_idle(dt)
		_photo_poll -= dt
		if _photo_poll <= 0.0:
			_photo_poll = 0.5
			_photo_thought()
		_update_zone()
		_update_waypoint()
		_update_journal_key(dt)
		_save_clock -= dt
		if _save_clock <= 0.0:
			_save_clock = 30.0
			save()
	else:
		player.interact_target = null
		hud.set_prompt(null)
		hud.waypoint_target = null
		hud.mano_pos = null
		if _journal_hold >= 0.0:
			_journal_hold = -1.0
			hud.peek_objective(false)


## The story clock moves on slowly while Mano walks about (chapters.json clock_rate, game minutes per real
## minute), never past the chapter's clock_end nor the time its next pinned beat sets (Chapters.clock_cap); the
## story's own `$ clock` steps move it on outright, never back.
func _tick_clock(dt: float) -> void:
	_clock_acc += dt * Chapters.clock_rate() / 60.0
	if _clock_acc < 1.0:
		return
	var whole := floorf(_clock_acc)
	_clock_acc -= whole
	GameState.flags["clock"] = mini(Chapters.clock() + int(whole), maxi(Chapters.clock_cap(), Chapters.clock()))


# ------------------------------------------------------------------ idle life and the film (V2-31, V2-30)
const IDLE_AFTER := 20.0     # seconds standing still before Mano looks round or checks his phone (docs/DESIGN.md §4.7)
const IDLE_AGAIN := [28.0, 45.0]
const IDLE_THINK := 0.45     # how often a beat comes with a thought


## Standing still in play (no move input, not jogging, no conversation): after IDLE_AFTER seconds Mano looks round
## (look_around) or glances at his phone (the lock screen; the black screen before chapter 3), sometimes with a
## thought (dialogue/idle.dlg, a bark). Any move starts the count again.
func _update_idle(dt: float) -> void:
	var moving := Input.get_vector("move_left", "move_right", "move_forward", "move_back").length() > 0.05 \
		or Vector2(player.velocity.x, player.velocity.z).length() > 0.2
	if moving or dialogue.is_barking() or overheard.playing() != "":
		_idle_t = 0.0
		_idle_next = IDLE_AFTER
		return
	if _idle_next <= 0.0:
		_idle_next = IDLE_AFTER
	_idle_t += dt
	if _idle_t >= _idle_next:
		_idle_t = 0.0
		_idle_next = randf_range(IDLE_AGAIN[0], IDLE_AGAIN[1])
		_idle_beat()


func _idle_beat() -> void:
	var charged := bool(GameState.flags.get("phone_charged", false))
	var dead := bool(GameState.flags.get("phone_dead", false)) and not charged
	var kind := "phone" if (charged or dead) and randf() < 0.4 and not bool(GameState.flags.get("airpods_case", false)) else "look"
	var cue := "idle.look"
	if kind == "phone":
		cue = "idle.phone" if charged else "idle.phone_dead"
		phone.glance(not charged)
	elif player.rig and player.rig.has_clip("look_around"):
		player.rig.play_gesture("look_around")
	var thought := ""
	if kind == "phone" or randf() < IDLE_THINK:
		var lines := story.bark_cue(cue)
		if not lines.is_empty():
			thought = String(lines[0][1])
			dialogue.bark(String(lines[0][0]), thought)
	idle_beats.append({"kind": kind, "thought": thought, "at": Chapters.clock_text(), "frozen": player.frozen})
	print("[idle] %s%s" % [kind, (": " + thought) if thought != "" else ""])


## Passing an open photo spot with Ishita's camera and film left: Mano thinks it would make a photo, once a spot,
## and the photo mode key hint comes up (the first time). Taking it is photo mode's job (Menus._capture_photo).
func _photo_thought() -> void:
	if Film.left() <= 0 or dialogue.is_barking():
		return
	var s := Film.near(player.global_position)
	if s.is_empty() or Film.taken().has(s.id) or not Film.open_now(s) or String(s.think) == "":
		return
	var seen: Array = GameState.flags.get("photo_seen", [])
	if s.id in seen:
		return
	seen = seen.duplicate()
	seen.append(s.id)
	GameState.flags["photo_seen"] = seen
	dialogue.bark("think", String(s.think))
	hud.hint("photo_mode")
	print("[photo] near %s: %s" % [s.id, s.think])


## The chapter's triggers (chapters.json "triggers"): the first one due plays its cue (with its npc).
func _poll_triggers() -> void:
	var due: Array = Chapters.pending_triggers(self, false, _chapter_t)
	if due.is_empty():
		return
	play_trigger(due[0])


func play_trigger(tr: Dictionary) -> void:
	Chapters.mark_fired(tr)
	var cue := String(tr.get("cue", ""))
	print("[chapter] trigger %s -> %s" % [tr.get("id", ""), cue])
	# a thought on the way (a `bark` trigger whose cue is think-only): shown while Mano keeps walking
	if bool(tr.get("bark", false)) and DialogueData.is_think_only(cue):
		for l in story.bark_cue(cue):
			dialogue.bark(l[0], l[1])
		return
	var with_id := String(tr.get("with", ""))
	# a staged scene ("place": {who: world.json point}): everyone to their marks before the first shot, which is a
	# cut, so the conversation is filmed where it is framed, not wherever Mano happens to cross the trigger
	# (in a doorway, say, with every line framed on the open door leaf)
	var marks = tr.get("place", {})
	var bring := String(tr.get("bring", ""))
	if marks is Dictionary and not marks.is_empty():
		for who in marks:
			place_at(String(who), String(marks[who]))
		_open_wide = true   # and it opens on the two-shot (docs/DESIGN.md §4.5), the pair and the place
	elif bring != "" and npcs.has(bring):
		# someone walking with Mano joins him where the trigger fired (a stop on Ishita's tour): beside him, facing
		# him, under the first cut; the scene opens on the two-shot with the place behind them
		_bring(npcs[bring])
		_open_wide = true
	elif npcs.has(with_id):
		_approach(npcs[with_id])
	say(story.steps(cue), with_id)


## A conversation that starts by itself (a trigger fires 4-6 m away, or right on top of someone): Mano stands at a
## talking distance first, 1.35 m from them on his side (or the nearest free spot round them), facing them. The
## conversation's first shot is a cut, so the step never shows.
func _approach(npc: NPC) -> void:
	var to := player.global_position - npc.global_position
	to.y = 0.0
	var d := to.length()
	if d >= 1.0 and d <= 2.0:
		return
	# from where Mano came; right on top of them, in front of them (where there is room to film)
	var dir := to / d if d >= 1.0 else npc.facing_dir()
	var space := get_world_3d().direct_space_state
	var probe := PhysicsShapeQueryParameters3D.new()
	var cap := CapsuleShape3D.new()
	cap.radius = 0.3
	cap.height = 1.5
	probe.shape = cap
	probe.collision_mask = 1 | 4
	var why: Array = []
	for k in [0, 1, -1, 2, -2, 3, -3, 4, -4, 6]:
		var p: Vector3 = npc.global_position + dir.rotated(Vector3.UP, k * 0.45) * 1.35
		probe.transform = Transform3D(Basis(), p + Vector3.UP * 1.0)
		var hits := space.intersect_shape(probe, 4)
		if not hits.is_empty():
			why.append("%d: %s" % [k, hits.map(func(h): return String(h.collider.name) if h.collider else "?")])
			continue
		var ray := PhysicsRayQueryParameters3D.create(npc.global_position + Vector3.UP * 1.2, p + Vector3.UP * 1.2, 1)
		var hit := space.intersect_ray(ray)
		if not hit.is_empty():
			why.append("%d: wall %s" % [k, hit.collider.name if hit.collider else "?"])
			continue   # a wall between them
		player.teleport(Vector3(p.x, npc.global_position.y + 0.02, p.z), 0.0)
		player.face_towards(npc.global_position)
		return
	push_warning("approach %s: no free spot 1.35 m round them (%s)" % [npc.id, why])


## The follower `npc` to a free spot 1.3 m beside Mano (his right first: the follow camera's side, where they walk),
## both turned to each other. No spot free round him: they stay where they are and he faces them.
func _bring(npc: NPC) -> void:
	var me := player.global_position
	var f := Vector3(sin(player.facing_yaw()), 0, cos(player.facing_yaw()))
	var best := _free_spot_beside(me, f)
	if best != Vector3.INF:
		var to_me := me - best
		npc.apply_stage(best, atan2(to_me.x, to_me.z), {})
		npc.reset_trail()
		player.face_towards(best)
		return
	push_warning("bring %s: no free spot beside Mano" % npc.id)
	player.face_towards(npc.global_position)


## A free spot 1.3 m (or 1.0 m) beside `me`, facing `f`: his right first, then his left, then wider round him;
## clear of walls and of people (layer 4), in sight of him, on a floor at most 0.5 m above or below his.
## Vector3.INF when there is none.
func _free_spot_beside(me: Vector3, f: Vector3) -> Vector3:
	var space := get_world_3d().direct_space_state
	var probe := PhysicsShapeQueryParameters3D.new()
	var cap := CapsuleShape3D.new()
	cap.radius = 0.3
	cap.height = 1.5
	probe.shape = cap
	probe.collision_mask = 1 | 4
	var best := Vector3.INF
	var best_dy := INF
	for deg in [-90.0, 90.0, -50.0, 50.0, -130.0, 130.0, 0.0, 180.0]:
		for r in [1.3, 1.0]:
			var p: Vector3 = me + f.rotated(Vector3.UP, deg_to_rad(deg)) * r
			probe.transform = Transform3D(Basis(), p + Vector3.UP * 1.0)
			if not space.intersect_shape(probe, 1).is_empty():
				continue
			var ray := PhysicsRayQueryParameters3D.create(me + Vector3.UP * 1.2, p + Vector3.UP * 1.2, 1)
			if not space.intersect_ray(ray).is_empty():
				continue
			var down := PhysicsRayQueryParameters3D.create(p + Vector3.UP * 0.8, p + Vector3.DOWN * 1.0, 1)
			var hit := space.intersect_ray(down)
			if hit.is_empty():
				continue
			# on his own level first (in Amphi 4 a spot a tier down is among the seats below him)
			var dy := absf(hit.position.y - me.y)
			if dy < best_dy - 0.05:
				best_dy = dy
				best = Vector3(p.x, hit.position.y, p.z)
			break
		if best_dy < 0.12:
			break
	return best if best != Vector3.INF and best_dy <= 0.5 else Vector3.INF


func zone_id() -> String:
	return String(_zone.get("id", ""))


## A light change in the middle of a scene (`$ time preset`): to black, the preset, back up. A `$ lamps` given
## while the screen is still going black waits for the preset, which would otherwise undo it.
func time_cut(preset: String, fade := 0.6) -> void:
	_cut_pending = true
	var tw := hud.fade_to(1.0, fade)
	tw.tween_callback(func():
		world_env.apply_time(preset)
		_show_lights()
		_cut_pending = false
		for l in _lamps_after_cut:
			world_env.set_lamps(l[0], l[1], l[2])
		_lamps_after_cut.clear())
	tw.tween_interval(0.25)
	tw.tween_property(hud.fade, "color:a", 0.0, fade)


var _cut_pending := false
var _lamps_after_cut: Array = []


## `$ lamps group level [seconds]`.
func set_lamps(group: String, level: float, seconds := 0.0) -> void:
	if _cut_pending:
		_lamps_after_cut.append([group, level, seconds])
	else:
		world_env.set_lamps(group, level, seconds)


## The journal key: a tap opens the notebook when the key comes up; held, it shows the objective strip until
## it is let go (docs/DESIGN.md §5.5).
func _update_journal_key(dt: float) -> void:
	if _journal_hold < 0.0:
		return
	if Input.is_action_pressed("journal"):
		_journal_hold += dt
		if _journal_hold >= JOURNAL_HOLD:
			hud.peek_objective(true)
		return
	var tapped := _journal_hold < JOURNAL_HOLD
	_journal_hold = -1.0
	hud.peek_objective(false)
	if tapped:
		menus.show_journal()


func _unhandled_input(event: InputEvent) -> void:
	if mode == "sit":
		# any input stands Mano up (docs/DESIGN.md §4.1); nothing else does
		if _stand_input(event):
			get_viewport().set_input_as_handled()
			end_sit()
		return
	if mode != "play":
		return
	if event.is_action_pressed("phone"):
		get_viewport().set_input_as_handled()
		hud.hint_used("phone")
		open_phone()
		return
	if event.is_action_pressed("interact"):
		var target = player.find_interactable()
		if target:
			get_viewport().set_input_as_handled()
			interact(target)
	elif event.is_action_pressed("pause"):
		get_viewport().set_input_as_handled()
		menus.show_pause()
	elif event.is_action_pressed("journal"):
		get_viewport().set_input_as_handled()
		_journal_hold = 0.0   # _update_journal_key decides: a tap or a hold
	elif event.is_action_pressed("map"):
		get_viewport().set_input_as_handled()
		menus.show_map()
	elif event.is_action_pressed("wardrobe"):
		get_viewport().set_input_as_handled()
		menus.show_wardrobe()
	elif event.is_action_pressed("photo_mode"):
		get_viewport().set_input_as_handled()
		menus.show_photo()
	elif event is InputEventMouseButton and event.pressed and Input.mouse_mode != Input.MOUSE_MODE_CAPTURED:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func enter_menu(name: String) -> void:
	mode = name
	player.frozen = true
	camera_rig.input_enabled = false
	hud.set_hud_visible(false)
	hud.hint_used(name)   # its one-off key hint has done its job
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE


# ------------------------------------------------------------------ interaction and conversations
func interact(it: Interactable) -> void:
	if it.kind == "sit":
		begin_sit(it.id)
		return
	if it.kind == "npc":
		var lines: Array = story.talk(it.id)
		_step_back_from(it.npc)
		talk_to(it, lines)
		return
	# a look-at made only of Mano's thoughts (V2-10) is a bark: he keeps walking while it shows; a readable with an
	# insert stops him to read it
	var cue := story.use_cue(it.id)
	var ins = WorldData.section("spots").get(it.id, {}).get("insert")
	if DialogueData.is_think_only(cue) and not ins is Dictionary:
		var now := Time.get_ticks_msec() / 1000.0
		if cue == _bark_cue and now < _bark_until:
			return
		var lines := story.bark_cue(cue)
		var secs := 0.0
		# what Mano chose to look at comes first: a passing thought showing or waiting goes (think_amphi's Dijkstra
		# line would otherwise hold the slide's own thought back until the next spot)
		dialogue.clear_barks()
		for l in lines:
			secs += dialogue.bark(l[0], l[1])
		_bark_cue = cue
		_bark_until = now + secs
		return
	player.face_towards(it.pos)
	if ins is Dictionary:
		_insert(it, ins)
	say(story.use(it.id))


## A readable (a world.json spot of kind "read" with an `insert`: V2-28, docs/DESIGN.md §4.7): a 20° insert on what is
## read, from just beside Mano's eyes, with the near depth of field, while his note on it shows; the dialogue's end
## hands the camera back.
func _insert(it: Interactable, ins: Dictionary) -> void:
	var look := WorldData.vec(ins.get("look", [it.pos.x, it.pos.y + 1.4, it.pos.z]))
	var head := player.rig.head_position() if player.rig else player.global_position + Vector3.UP * 1.6
	var from := WorldData.vec(ins.from) if ins.has("from") else head + (look - head).normalized() * 0.3 + Vector3.UP * 0.04
	from = _unblock(look, from)
	player.face_towards(look)
	_hold_shot = true
	hud.set_letterbox(true)
	camera_rig.set_shot(from, look, float(ins.get("fov", 20.0)), from.distance_to(look), true, "insert")
	print("[look] insert %s: from %s at %s" % [it.id, from.snapped(Vector3.ONE * 0.01), look])


## E pressed right on top of someone standing (a player walks into people, and from 0.76 m a choice is filmed on
## the back of the other's head): Mano steps back to a talking distance on his own side, under the conversation's
## first cut. Left alone: someone seated or on another level, and a spot behind Mano that is not free.
func _step_back_from(npc: NPC) -> void:
	if npc == null or npc.swivel_chair != null or (npc.rig and npc.rig.sitting):
		return
	var to := player.global_position - npc.global_position
	if absf(to.y) > 0.3:
		return
	to.y = 0.0
	var d := to.length()
	if d >= 1.05 or d < 0.05:
		return
	var p := npc.global_position + to / d * 1.25
	p.y = player.global_position.y
	var probe := PhysicsShapeQueryParameters3D.new()
	var cap := CapsuleShape3D.new()
	cap.radius = 0.3
	cap.height = 1.5
	probe.shape = cap
	probe.collision_mask = 1 | 4   # walls and standing people (Mano himself is on layer 2)
	probe.transform = Transform3D(Basis(), p + Vector3.UP * 1.0)
	if get_world_3d().direct_space_state.intersect_shape(probe, 1).is_empty():
		player.teleport(p, player.facing_yaw())


func talk_to(it: Interactable, lines: Array) -> void:
	var npc: NPC = it.npc
	mode = "dialogue"
	player.frozen = true
	camera_rig.input_enabled = false
	if npc.swivel_chair:
		_step_to_aisle(npc)
	player.face_towards(npc.global_position)
	npc.start_talk()
	# Mano listens in his plain idle: his conversing clip (talk_idle) opens with both arms wide and later reaches
	# out, across the friend's face in the over-the-shoulder shots (Anisha's sincere beat, the arrival at SM14); his
	# own lines still gesture (_on_line). Photo mode's "talking" pose keeps talk_idle (restored at the end).
	player.rig.set_talk_clip("idle")
	player.rig.set_conversing(true)
	_conv = {"npc": npc, "side": _pick_side(npc)}
	# a staged scene, or someone swivelling round on a desk chair (their face is still on its way round when the first
	# line starts, behind Mano from over his shoulder): the conversation opens on the two-shot
	if _open_wide or npc.swivel_chair != null:
		_conv["open_wide"] = true
		_open_wide = false
	hud.set_letterbox(true)
	hud.set_hud_visible(false)
	Sfx.duck_music(true)
	_shot_for("nar", false)
	dialogue.say(lines)


## Talking to someone at a desk from across it would leave their monitor between the camera and
## their face: Mano steps round to the aisle beside their chair (the conversation's first cut hides it).
func _step_to_aisle(npc: NPC) -> void:
	var f := Vector3(sin(npc._home_yaw), 0, cos(npc._home_yaw))
	var seat := npc.swivel_chair.global_position
	var to := player.global_position - seat
	to.y = 0
	if f.dot(to) < 0.0:
		return   # already on the chair side
	var space := get_world_3d().direct_space_state
	var probe := PhysicsShapeQueryParameters3D.new()
	var cap := CapsuleShape3D.new()
	cap.radius = 0.3
	cap.height = 1.6
	probe.shape = cap
	probe.collision_mask = 1 | 4 | LevelBinder.CAMERA_OCCLUDERS   # walls, people and the neighbours' chairs
	var side := Vector3(-f.z, 0, f.x)
	for s: float in [1.0, -1.0, 0.0]:
		var p := seat - f * 0.95 + side * s * 0.55
		probe.transform = Transform3D(Basis(), p + Vector3.UP * 0.95)
		if space.intersect_shape(probe, 1).is_empty():
			player.teleport(Vector3(p.x, player.global_position.y, p.z), player.facing_yaw())
			return


## Run dialogue; with `with_npc` it becomes a conversation with that NPC (camera + letterbox).
func say(lines: Array, with_npc := "") -> void:
	if with_npc != "" and npcs.has(with_npc):
		talk_to(npcs[with_npc].interact, lines)
		return
	mode = "dialogue"
	player.frozen = true
	camera_rig.input_enabled = false
	hud.set_hud_visible(false)
	dialogue.say(lines)


func _speaker_info(who: String) -> Dictionary:
	if CastDefs.SPEAKERS.has(who):
		return CastDefs.SPEAKERS[who]
	if npcs.has(who):
		return {"name": npcs[who].display_name, "color": npcs[who].color}
	if who.begins_with("crowd"):
		return {"name": "Student", "color": Color("#c9d1d9")}
	return {"name": who.capitalize(), "color": Color("#c9d1d9")}


func _rig_of(who: String) -> CharacterRig:
	if who == "mano":
		return player.rig
	# Mme Dupont's lines say "madame" at both of her spots: the one in the conversation (madame2 at the accueil) talks
	if not _conv.is_empty() and _conv.npc.id != who and VoiceLines.speaker_of(_conv.npc.id) == VoiceLines.speaker_of(who):
		return _conv.npc.rig
	if npcs.has(who):
		return npcs[who].rig
	if not _conv.is_empty() and who.begins_with("crowd"):
		return _conv.npc.rig
	return null


func _on_line(who: String, text: String, expr: String) -> void:
	# lip flap and expression on the speaker; everyone in the scene looks at the speaker
	if _speaker_rig:
		_speaker_rig.talking = false
	# Mano's thoughts (`think`) are framed on him, with his expression, and his lips do not move
	var thought := who == "think"
	if thought:
		who = "mano"
	var last_rig := _speaker_rig
	_speaker_rig = _rig_of(who)
	# whoever spoke last lowers their hands when someone else starts: a talk gesture still playing reached across the
	# next over-the-shoulder shot (Mano's sleeve over Ishita's face at the tour's photo question)
	if last_rig and last_rig != _speaker_rig and last_rig.tree:
		last_rig.tree.set("parameters/gesture/request", AnimationNodeOneShot.ONE_SHOT_REQUEST_FADE_OUT)
	var e := expr if expr != "" else _guess_expression(text)
	if _speaker_rig:
		# someone asleep who says a line with a written expression has woken up (the SUP in Amphi 4)
		if expr != "" and expr != "tired" and _speaker_rig.eyes_closed > 0.5 and not thought:
			_speaker_rig.eyes_closed = 0.0
		_speaker_rig.talking = who != "nar" and not thought
		_speaker_rig.lip_sync(dialogue.voice.get("env", PackedFloat32Array()), dialogue.voice_player)
		_speaker_rig.set_expression(e)
		if randf() < 0.35 and _speaker_rig.has_clip("talk_1") and not _speaker_rig.sitting and not thought:
			_speaker_rig.play_gesture(["talk_1", "talk_2"][randi() % 2] if _speaker_rig.has_clip("talk_2") else "talk_1")
	if not _conv.is_empty():
		var npc: NPC = _conv.npc
		# the one Mano talks with listens in their plain idle, as Mano does (talk_to): the conversing idle opens both
		# arms wide and reaches out, into the lens of Mano's over-the-shoulder shots (Ian's hand over Mano's face at
		# the summit's counter); on their own lines it is back
		if npc.rig and not npc.rig.sitting:
			npc.rig.set_talk_clip("idle" if who == "mano" else "talk_idle")
		if who == "mano":
			npc.rig.look_at_point = player.rig.head_position()
			player.rig.look_at_point = npc.rig.head_position()
		elif _speaker_rig:
			player.rig.look_at_point = _speaker_rig.head_position()
		if _hold_shot and (who == "nar" or thought):
			return
		_hold_shot = false
		# a staged scene's first line: the opening two-shot, both faces in profile and the place behind them (the
		# speaker's over-the-shoulder shot could not see past Mano's conversing idle, whose arms open wide as it
		# starts: every arrival at SM14 opened on his back)
		if _conv.get("open_wide", false):
			_conv.erase("open_wide")
			_shot_for("nar", true)
			return
		_shot_for(who, true)


static func _guess_expression(text: String) -> String:
	if text.contains("?!") or text.contains("WHAT") or text.contains("WHERE"):
		return "shock"
	if text.contains("haha") or text.contains("HAHA") or text.contains("lol") or text.contains("legend"):
		return "grin"
	if text.ends_with("!"):
		return "smile"
	if text.begins_with("..."):
		return "neutral"
	return "neutral"


var _hold_shot := false
var _open_wide := false   # the next conversation opens on the two-shot (a staged trigger, main.play_trigger)


## The ending gag: the new AirPod falls out; film it from the floor while it bounces. `grate` (the post-credits): a
## drain grate lies where it lands, it slips through the bars after its first bounce, and the song cuts out.
func drop_airpod(grate := false) -> void:
	var body := player.drop_airpod()
	Sfx.play("plink")
	if body == null:
		return
	_hold_shot = true
	var fwd := Vector3(sin(player.facing_yaw()), 0, cos(player.facing_yaw()))
	var right := Vector3(-fwd.z, 0, fwd.x) * -1.0
	var land := player.global_position - fwd * 0.5 + right * 0.2 + Vector3.UP * 0.04
	if grate:
		_drain_grate(Vector3(land.x, player.global_position.y + 0.006, land.z), player.facing_yaw())
		var b := body
		get_tree().create_timer(0.42).timeout.connect(func():
			if is_instance_valid(b):
				b.collision_mask = 0   # through the bars
				b.linear_velocity = Vector3(0, -0.6, 0)
				b.angular_velocity *= 0.3)
		if _score != "" or Sfx.music_now() != "":
			Sfx.music("", -60.0, 0.05, 0.12)   # the song stops mid-phrase at the plink
			_score = ""
	# low shot from the open side behind Mano, looking back at the floor near his feet; over a drain grate, from
	# above it (a grazing shot put the lens among the bars), the pavement and his shoes round it
	var from := land - fwd * 0.95 + right * 0.55 + Vector3.UP * 0.16
	if grate:
		from = land + Vector3.UP * 0.8 - fwd * 0.35 + right * 0.3
	from = _unblock(land + Vector3.UP * 0.05, from)
	camera_rig.set_shot(from, land, 38.0 if grate else 34.0, from.distance_to(land), true)
	var t := 0.0
	while t < 2.2 and is_instance_valid(body) and _hold_shot:
		await get_tree().process_frame
		if not _hold_shot or not is_instance_valid(body):
			break   # the next line already cut away
		t += get_process_delta_time()
		var at := body.global_position
		if at.y < land.y - 0.3:   # safety: never chase it under the floor
			break
		camera_rig.set_shot(from, at.lerp(land, 0.65 if grate else 0.3), 38.0 if grate else 34.0, from.distance_to(at), true)


## A drain grate on the pavement (the post-credits): a dark slot and a row of iron bars, no texture, no collision.
func _drain_grate(at: Vector3, yaw: float) -> void:
	var root := Node3D.new()
	root.name = "DrainGrate"
	add_child(root)
	root.global_position = at
	root.rotation.y = yaw
	var hole := MeshInstance3D.new()
	var hm := BoxMesh.new()
	hm.size = Vector3(0.42, 0.004, 0.26)
	hole.mesh = hm
	var dark := StandardMaterial3D.new()
	dark.albedo_color = Color(0.02, 0.02, 0.02)
	dark.roughness = 1.0
	hole.material_override = dark
	root.add_child(hole)
	var iron := StandardMaterial3D.new()
	iron.albedo_color = Color(0.16, 0.15, 0.14)
	iron.metallic = 0.6
	iron.roughness = 0.55
	for i in 8:
		var bar := MeshInstance3D.new()
		var bm := BoxMesh.new()
		bm.size = Vector3(0.022, 0.012, 0.26)
		bar.mesh = bm
		bar.material_override = iron
		bar.position = Vector3(-0.19 + i * 0.054, 0.005, 0.0)
		root.add_child(bar)
	var frame := MeshInstance3D.new()
	var fm := BoxMesh.new()
	fm.size = Vector3(0.46, 0.01, 0.03)
	frame.mesh = fm
	frame.material_override = iron
	for z in [-0.14, 0.14]:
		var f := frame.duplicate() as MeshInstance3D
		f.position = Vector3(0, 0.004, z)
		root.add_child(f)
	for c in root.get_children():
		(c as GeometryInstance3D).cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	# the street lamp's pool on it: at 00:25 the pavement is too dark for the low shot of the *plink* (one small
	# unshadowed light, gone with the grate)
	var pool := OmniLight3D.new()
	pool.light_color = Color("#ffcf8a")
	pool.light_energy = 1.4
	pool.omni_range = 2.2
	pool.shadow_enabled = false
	pool.position = Vector3(0.3, 1.3, -0.2)
	root.add_child(pool)


func _pick_side(npc: NPC) -> int:
	# keep the camera on one side of the line of action (180° rule): the side with more room
	var m := player.rig.head_position()
	var n := npc.rig.head_position()
	var d := (n - m)
	d.y = 0
	d = d.normalized()
	var side := Vector3(-d.z, 0, d.x)
	var space := get_world_3d().direct_space_state
	var best := 1
	var best_room := -1.0
	for s in [1, -1]:
		var mid := (m + n) * 0.5
		var q := PhysicsRayQueryParameters3D.create(mid, mid + side * s * 2.6, 1)
		var hit := space.intersect_ray(q)
		var room := 2.6 if hit.is_empty() else mid.distance_to(hit.position)
		if room > best_room + 0.2:
			best_room = room
			best = s
	return best


## Conversation coverage: the speaker is framed from the candidate angle that sees their face best,
## over the listener's shoulder when that is clear, otherwise wider angles around the speaker
## (a seated student at a PC, a friend standing behind Mano). Views blocked by the level or by
## another character's head are rejected, and the camera stays on one side of the line of action.
func _shot_for(who: String, cut: bool) -> void:
	if _conv.is_empty():
		return
	var npc: NPC = _conv.npc
	var same := npc.id == who or VoiceLines.speaker_of(npc.id) == VoiceLines.speaker_of(who)   # Mme Dupont: madame2 says "madame"
	var group := String(Chapters.info().get("group_shot", ""))
	var gsh: Dictionary = WorldData.section("shots").get(group, {}) if group != "" else {}
	# a second character joining in (Silvia next to Ian, Karim across the babyfoot table) gets the shot when they
	# speak, up to 7 m away (docs/DESIGN.md §4.5)
	if same:
		pass
	elif npcs.has(who) and npcs[who] != npc and npcs[who].visible and npcs[who].global_position.distance_to(npc.global_position) < 7.0:
		npc = npcs[who]
	elif npcs.has(who) and npcs[who] != npc and not gsh.is_empty() \
			and player.global_position.distance_to(WorldData.vec(gsh.get("look", [0, 0, 0]))) < 14.0:
		# someone further off (or not in the shot's reach) speaks up where the chapter's group shot is: that wide shot
		# (docs/DESIGN.md §4.5, the finale on the steps: chapters.json group_shot)
		camera_shot(group)
		_hold_shot = false
		return
	var m := player.rig.head_position() - Vector3.UP * 0.04
	var n := _end_of_turn(npc, npc.rig.head_position() - Vector3.UP * 0.04)
	if who == "nar":
		var d := n - m
		d.y = 0
		var side := Vector3(-d.z, 0, d.x).normalized() * float(_conv.side)
		var mid := (m + n) * 0.5
		var wide := mid + side * maxf(2.0, d.length() * 1.4) - d.normalized() * 0.3 + Vector3.UP * 0.12
		wide = _unblock(mid, wide)
		if OS.is_debug_build():
			print("[shot] two-shot: from %s at %s" % [wide.snapped(Vector3.ONE * 0.01), mid.snapped(Vector3.ONE * 0.01)])
		camera_rig.set_shot(wide, mid, 34.0, wide.distance_to(mid), cut)
		return
	var speaker: CharacterRig = player.rig if who == "mano" else npc.rig
	var face := m if who == "mano" else n
	var listener := n if who == "mano" else m
	var axis := face - listener
	axis.y = 0
	axis = axis.normalized()
	var line_side := Vector3(-axis.z, 0, axis.x) * float(_conv.side)
	var yaw: float = player.facing_yaw()
	var facing := Vector3(sin(yaw), 0, cos(yaw)) if who == "mano" else npc.facing_dir()
	var cands: Array = []   # [camera position, bonus]
	for sd in [1.0, -1.0]:
		cands.append([listener - axis * 1.05 + line_side * sd * 0.52 + Vector3.UP * 0.08, 0.8])   # classic over-the-shoulder
		cands.append([listener - axis * 1.45 + line_side * sd * 0.85 + Vector3.UP * 0.1, 0.5])
	for deg in [0.0, 30.0, -30.0, 55.0, -55.0, 80.0, -80.0]:
		for r in [1.35, 1.8]:
			cands.append([face + facing.rotated(Vector3.UP, deg_to_rad(deg)) * r + Vector3.UP * 0.06, 0.0])
	var best: Vector3 = cands[0][0]
	var best_score := -INF
	for c in cands:
		var from: Vector3 = c[0]
		var score: float = c[1] + _view_score(from, face, facing, speaker)
		if (from - listener).dot(line_side) >= 0.0:
			score += 0.6   # 180° rule: stay on the side the conversation started on
		if score > best_score:
			best_score = score
			best = from
	if OS.is_debug_build():
		print("[shot] %s: from %s at %s (score %.2f; Mano's head %s, listener %s)" % [who, best.snapped(Vector3.ONE * 0.01), face.snapped(Vector3.ONE * 0.01),
			best_score, player.rig.head_position().snapped(Vector3.ONE * 0.01), listener.snapped(Vector3.ONE * 0.01)])
	camera_rig.set_shot(best, face, 30.0, best.distance_to(face), cut)


## A seated character still swivelling round to Mano: where their head will be once the chair has turned. Their
## facing is already the end of the turn (NPC.facing_dir); the head is not, so without this the first shot of a
## conversation is framed on where the face is mid-turn, and the face ends up behind Mano's back.
func _end_of_turn(npc: NPC, head: Vector3) -> Vector3:
	if npc.swivel_chair == null or npc.rig == null:
		return head
	var f := npc.facing_dir()
	var left := angle_difference(npc.rig.rotation.y, atan2(f.x, f.z))
	if absf(left) < 0.05:
		return head
	var pivot: Vector3 = npc.swivel_chair.global_position
	pivot.y = head.y
	return pivot + (head - pivot).rotated(Vector3.UP, left)


## How well a camera at `from` shows the face at `face`: frontal is good; walls, props and
## other characters' heads in the way are not.
func _view_score(from: Vector3, face: Vector3, facing: Vector3, speaker: CharacterRig) -> float:
	var space := get_world_3d().direct_space_state
	var probe := PhysicsShapeQueryParameters3D.new()
	var ball := SphereShape3D.new()
	ball.radius = 0.14
	probe.shape = ball
	probe.transform = Transform3D(Basis(), from)
	probe.collision_mask = 1 | LevelBinder.CAMERA_OCCLUDERS
	if not space.intersect_shape(probe, 1).is_empty():
		return -100.0   # inside a wall or a prop
	var ray := PhysicsRayQueryParameters3D.create(face, from, 1 | LevelBinder.CAMERA_OCCLUDERS)
	if not space.intersect_ray(ray).is_empty():
		return -50.0
	var to_cam := from - face
	to_cam.y = 0
	var frontal := facing.dot(to_cam.normalized())
	var score := frontal * 3.0
	if frontal < -0.2:
		score -= 4.0   # the back of their head
	# other bodies between the lens and the face (the last 25 cm is the speaker's own head)
	var seg := face - from
	var seg_len := seg.length()
	var others: Array = [player.rig]
	for k in npcs:
		others.append(npcs[k].rig)
	for c in crowd:
		others.append(c.rig)
	for r in others:
		if r == speaker or r == null or not r.is_visible_in_tree():
			continue
		var h: Vector3 = r.head_position()
		if h.distance_to(face) > 4.5:
			continue
		# the lens within someone's reach: their hand or sleeve fills the frame (the camera 0.35 m from Cristina for
		# c4.kebab_done's first line, a hand over Mano's face in two runs out of three). An over-the-shoulder
		# camera is 1.2 m or more from its listener, so this only moves it away from bystanders
		var reach := Vector2(from.x - r.global_position.x, from.z - r.global_position.z).length()
		if reach < 0.6 and absf(from.y - h.y) < 1.0:
			score -= 4.0
		elif reach < 0.8 and absf(from.y - h.y) < 1.0:
			score -= 1.0
		# the head, the neck, the chest and, tighter, the shoulders (V2-21: a shorter model must not be hidden whole
		# behind his head and shoulder; a shoulder at the edge of the frame is fine, over a face it is not)
		var across: Vector3 = r.global_transform.basis.x.normalized() * 0.19
		# and the torso: a seated speaker's face is filmed at a standing listener's chest height
		for p: Array in [[h - Vector3.UP * 0.06, 0.2, 0.32], [h - Vector3.UP * 0.2, 0.2, 0.32], [h - Vector3.UP * 0.4, 0.2, 0.32],
				[h - Vector3.UP * 0.32 + across, 0.1, 0.16], [h - Vector3.UP * 0.32 - across, 0.1, 0.16],
				[h - Vector3.UP * 0.62, 0.22, 0.32]]:
			var pt: Vector3 = p[0]
			var t := clampf((pt - from).dot(seg) / (seg_len * seg_len), 0.0, 1.0)
			if t * seg_len > seg_len - 0.25:
				continue
			var miss := pt.distance_to(from + seg * t)
			if miss < p[1]:
				score -= 4.0
			elif miss < p[2]:
				score -= 1.0
	return score


func _unblock(look: Vector3, from: Vector3) -> Vector3:
	var space := get_world_3d().direct_space_state
	var q := PhysicsRayQueryParameters3D.create(look, from, 1)
	var hit := space.intersect_ray(q)
	if hit.is_empty():
		return from
	return look.lerp(hit.position, 0.85)


## Characters whose `when` condition changed with the story appear or disappear, and go where the chapter's
## staging puts them now.
func _refresh_presence() -> void:
	for id in npcs:
		restage(id)
	_show_notes()
	_show_lights()


func _on_dialogue_finished() -> void:
	_refresh_presence()
	if _speaker_rig:
		_speaker_rig.talking = false
		_speaker_rig.set_expression("neutral")
		_speaker_rig = null
	if not _conv.is_empty():
		_conv.npc.end_talk()
		_conv.npc.rig.set_expression("neutral")
		_conv.npc.rig.set_talk_clip("talk_idle")
		_conv = {}
	player.rig.look_at_point = null
	player.rig.set_conversing(false)
	player.rig.set_talk_clip("talk_idle")
	if minigame != null or mode in ["ending", "title", "credits"]:
		story.run_after()
		return
	# `$ say` and `$ chapter` waited for the end of the conversation: they take over from here
	if story.has_after():
		save()
		story.run_after()
		return
	camera_rig.clear_shot()
	resume()
	save()


# ------------------------------------------------------------------ sit-downs (V2-14, docs/DESIGN.md §4.1)
const SIT_FADE := 0.3         # to black and back as Mano sits down (he is set on the seat under it)
const SIT_HOLD_A := 6.0       # seconds on cam A, the 3/4 medium, before the wide
const SIT_BLEND := 0.125      # the blend to cam B, the wide: 8 s
const SIT_THOUGHT := 2.5      # the thought comes up this far in
const SIT_C_AT := 22.0        # the detail (cam C) cuts in this far in, for SIT_C_FOR, if the sit has one
const SIT_C_FOR := 4.0
const SIT_GUARD := 0.8        # input this soon after sitting does not count (the key that sat him down)
const SIT_SONG_DB := -8.0
const SIT_MOVE := {"orbit": 2.0}   # after the wide's blend: 2°/s round his head unless the sit says otherwise
const SIT_CLEAR := 1.8        # strangers (the crowd) seated this close to the seat go while he sits, back when he stands
const SIT_LINE := 0.45        # anyone whose body is this close to a sit camera's line to the seat goes under the dip too


func is_sitting() -> bool:
	return mode == "sit"


## A sit-down's prompt shows when its chapter is on, its condition holds and the clock is in its window.
func sit_available(id: String) -> bool:
	if mode != "play":
		return false
	var s := WorldData.sit(id)
	if s.is_empty() or int(s.chapter) != Chapters.current():
		return false
	if String(s.when) != "" and not Conditions.eval(String(s.when)):
		return false
	var c: Array = s.clock
	if c.size() == 2:
		var now := Chapters.clock()
		if now < Conditions.minutes(String(c[0])) or now > Conditions.minutes(String(c[1])):
			return false
	return true


## Mano sits down at a sit-down (data/world.json "sits"): under a short dip to black he is on the seat, the HUD
## goes, the letterbox comes in, cam A holds 6 s and blends over 8 s to the wide (cam B), which then orbits slowly;
## the song rises from where it was last left and the room goes 6 dB quieter; his thought (sit.<id>) comes up at
## 2.5 s. Any input stands him up (end_sit). The first time, a moment goes into the journal (flags.moments).
func begin_sit(id: String) -> void:
	var s := WorldData.sit(id)
	if s.is_empty() or not s.cams.has("a") or not s.cams.has("b"):
		push_warning("sit: no sit-down '%s' with cams a and b in data/world.json" % id)
		if mode != "play":
			resume()
		return
	print("[sit] %s: sits at %s, song %s from %.1f s, clock %s" % [id, s.pos, _sit_song(s), Sfx.position_of(_sit_song(s)), Chapters.clock_text()])
	_sit = {"id": id, "s": s, "t": 0.0, "phase": "fade", "from": player.global_position, "from_yaw": player.facing_yaw(),
		"thought": false, "saved": {}}
	mode = "sit"
	player.frozen = true
	player.interact_target = null
	camera_rig.input_enabled = false
	hud.set_hud_visible(false)
	hud.set_prompt(null)
	hud.set_letterbox(true)
	dialogue.clear_barks()
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	var tw := hud.fade_to(1.0, SIT_FADE)
	tw.tween_callback(func():
		if mode != "sit":
			return
		player.set_physics_process(false)
		player.teleport(s.pos, s.yaw)
		player.rig.sitting = true
		player.rig.set_sit_clip("sit_idle")
		player.rig.look_at_point = null
		# a stranger at his shoulder on the same sofa (KB1's round sofa) would share the moment: they go under the dip
		var gone: Array = []
		for c in crowd:
			if c.visible and Vector2(c.global_position.x - s.pos.x, c.global_position.z - s.pos.z).length() < SIT_CLEAR:
				c.visible = false
				gone.append(c)
		# whoever follows him (Ishita on her tour) steps out of the moment, and anyone else standing between a sit
		# camera and the seat goes under the dip too: characters are not camera occluders, and a follower standing
		# by the seat would fill cam A with their back
		var stepped: Array = []
		for nid in npcs:
			var n: NPC = npcs[nid]
			if n.visible and (n.following or _blocks_sit_cams(n.rig, s)):
				n.set_present(false)
				stepped.append(nid)
		for c in crowd:
			if c.visible and _blocks_sit_cams(c.rig, s):
				c.visible = false
				gone.append(c)
		if not stepped.is_empty() or not gone.is_empty():
			print("[sit] %s: out of the shots under the dip: %s, %d strangers" % [id, stepped, gone.size()])
		_sit["gone"] = gone
		_sit["stepped"] = stepped
		_sit_shot("a", true)
		camera_rig.set_motion(_sit_drift(s, 0.03))
		_sit.phase = "a"
		_sit.t = 0.0)
	tw.tween_property(hud.fade, "color:a", 0.0, 0.7)
	Sfx.song(_sit_song(s), SIT_SONG_DB, 3.5, 3.0)
	Sfx.duck_ambience(-6.0, 3.0)
	var ms: Array = GameState.flags.get("moments", [])
	if not id in ms:
		ms = ms.duplicate()
		ms.append(id)
		GameState.flags["moments"] = ms
		_sit["first"] = true


## A character's body near one of a sit's camera lines (cams a, b, c to the point they look at), short of the
## seat itself: they would stand between the lens and Mano.
func _blocks_sit_cams(r: CharacterRig, s: Dictionary) -> bool:
	if r == null:
		return false
	var h: Vector3 = r.head_position()
	var body: Array = [h, h - Vector3.UP * 0.45, h - Vector3.UP * 0.9]
	for k in s.cams:
		var c: Dictionary = s.cams[k]
		var a: Vector3 = c.from
		var b: Vector3 = c.look
		var seg := b - a
		var l2 := seg.length_squared()
		if l2 < 0.01:
			continue
		for p: Vector3 in body:
			var t := clampf((p - a).dot(seg) / l2, 0.0, 1.0)
			if t * sqrt(l2) > sqrt(l2) - 0.4:
				continue   # at the seat: beside Mano, not in front of the lens
			if p.distance_to(a + seg * t) < SIT_LINE:
				return true
	return false


## The song a sit-down plays: its stem, or the stem a flag names ("@playlist": the finale's pick).
func _sit_song(s: Dictionary) -> String:
	var m := String(s.get("music", ""))
	if m.begins_with("@"):
		m = String(GameState.flags.get(m.substr(1), ""))
	return m if m != "" else "ending"


func _sit_shot(key: String, cut: bool, blend := CameraRig.BLEND) -> void:
	var c: Dictionary = _sit.s.cams[key]
	var look: Vector3 = c.look
	var from := _unblock(look, c.from)
	camera_rig.set_shot(from, look, float(c.fov), from.distance_to(_sit.s.pos + Vector3.UP * 0.95), cut, "sit", blend)


## A slow creep on cam A: `speed` m/s toward the seat, so the medium breathes before the wide.
func _sit_drift(s: Dictionary, speed: float) -> Vector3:
	var a: Dictionary = s.cams.a
	var d: Vector3 = (a.look - a.from)
	d.y = 0.0
	return d.normalized() * speed if d.length() > 0.01 else Vector3.ZERO


func _update_sit(dt: float) -> void:
	if _sit.is_empty() or _sit.phase == "fade":
		return
	_sit.t += dt
	var t: float = _sit.t
	var s: Dictionary = _sit.s
	if not _sit.thought and t >= SIT_THOUGHT:
		_sit.thought = true
		if story.has_cue(String(s.cue)):
			for l in story.bark_cue(String(s.cue)):
				dialogue.bark(l[0], l[1], 6.0)
	match String(_sit.phase):
		"a":
			if t >= SIT_HOLD_A:
				_sit_shot("b", false, SIT_BLEND)
				_sit.phase = "b"
		"b":
			if t >= SIT_HOLD_A + 1.0 / SIT_BLEND:
				_sit_move()
				_sit.phase = "move"
		"move", "move2":
			_sit_guard(dt)
			if String(_sit.phase) == "move" and s.cams.has("c") and t >= SIT_C_AT and t < SIT_C_AT + 1.0:
				_sit.saved = camera_rig.shot_now()
				_sit_shot("c", true)
				_sit.phase = "c"
		"c":
			if t >= SIT_C_AT + SIT_C_FOR:
				var b: Dictionary = _sit.saved
				if not b.is_empty():
					camera_rig.set_shot(b.from, b.look, b.fov, b.focus, true, "sit")
				_sit_move()
				_sit.phase = "move2"


## The wide's slow move stops before the camera reaches a wall or a prop (a 0.35 m sphere there, or the view to his
## head cut), five times a second.
func _sit_guard(dt: float) -> void:
	_sit["guard_t"] = float(_sit.get("guard_t", 0.0)) - dt
	if float(_sit.guard_t) > 0.0:
		return
	_sit.guard_t = 0.2
	var now := camera_rig.shot_now()
	if now.is_empty():
		return
	var space := get_world_3d().direct_space_state
	var probe := PhysicsShapeQueryParameters3D.new()
	var ball := SphereShape3D.new()
	ball.radius = 0.35
	probe.shape = ball
	probe.collision_mask = 1 | LevelBinder.CAMERA_OCCLUDERS
	probe.transform = Transform3D(Basis(), now.from)
	var ray := PhysicsRayQueryParameters3D.create(_sit.s.pos + Vector3.UP * 1.0, now.from, 1 | LevelBinder.CAMERA_OCCLUDERS)
	if not space.intersect_shape(probe, 1).is_empty() or not space.intersect_ray(ray).is_empty():
		camera_rig.set_motion()


## The wide's slow move: an orbit round his head (°/s), or a creep (m/s), from the sit's "move" or SIT_MOVE.
func _sit_move() -> void:
	var mv: Dictionary = _sit.s.get("move", {})
	if mv.is_empty():
		mv = SIT_MOVE
	if mv.has("drift"):
		camera_rig.set_motion(WorldData.vec(mv.drift))
	else:
		camera_rig.set_motion(Vector3.ZERO, float(mv.get("orbit", 2.0)), _sit.s.pos + Vector3.UP * 0.95)


## What counts as "any input" for standing up: a key, a button, a click, a stick pushed (not the mouse moving).
func _stand_input(event: InputEvent) -> bool:
	if event.is_echo():
		return false
	if event is InputEventKey or event is InputEventMouseButton or event is InputEventJoypadButton:
		return event.is_pressed()
	if event is InputEventJoypadMotion:
		return absf(event.axis_value) > 0.6
	return false


## Mano stands up (any input in a sit-down): at once he is playable again, on his feet where he sat down from (or
## the sit's `stand`), behind a quick dip; the song fades over 3 s and the room comes back over 2 s. When the story
## sat him down (`$ sit`) and something waits for its end (`$ chapter`), that takes over instead.
func end_sit() -> void:
	if mode != "sit" or _sit.is_empty() or (_sit.phase == "fade") or float(_sit.t) < SIT_GUARD:
		return
	var t_in := Time.get_ticks_msec() / 1000.0
	var s: Dictionary = _sit.s
	var id := String(_sit.id)
	var first := bool(_sit.get("first", false))
	var stand: Vector3 = s.stand if s.stand != Vector3.INF else _sit.from
	for c in _sit.get("gone", []):
		if is_instance_valid(c):
			c.visible = true
	var stepped: Array = _sit.get("stepped", [])
	_sit = {}
	player.rig.sitting = false
	player.set_physics_process(true)
	player.teleport(stand, s.yaw if s.stand != Vector3.INF else player.facing_yaw())
	# those who stepped out come back under the stand's dip; a follower beside him, on a free spot (not inside Toma
	# at the foot of the steps)
	for nid in stepped:
		restage(nid)
		var n: NPC = npcs.get(nid)
		if n and n.following and n.visible:
			var f := Vector3(sin(player.facing_yaw()), 0, cos(player.facing_yaw()))
			var p := _free_spot_beside(player.global_position, f)
			if p != Vector3.INF:
				var to_me := player.global_position - p
				n.apply_stage(p, atan2(to_me.x, to_me.z), {})
			n.reset_trail()
	camera_rig.clear_shot(true)
	camera_rig.snap_behind(player.facing_yaw())
	dialogue.clear_barks()
	Sfx.duck_ambience(0.0, 2.0)
	var m: Array = place_music()
	Sfx.music(m[0], m[1], 2.5, 3.0)
	if story.has_after():
		# the story sat him down and something waits (`$ chapter`): its own fade takes over, no dip of ours under it
		mode = "cutscene"
		story.run_after()
	else:
		hud.fade.color.a = 0.9
		hud.fade_to(0.0, 0.35)
		resume()
	sit_stood = {"id": id, "after": Time.get_ticks_msec() / 1000.0 - t_in, "mode": mode, "sitting": player.rig.sitting}
	print("[sit] %s: stood up, mode %s, %.3f s after the input" % [id, mode, sit_stood.after])
	if first and mode == "play":
		# non-breaking spaces: "1 of 6" stays on one line (the toast wrapped a lone "6")
		toast("A moment. %d\u00a0of\u00a0%d" % [GameState.flags.get("moments", []).size(), WorldData.sit_ids().size()], "heart")
		# all six (V2-30): one more thought, once (dialogue/sits.dlg sit.all), and a line in the journal
		if GameState.flags.get("moments", []).size() >= WorldData.sit_ids().size() and not bool(GameState.flags.get("moments_all", false)):
			GameState.flags["moments_all"] = true
			for l in story.bark_cue("sit.all"):
				dialogue.bark(String(l[0]), String(l[1]))


# ------------------------------------------------------------------ minigames
func start_minigame(name: String, opts: Dictionary, cb: Callable) -> void:
	var script_path := "res://scripts/minigames/%s.gd" % name
	if not ResourceLoader.exists(script_path):
		cb.call(true)
		return
	mode = "minigame"
	player.frozen = true
	camera_rig.input_enabled = false
	hud.set_hud_visible(false)
	hud.set_letterbox(false)
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	if opts.has("sit_at") and binder.anchors.has(opts.sit_at):
		var a: Dictionary = binder.anchors[opts.sit_at]
		player.teleport(a.pos, a.yaw)
		player.rig.sitting = true
		player.rig.set_sit_clip("typing")
	elif opts.has("stand_at") and binder.anchors.has(opts.stand_at):
		var a: Dictionary = binder.anchors[opts.stand_at]
		player.teleport(a.pos, a.yaw)
	minigame = load(script_path).new()
	add_child(minigame)
	Sfx.music("tension", -12.0)
	minigame.setup(self, opts, func(result):
		_end_minigame()
		cb.call(result))


func _end_minigame() -> void:
	_refresh_presence()
	if minigame:
		minigame.queue_free()
		minigame = null
	player.rig.sitting = false
	camera_rig.clear_shot()
	mode = "play"
	resume()


# ------------------------------------------------------------------ world state
func _update_zone() -> void:
	var z := binder.zone_at(player.global_position)
	if z.is_empty():
		z = SandboxLevel.zone_fallback(player.global_position)
	if z.get("id", "") != _zone.get("id", ""):
		var first := _zone.is_empty()
		_zone = z
		# the M map inks the places Mano has been (V2-09)
		var seen: Array = GameState.flags.get("zones_seen", [])
		if String(z.get("id", "")) != "" and not String(z.id) in seen and mode == "play":
			seen = seen.duplicate()
			seen.append(String(z.id))
			GameState.flags["zones_seen"] = seen
		Sfx.set_zone(z.get("id", "court"))
		if mode == "play":
			_zone_music()
		player.surface = z.get("surface", "concrete")
		world_env.set_interior(1.0 if z.get("id", "") in ["amphi", "volt_gf", "volt_f1", "sm14", "sm15", "cafe", "under"] else 0.0)
		if not first and z.get("label", "") != "":
			_area_banner(z)


## The track for this place and time (chapters.json "music": by preset, "zone:<id>" first).
func _zone_music() -> void:
	var m: Array = place_music()
	Sfx.music(m[0], m[1])
	Chat.heard(Sfx.music_now())   # already playing before a load or a chapter start: still heard tonight


## The area banner, the first time Mano walks into a place in each chapter: the place's name, and under it where it
## is and the story clock ("KB1 1st floor, 18:31"; data/world.json zone_banners). The name is the level zone's
## label unless world.json zone_titles spells it better (the level's labels have no accents: "Batiment Voltaire").
func _area_banner(z: Dictionary) -> void:
	var key := "%d:%s" % [Chapters.current(), z.get("id", "")]
	var seen: Array = GameState.flags.get("banners", [])
	if key in seen:
		return
	seen.append(key)
	GameState.flags["banners"] = seen
	var where := String(WorldData.section("zone_banners").get(z.get("id", ""), z.get("sub", "")))
	var sub := Chapters.clock_text() if where == "" else "%s, %s" % [where, Chapters.clock_text()]
	hud.show_banner(String(WorldData.section("zone_titles").get(z.get("id", ""), z.label)), sub)
	hud.hint("photo_mode")   # a new place is the moment photo mode matters


func _build_graph() -> void:
	_graph = {}
	for key in binder.portals:
		var ab := String(key).split("|")
		if ab.size() != 2:
			continue
		for pair in [[ab[0], ab[1]], [ab[1], ab[0]]]:
			if not _graph.has(pair[0]):
				_graph[pair[0]] = []
			_graph[pair[0]].append(pair[1])


func _update_waypoint() -> void:
	var t: Dictionary = story.target()
	if t.is_empty():
		hud.waypoint_target = null
		return
	var goal: Vector3 = t.pos
	var here: String = _zone.get("id", "")
	var there: String = binder.zone_at(goal).get("id", "")
	var aim := goal
	if here != "" and there != "" and here != there and _graph.has(here):
		# breadth-first through doors/stairs to the next portal on the way
		var prev := {here: ""}
		var q: Array = [here]
		while not q.is_empty():
			var z: String = q.pop_front()
			if z == there:
				break
			for nb in _graph.get(z, []):
				if not prev.has(nb):
					prev[nb] = z
					q.append(nb)
		if prev.has(there):
			var nxt := there
			while prev[nxt] != here:
				nxt = prev[nxt]
			var pts: Array = binder.portals.get("%s|%s" % [here, nxt], [])
			if pts.is_empty():
				pts = binder.portals.get("%s|%s" % [nxt, here], []).duplicate()
				pts.reverse()
			if not pts.is_empty():
				aim = pts[0]
				for i in pts.size():
					if player.global_position.distance_to(pts[i]) < 1.6 and i < pts.size() - 1:
						aim = pts[i + 1]
	hud.waypoint_target = aim + Vector3.UP * 1.1


## A story reference (chapters.json targets, start_at, triggers) as {pos, label} (and yaw for points and anchors),
## or {}: npc:<id>, spot:<id> (a level marker or a world.json spot), point:<id> (world.json), anchor:<id> (level).
func target_of(kind: String, id: String, label: String) -> Dictionary:
	if kind == "npc" and npcs.has(id):
		return {"pos": npcs[id].global_position, "label": label}
	if kind == "spot":
		if _world_spots.has(id) and (_world_spots[id].override or not binder.spots.has(id)):
			return {"pos": _world_spots[id].pos, "label": label}
		if binder.spots.has(id):
			return {"pos": binder.spots[id].pos, "label": label}
	if kind == "point":
		var p := WorldData.point(id)
		if not p.is_empty():
			return {"pos": p.pos, "yaw": p.yaw, "label": label}
	if kind == "anchor" and binder.anchors.has(id):
		return {"pos": binder.anchors[id].pos, "yaw": binder.anchors[id].yaw, "label": label}
	return {}


func player_pos() -> Vector3:
	return player.global_position


## `doodle` is a hand-drawn icon id (HUD.toast), never a character.
func toast(text: String, doodle := "") -> void:
	hud.toast(text, doodle)


func save() -> void:
	if player and GameState.flags.get("toma", false) and mode != "ending":
		GameState.ducks_found = ducks.found_ids() if ducks else []
		GameState.write_save(player.global_transform.rotated_local(Vector3.UP, player.facing_yaw()))


func on_flags_changed() -> void:
	Chapters.track()
	hud.set_objective(story.objective())


func show_ending() -> void:
	phone.close(false)
	phone.hide_card()
	mode = "ending"
	GameState.clear_save()
	Sfx.music("ending", -6.0)
	menus.show_ending()


# ------------------------------------------------------------------ the finale (V2-26, V2-27)
const FILM_W := 960          # a print on Ishita's disposable camera, as the credits show it (pixels wide)
const GROUP_TIMER := 2.4     # the self-timer of the group photo: three beeps, then the flash
var _credits: CreditsRoll = null
## The last group photo (autotest=credits checks every friend's head is in it): {heads: {id: Vector2 or null}, path}.
var group_photo := {}


## `$ photo kind`: a photo on Ishita's disposable camera, kept in user://film/ for the credits (GameState.film_dir;
## *.autotest in autotests). "film": the frame on screen as it is (a stop on Ishita's tour), flags.film_shots + 1.
## "group": everyone on the steps faces the camera (world.json shot steps_group), the self-timer beeps and the
## flash goes. Returns how long the conversation waits on it.
func take_photo(kind: String) -> float:
	if kind == "group":
		_photo_group()
		return GROUP_TIMER + 1.4
	# the photo spot Mano stands at goes on the film (Film.take_at); one already on it is not taken again
	var r := Film.take_at(player.global_position)
	print("[photo] film at %s: %s, %d exposures used" % [player.global_position.snapped(Vector3.ONE * 0.1), r if r != "" else "no spot near", int(GameState.flags.get("film_shots", 0))])
	if r == "dup":
		return 0.2
	_keep_frame("film_%02d" % int(GameState.flags.get("film_shots", 0)), true)
	return 0.7


func _photo_group() -> void:
	hud.set_letterbox(false)
	_hold_shot = true
	var sh: Dictionary = WorldData.section("shots").get("steps_group", {})
	var cam_at := WorldData.vec(sh.get("from", [0, 1.7, 0]))
	var mark := WorldData.point("steps5_mano")
	if not mark.is_empty():
		var to: Vector3 = cam_at - mark.pos
		player.teleport(mark.pos, atan2(to.x, to.z))
	player.rig.look_at_point = cam_at
	player.rig.set_conversing(false)
	# everyone on the steps turns to the lens (their staging comes back after: stage_key forgotten)
	for id in npcs:
		var npc: NPC = npcs[id]
		if npc.visible and npc.global_position.distance_to(player.global_position) < 6.0:
			var d := cam_at - npc.global_position
			npc.apply_stage(npc.global_position, atan2(d.x, d.z), {"sit": npc.rig.sitting} if npc.rig else {})
			npc.stage_key = "-"
	camera_shot("steps_group")
	hud.set_letterbox(false)
	for i in 3:
		await get_tree().create_timer(GROUP_TIMER / 3.0).timeout
		Sfx.ui("ui_hover", -2.0 + i * 2.0)
	var heads := {}
	for id in ["toma", "anisha", "ian", "silvia", "ishita", "cristina", "joaquin"]:
		var npc: NPC = npcs.get(id)
		heads[id] = _in_frame(npc.rig.head_position()) if npc and npc.visible else null
	heads["mano"] = _in_frame(player.rig.head_position())
	var path := await _keep_frame("group", false)
	group_photo = {"heads": heads, "path": path}
	print("[photo] group: heads in the frame %s -> %s" % [heads, path])
	player.rig.look_at_point = null
	_refresh_presence.call_deferred()


## A point's place in the frame (0-1 across, 0-1 down), or null when it is behind the lens or outside the picture.
func _in_frame(p: Vector3):
	var cam := camera_rig.cam
	if not cam.is_position_in_frustum(p):
		return null
	var ray := PhysicsRayQueryParameters3D.create(cam.global_position, p, 1)
	if not get_world_3d().direct_space_state.intersect_ray(ray).is_empty():
		return null   # a wall or a prop between the lens and that head
	var vp := get_viewport().get_visible_rect().size
	var px := cam.unproject_position(p)
	return Vector2(px.x / vp.x, px.y / vp.y)


## The frame on screen, without the HUD or the subtitles, saved as a print in the film folder (the flash and the
## shutter with it). Returns the file's path.
func _keep_frame(name: String, with_letterbox: bool) -> String:
	hud.root.visible = false
	await RenderingServer.frame_post_draw
	var img: Image = get_viewport().get_texture().get_image()
	hud.root.visible = true
	if not with_letterbox:
		pass
	Sfx.play("shutter")
	hud.flash()
	var w := img.get_width()
	if w > FILM_W:
		img.resize(FILM_W, roundi(img.get_height() * float(FILM_W) / w), Image.INTERPOLATE_LANCZOS)
	var dir := GameState.film_dir()
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(dir))
	var path := dir.path_join(name + ".png")
	img.save_png(path)
	print("[photo] kept %s (%dx%d)" % [path, img.get_width(), img.get_height()])
	return path


## A new night, a new film: the last night's prints from Ishita's camera go (film_NN.png, group.png); the copies of
## photo-mode shots (photo_*.png) are the player's own and stay.
func _clear_film() -> void:
	var dir := ProjectSettings.globalize_path(GameState.film_dir())
	var d := DirAccess.open(dir)
	if d == null:
		return
	for f in d.get_files():
		if String(f).begins_with("film_") or String(f) == "group.png":
			d.remove(f)


## `$ airpods case|ear`: both AirPods out of his ears and into their case (the turn: Anisha's SOS), or back in.
func set_airpods(where: String) -> void:
	var in_case := where == "case"
	GameState.flags["airpods_case"] = in_case
	player.stow_airpods(in_case, true)
	Sfx.play("pickup", -4.0)
	if in_case:
		toast("Both in the case", "airpod")
	GameState.flags_changed.emit()


## `$ caption "text" seconds`: to black, and the line written on in Mano's pen in the middle of it (the cold open's
## "Six hours earlier."). The screen stays black after: what comes next fades it up. Returns how long it takes.
func caption(text: String, seconds := 2.4) -> float:
	hud.fade_to(1.0, 0.5)
	get_tree().create_timer(0.55).timeout.connect(func():
		if mode == "dialogue":   # still in the scene that asked (not skipped on into the next chapter's card)
			hud.caption(text, seconds))
	return 0.55 + seconds + 0.5


## `$ freeze`: the picture stops (the cold open): a still of the frame holds over the scene until the next opening.
func freeze_frame() -> void:
	_freeze_now()


func _freeze_now() -> void:
	await RenderingServer.frame_post_draw
	var img: Image = get_viewport().get_texture().get_image()
	hud.freeze(ImageTexture.create_from_image(img))
	Sfx.play("shutter", -10.0)


## `$ credits` (the end of chapter 5): mode "credits". The camera rises from the steps over the courtyard toward
## rue Pasteur and KB1's lit windows while the names and the night's film prints go by (CreditsRoll); the song
## picked for the playlist goes on under them. Any key after the first seconds runs them to the end. Then the
## post-credits (00:25 on rue Pasteur, post.credits with Mme Dupont) and the recap.
func roll_credits() -> void:
	print("[credits] roll: %d prints in %s, score '%s'" % [CreditsRoll.print_paths().size(), GameState.film_dir(), _score])
	mode = "credits"
	player.frozen = true
	camera_rig.input_enabled = false
	hud.set_hud_visible(false)
	hud.set_letterbox(false)
	phone.close(false)
	phone.hide_card()
	dialogue.clear_barks()
	Input.mouse_mode = Input.MOUSE_MODE_HIDDEN
	if _score == "":
		set_score(String(GameState.flags.get("playlist", "")) if String(GameState.flags.get("playlist", "")) != "" else "ending")
	_hold_shot = true
	var a: Dictionary = WorldData.section("shots").get("credits_start", {})
	var b: Dictionary = WorldData.section("shots").get("credits_end", {})
	if _credits:
		_credits.queue_free()
	_credits = CreditsRoll.new()
	_credits.game = self
	_credits.shot_a = a
	_credits.shot_b = b
	add_child(_credits)
	_credits.finished.connect(_post_credits, CONNECT_ONE_SHOT)


## After the credits: under the black, 00:25; Mano on rue Pasteur heading for the last metro, Mme Dupont locking up
## behind him; post.credits plays (the AirPods back in, *plink*, a drain grate) and ends on the recap.
func _post_credits() -> void:
	if _credits:
		_credits.queue_free()
		_credits = null
	mode = "cutscene"
	hud.fade.color.a = 1.0
	camera_rig.clear_shot(true)
	_hold_shot = false
	GameState.flags["clock"] = Conditions.minutes("24:25")
	place_at("mano", "post_street")
	var over = GameState.flags.get("stage_over", {})
	if not over is Dictionary:
		over = {}
	over["madame2"] = "post_madame"
	GameState.flags["stage_over"] = over
	restage("madame2")
	player.stow_airpods(true)   # both in the case: the post-credits put them in, one after the other
	Sfx.set_zone("street")
	if _score != "":
		Sfx.music(_score, SCORE_DB - 4.0, 2.0)   # quieter now: in both his ears, walking home
	print("[credits] post-credits at %s on rue Pasteur" % Chapters.clock_text())
	await get_tree().create_timer(0.6).timeout
	hud.fade_to(0.0, 1.2)
	say(story.steps("post.credits"), "madame2")


## `$ recap` (the last line of the post-credits): the notebook's last page, "à suivre…" and the night as Mano lived
## it (Menus.show_recap: "your night"), then "Keep exploring" (the campus at night) or the title.
func show_recap() -> void:
	phone.close(false)
	phone.hide_card()
	mode = "ending"
	_score = ""
	GameState.flags["credits_done"] = true
	GameState.clear_save()
	Sfx.music("ending", -6.0)
	menus.show_recap()


## The menus that open over play (pause and its settings, journal, map, wardrobe, photo mode): what they hold is
## a moment of play, so closing the window there saves as play does.
const PLAY_MENUS := ["pause", "journal", "map", "wardrobe", "photo", "phone"]


func _notification(what: int) -> void:
	if what == NOTIFICATION_APPLICATION_FOCUS_OUT and mode == "play":
		menus.show_pause()
	elif what == NOTIFICATION_WM_CLOSE_REQUEST and (mode == "play" or mode in PLAY_MENUS):
		# closing the window saves first; in a conversation, cutscene or minigame the last save stands
		# (it was written at the end of the last conversation, or under the chapter card)
		save()
