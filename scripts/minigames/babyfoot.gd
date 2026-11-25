extends Node3D
## Babyfoot against Karim on the BDE table. First to 3.
## Field logic in table-local metres: x along the table (Mano attacks +x), z across it.
## 2v2 (V2-23): with a partner (opts.partner or flags.foot_partner: ian, silvia or joaquin) Mano works the attack
## rod and the partner the goalie rod. Karim gets 12 % slower for every game Mano has lost (flags.foot_losses),
## never below 60 %. After two losses the partner says "Switch.", takes the attack and shoots past Karim's goalie.

const FX := 0.58
const FZ := 0.33
const GOAL := 0.11
const SURF := 0.86
const BALL_R := 0.017
const RODS := [
	{"x": -0.47, "n": 1, "gap": 0.0, "team": 1, "role": "goal"},
	{"x": -0.17, "n": 3, "gap": 0.2, "team": -1, "role": "attack"},
	{"x": 0.17, "n": 3, "gap": 0.2, "team": 1, "role": "attack"},
	{"x": 0.47, "n": 1, "gap": 0.0, "team": -1, "role": "goal"},
]
const PARTNERS := ["ian", "silvia", "joaquin"]
const SLOWER := 0.12     # Karim's speed per game lost
const SLOWEST := 0.6
## What the partner says as the game starts, and when they take over after two losses (text only: no voices).
const PARTNER_LINES := {
	"ian": ["Ian: \"I've got the goal. Pain au chocolat on three.\"", "Ian: \"Switch. Trust me.\""],
	"silvia": ["Silvia: \"I'll hold the goal. You do the scoring.\"", "Silvia: \"Switch. My turn.\""],
	"joaquin": ["Joaquin: \"Goal's mine. I've studied his shots.\"", "Joaquin: \"...Switch. I have a theory.\""],
}

var game
var _done: Callable
var _ps := 0
var _as := 0
var _pz := 0.0
var _az := 0.0
var _pv := 0.0
var _av := 0.0
var _ball = null          # {x, z, vx, vz} or null
var _wait := 1.6
var _kick := 0.0
var _akick := 0.0
var _ai_t := 0.0
var _ai_target := 0.0
var _over := 0.0
var _serve_dir := 1
var _stuck := 0.0
var _rods: Array = []
var partner := ""          # "" is solo
var switched := false      # the partner has the attack (after two losses)
var karim_k := 1.0         # Karim's speed factor
var _qz := 0.0             # the partner's rod
var _qv := 0.0
var _qkick := 0.0
var _q_t := 0.0
var _q_target := 0.0
var _pnpc: Node3D = null   # the partner standing at the table with Mano
var _pnpc_home := []
var _ball_mesh: MeshInstance3D
var _score: Label
var _msg: Label


func setup(g, opts: Dictionary, done: Callable) -> void:
	game = g
	_done = done
	partner = String(opts.get("partner", GameState.flags.get("foot_partner", "")))
	if not partner in PARTNERS:
		partner = ""
	var losses := int(GameState.flags.get("foot_losses", 0))
	karim_k = maxf(SLOWEST, 1.0 - SLOWER * losses)
	switched = partner != "" and losses >= 2
	print("[babyfoot] partner %s, Karim at %d %%, %s" % [partner if partner != "" else "none (solo)", roundi(karim_k * 100.0),
		"switched: the partner attacks" if switched else ("2v2: the partner keeps goal" if partner != "" else "1v1")])
	var a: Dictionary = game.binder.anchors.get("babyfoot", {})
	if a.is_empty():
		a = {"pos": game.player.global_position + Vector3(0, 0, -0.9), "yaw": 0.0}
		_build_body()
	global_position = a.pos
	rotation.y = a.yaw
	_build_field()
	var from := to_global(Vector3(0, SURF + 1.3, 0.66))
	var look := to_global(Vector3(0, SURF, 0.02))
	game.camera_rig.set_shot(from, look, 48.0, from.distance_to(look))
	_build_ui()
	_place_partner()
	if partner == "":
		_render_score("First to 3")
	elif switched:
		_render_score(PARTNER_LINES[partner][1])
	else:
		_render_score(PARTNER_LINES[partner][0])


## The partner at the table beside Mano, at their rod's end (back where they were when the game is over).
func _place_partner() -> void:
	if partner == "" or not game.npcs.has(partner):
		return
	_pnpc = game.npcs[partner]
	_pnpc_home = [_pnpc.global_position, _pnpc.rig.rotation.y if _pnpc.rig else 0.0]
	# at the corner by their rod's handle, beside Mano: only an arm reaches into the shot from above
	var at := to_global(Vector3(-0.72 if not switched else 0.72, 0.0, 1.0))
	_pnpc.set_present(true)
	_pnpc.apply_stage(at, rotation.y + PI, {})
	_pnpc.set_solid(false)


func _exit_tree() -> void:
	if _pnpc and is_instance_valid(_pnpc) and not _pnpc_home.is_empty():
		_pnpc.apply_stage(_pnpc_home[0], _pnpc_home[1], {})
		_pnpc.set_solid(true)


func _mat(c: Color, rough := 0.5, metal := 0.0) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = c
	m.roughness = rough
	m.metallic = metal
	return m


func _box(size: Vector3, pos: Vector3, m: Material) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = size
	mi.mesh = bm
	mi.material_override = m
	mi.position = pos
	add_child(mi)
	return mi


func _build_body() -> void:
	var wood := _mat(Color("#2b2f3a"), 0.6)
	_box(Vector3(1.3, 0.24, 0.78), Vector3(0, SURF - 0.125, 0), wood)
	for x in [-0.55, 0.55]:
		for z in [-0.3, 0.3]:
			_box(Vector3(0.07, SURF - 0.2, 0.07), Vector3(x, (SURF - 0.2) * 0.5, z), wood)


func _build_field() -> void:
	# pitch with lines, rails, goals
	var pitch := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(FX * 2, FZ * 2)
	pitch.mesh = pm
	var tex := _pitch_texture()
	var m := StandardMaterial3D.new()
	m.albedo_texture = tex
	m.roughness = 0.8
	pitch.material_override = m
	pitch.position.y = SURF + 0.002
	add_child(pitch)
	var rail := _mat(Color("#1d2028"), 0.5)
	_box(Vector3(FX * 2 + 0.06, 0.08, 0.03), Vector3(0, SURF + 0.04, -FZ - 0.015), rail)
	_box(Vector3(FX * 2 + 0.06, 0.08, 0.03), Vector3(0, SURF + 0.04, FZ + 0.015), rail)
	for sx in [-1, 1]:
		_box(Vector3(0.03, 0.08, FZ - GOAL), Vector3(sx * (FX + 0.015), SURF + 0.04, -(FZ + GOAL) * 0.5), rail)
		_box(Vector3(0.03, 0.08, FZ - GOAL), Vector3(sx * (FX + 0.015), SURF + 0.04, (FZ + GOAL) * 0.5), rail)
		_box(Vector3(0.06, 0.07, GOAL * 2), Vector3(sx * (FX + 0.05), SURF + 0.0, 0), _mat(Color(0.05, 0.05, 0.06), 0.9))
	var steel := _mat(Color("#c9ced6"), 0.25, 0.9)
	for r in RODS:
		var grp := Node3D.new()
		grp.position = Vector3(r.x, SURF + 0.075, 0)
		add_child(grp)
		var bar := MeshInstance3D.new()
		var cm := CylinderMesh.new()
		cm.top_radius = 0.007
		cm.bottom_radius = 0.007
		cm.height = 1.05
		bar.mesh = cm
		bar.rotation.x = PI / 2
		bar.material_override = steel
		grp.add_child(bar)
		var handle := MeshInstance3D.new()
		var hm := CylinderMesh.new()
		hm.top_radius = 0.017
		hm.bottom_radius = 0.017
		hm.height = 0.11
		handle.mesh = hm
		handle.rotation.x = PI / 2
		handle.position.z = 0.58 if r.team == 1 else -0.58
		var hc := Color("#202020") if r.team == 1 else Color("#c0392b")
		if r.team == 1 and _controller(_rods.size()) == "partner":
			hc = _partner_color()   # the partner's handle in their colour
		handle.material_override = _mat(hc, 0.6)
		grp.add_child(handle)
		var figs: Array = []
		for k in r.n:
			var f := _figure(Color("#1d1d22") if r.team == 1 else Color("#e8b923"))
			grp.add_child(f)
			figs.append(f)
		_rods.append({"def": r, "group": grp, "figs": figs})
	_ball_mesh = MeshInstance3D.new()
	var sm := SphereMesh.new()
	sm.radius = BALL_R
	sm.height = BALL_R * 2
	_ball_mesh.mesh = sm
	_ball_mesh.material_override = _mat(Color("#f5f5f0"), 0.35)
	_ball_mesh.visible = false
	add_child(_ball_mesh)
	var lamp := OmniLight3D.new()
	lamp.position = Vector3(0, SURF + 0.9, 0)
	lamp.light_energy = 1.2
	lamp.omni_range = 2.5
	lamp.light_color = Color(1.0, 0.92, 0.8)
	lamp.shadow_enabled = true
	add_child(lamp)


func _figure(c: Color) -> Node3D:
	var g := Node3D.new()
	var body := MeshInstance3D.new()
	var cap := CapsuleMesh.new()
	cap.radius = 0.016
	cap.height = 0.082
	body.mesh = cap
	body.position.y = -0.02
	body.material_override = _mat(c, 0.45)
	g.add_child(body)
	var head := MeshInstance3D.new()
	var hm := SphereMesh.new()
	hm.radius = 0.014
	hm.height = 0.028
	head.mesh = hm
	head.position.y = 0.035
	head.material_override = _mat(Color("#2a1d16"), 0.6)
	g.add_child(head)
	var legs := MeshInstance3D.new()
	var lm := BoxMesh.new()
	lm.size = Vector3(0.03, 0.05, 0.014)
	legs.mesh = lm
	legs.position.y = -0.075
	legs.material_override = _mat(Color("#141414"), 0.7)
	g.add_child(legs)
	return g


func _pitch_texture() -> ImageTexture:
	var w := 464
	var h := 264
	var img := Image.create(w, h, false, Image.FORMAT_RGB8)
	for y in h:
		for x in w:
			var stripe := int(x / 58.0) % 2 == 0
			img.set_pixel(x, y, Color("#2f7d3b") if stripe else Color("#2a7035"))
	var white := Color(0.92, 0.94, 0.9)
	for y in h:
		for t in 2:
			img.set_pixel(w / 2 + t, y, white)
	for x in w:
		for t in 2:
			img.set_pixel(x, t, white)
			img.set_pixel(x, h - 1 - t, white)
	for a in 360:
		var p := Vector2(w / 2, h / 2) + Vector2(cos(deg_to_rad(a)), sin(deg_to_rad(a))) * 34.0
		img.set_pixel(int(p.x), int(p.y), white)
	return ImageTexture.create_from_image(img)


func _build_ui() -> void:
	var layer := CanvasLayer.new()
	layer.layer = 15
	add_child(layer)
	var root := Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.theme = UITheme.theme
	layer.add_child(root)
	var top := VBoxContainer.new()
	top.anchor_left = 0.5
	top.anchor_right = 0.5
	top.offset_left = -400
	top.offset_right = 400
	top.offset_top = 40
	_score = UITheme.shadowed(UITheme.label("", 46, UITheme.display_xb, UITheme.INK), 3, 0.6)
	_score.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	top.add_child(_score)
	# the partner's lines sit over the table and Karim's yellow hoodie: the heavier dark outline of text over the scene
	_msg = UITheme.over_scene(UITheme.label("", 28, UITheme.hand, UITheme.GOLD), 8, 0.6) as Label
	_msg.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	top.add_child(_msg)
	root.add_child(top)
	var bottom := HBoxContainer.new()
	bottom.anchor_left = 0.5
	bottom.anchor_right = 0.5
	bottom.anchor_top = 1.0
	bottom.anchor_bottom = 1.0
	bottom.offset_left = -260
	bottom.offset_right = 260
	bottom.offset_top = -86
	bottom.add_theme_constant_override("separation", 10)
	for k in ["W", "S"]:
		bottom.add_child(UITheme.key_cap(k, 16))
	bottom.add_child(UITheme.shadowed(UITheme.label("move your rods", 22, UITheme.hand, UITheme.INK), 2, 0.6))
	bottom.add_child(UITheme.key_cap(UITheme.action_key("confirm"), 16))
	bottom.add_child(UITheme.shadowed(UITheme.label("kick", 22, UITheme.hand, UITheme.INK), 2, 0.6))
	root.add_child(bottom)


func _render_score(msg: String) -> void:
	var us := "MANO" if partner == "" else "MANO + %s" % partner.to_upper()
	_score.text = "%s  %d  -  %d  KARIM" % [us, _ps, _as]
	_msg.text = msg


## Who works rod `i` on Mano's side: "mano" or "partner" (solo: Mano works both).
func _controller(i: int) -> String:
	if partner == "" or RODS[i].team != 1:
		return "mano"
	var attack: bool = RODS[i].role == "attack"
	if switched:
		return "partner" if attack else "mano"
	return "mano" if attack else "partner"


func _partner_color() -> Color:
	for d in CastDefs.npc_defs():
		if d.id == partner:
			return d.color
	return Color("#3a6ea5")


func _fig_z(r: Dictionary) -> Array:
	var t := _az
	if r.team == 1:
		t = _qz if _controller(RODS.find(r)) == "partner" else _pz
	var half: float = (r.n - 1) / 2.0 * r.gap
	var lo: float = -GOAL - 0.02 if r.n == 1 else -FZ + 0.04 + half
	var hi: float = GOAL + 0.02 if r.n == 1 else FZ - 0.04 - half
	var c := clampf(t, lo, hi)
	var out: Array = []
	for k in r.n:
		out.append(c - half + k * r.gap)
	return out


func _serve() -> void:
	_ball = {"x": 0.0, "z": randf_range(-0.06, 0.06), "vx": _serve_dir * 0.42, "vz": randf_range(-0.15, 0.15)}
	_ball_mesh.visible = true
	_stuck = 0.0
	Sfx.play("babyfoot_kick", -10.0)


func _goal(side: int) -> void:
	if side == 1:
		_ps += 1
	else:
		_as += 1
	_ball = null
	_ball_mesh.visible = false
	_wait = 1.4
	_serve_dir = -side
	Sfx.play("babyfoot_goal")
	game.camera_rig.add_trauma(0.4)
	var msg := "GOAL! Mano scores." if side == 1 else "Karim scores. He will not shut up about it."
	if side == 1 and switched and partner != "":
		msg = "GOAL! %s scores. Karim is speechless." % partner.capitalize()
	if _ps >= 3 or _as >= 3:
		_over = 2.8
		msg = "MANO WINS. The BDE is in shock." if _ps >= 3 else "KARIM WINS."
		if _ps >= 3:
			Sfx.play("crowd_cheer", -6.0)
	_render_score(msg)


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("confirm"):
		get_viewport().set_input_as_handled()
		if _over > 0.0 and _over < 2.0:
			_over = 0.01
		elif _kick <= 0.0:
			_kick = 0.2
			Sfx.play("babyfoot_kick", -8.0, "SFX", randf_range(0.95, 1.1))


func _process(dt: float) -> void:
	if _over > 0.0:
		_over -= dt
		if _over <= 0.0:
			var win := _ps >= 3
			_done.call(win)
			return
	var oz := _pz
	var axis := 0.0
	if Input.is_action_pressed("move_forward") or Input.is_action_pressed("ui_up"):
		axis -= 1.0
	if Input.is_action_pressed("move_back") or Input.is_action_pressed("ui_down"):
		axis += 1.0
	_pz = clampf(_pz + axis * 0.62 * dt, -FZ, FZ)
	_pv = (_pz - oz) / maxf(dt, 1e-4)
	_kick = maxf(0.0, _kick - dt)
	_akick = maxf(0.0, _akick - dt)
	# Karim re-reads the ball about four times a second, with some aim error
	var oaz := _az
	_ai_t -= dt
	if _ai_t <= 0.0:
		_ai_t = 0.24
		_ai_target = (_ball.z + (_ball.vz * 0.12 if _ball.vx > 0 else 0.0) + randf_range(-0.05, 0.05)) if _ball != null else 0.0
	var spd := (0.34 + (_ps - _as) * 0.035) * karim_k
	_az = clampf(_az + clampf(_ai_target - _az, -spd * dt, spd * dt), -FZ, FZ)
	_av = (_az - oaz) / maxf(dt, 1e-4)
	if partner != "":
		_partner_ai(dt)
	if _wait > 0.0:
		_wait -= dt
		if _wait <= 0.0 and _over <= 0.0:
			_serve()
	elif _ball != null and _over <= 0.0:
		_step_ball(dt)
	_update_visuals()


## The partner reads the ball a little faster than Karim and with less error; on goal they go where the ball
## will cross their rod, on the attack (switched) they line up with it.
func _partner_ai(dt: float) -> void:
	var oq := _qz
	_qkick = maxf(0.0, _qkick - dt)
	_q_t -= dt
	if _q_t <= 0.0:
		_q_t = 0.18
		if _ball == null:
			_q_target = 0.0
		else:
			var rod_x: float = RODS[2].x if switched else RODS[0].x
			var lead := 0.0
			if absf(_ball.vx) > 0.05:
				lead = clampf((rod_x - _ball.x) / _ball.vx, 0.0, 0.5)
			_q_target = _ball.z + _ball.vz * lead + randf_range(-0.02, 0.02)
	_qz = clampf(_qz + clampf(_q_target - _qz, -0.46 * dt, 0.46 * dt), -FZ, FZ)
	_qv = (_qz - oq) / maxf(dt, 1e-4)


func _step_ball(dt: float) -> void:
	var b: Dictionary = _ball
	b.x += b.vx * dt
	b.z += b.vz * dt
	b.vx *= 1.0 - 0.12 * dt
	b.vz *= 1.0 - 0.3 * dt
	if b.z < -FZ + BALL_R:
		b.z = -FZ + BALL_R
		b.vz = absf(b.vz)
	if b.z > FZ - BALL_R:
		b.z = FZ - BALL_R
		b.vz = -absf(b.vz)
	if b.x < -FX + BALL_R:
		if absf(b.z) < GOAL:
			_goal(-1)
			return
		b.x = -FX + BALL_R
		b.vx = absf(b.vx)
	if b.x > FX - BALL_R:
		if absf(b.z) < GOAL:
			_goal(1)
			return
		b.x = FX - BALL_R
		b.vx = -absf(b.vx)
	for rod in _rods:
		var r: Dictionary = rod.def
		if absf(b.x - r.x) > 0.03:
			continue
		for fz in _fig_z(r):
			if absf(b.z - fz) > 0.032:
				continue
			var by_partner: bool = r.team == 1 and _controller(_rods.find(rod)) == "partner"
			if r.team == -1 and _akick <= 0.0 and randf() < 0.9:
				_akick = 0.2
			if by_partner and _qkick <= 0.0:
				_qkick = 0.2
			var kicking: bool = (_qkick > 0.0 if by_partner else _kick > 0.0) if r.team == 1 else _akick > 0.0
			if kicking:
				b.vx = float(r.team) * randf_range(0.85, 1.15)
				b.vz = (b.z - fz) * 7.0 + (_pv if r.team == 1 else _av) * 0.5 + randf_range(-0.1, 0.1)
				if by_partner and switched:
					# the partner's shot: fast, into the half of the goal Karim's goalie is not covering
					var aim := -0.075 if _az > 0.0 else 0.075
					b.vx = 1.25
					b.vz = (aim - b.z) / maxf((FX - b.x) / b.vx, 0.05)
				Sfx.play("babyfoot_kick", -6.0)
				if r.team == 1:
					if by_partner:
						_qkick = 0.0
					else:
						_kick = 0.0
			else:
				b.vx = -b.vx * 0.65 if absf(b.vx) > 0.05 else float(r.team) * 0.25
				b.vz += (b.z - fz) * 3.0
			b.x = r.x + signf(b.vx) * 0.032
			break
	var speed := Vector2(b.vx, b.vz).length()
	_stuck = _stuck + dt if speed < 0.06 else 0.0
	if _stuck > 1.5:
		b.vx = float(_serve_dir) * 0.35
		b.vz = randf_range(-0.2, 0.2)
		_stuck = 0.0


func _update_visuals() -> void:
	for rod in _rods:
		var r: Dictionary = rod.def
		var zs := _fig_z(r)
		var by_partner: bool = r.team == 1 and _controller(_rods.find(rod)) == "partner"
		var kicking: bool = (_qkick > 0.0 if by_partner else _kick > 0.0) if r.team == 1 else _akick > 0.0
		var swing := (-0.9 if kicking else 0.0) * float(r.team)
		for k in rod.figs.size():
			var f: Node3D = rod.figs[k]
			f.position.z = zs[k]
			f.rotation.z = lerpf(f.rotation.z, swing, 0.5)
		# the whole rod slides with its players; the handle sticks out on the owner's side
		var mid: float = (zs[0] + zs[-1]) * 0.5
		(rod.group as Node3D).get_child(0).position.z = mid
		(rod.group as Node3D).get_child(1).position.z = mid + (0.58 if r.team == 1 else -0.58)
	if _ball != null:
		_ball_mesh.position = Vector3(_ball.x, SURF + BALL_R, _ball.z)
		_ball_mesh.rotate_z(-_ball.vx * 0.5)
