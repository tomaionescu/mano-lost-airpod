extends SceneTree
## Review driver for a character's hair and face in the game's own dialogue framing: loads the main scene, seats
## the reviewed NPC (id toma) in an Amphi 4 seat facing Mano at 1.3 m, freezes the rig on one frame of sit_talk
## (the same frame for every model, no random blinks) and shoots the dialogue cameras (30 deg lens at 1.35 /
## 1.8 m, over-the-shoulder), third-person and from behind. Models are swapped at runtime with NPC.setup. Writes
## no save.
## user args: out=<abs dir> models=a,b [time=golden,night] [pose=sit_talk@1.2]
## A model "file:<abs .glb>" is loaded at runtime in place of res://assets/characters/<stem>.glb. hairp sets hair
## shader uniforms (two numbers are a Vector2, three a Color; keys u_<name> go to the hair underlayer).
## var=<tag>@k:v;k:v (repeatable) shoots a variant after the base set, its uniforms set on top of hairp and set
## back afterwards; varonly=1 skips the base set.
var keep := []
var hairp := {}
var variants := []
var cards_bin := ""
var varonly := false

static func parse_kv(s: String) -> Dictionary:
	var d := {}
	for kv in s.split(";"):
		if kv == "":
			continue
		var nm := kv.get_slice(":", 0)
		var vs := kv.get_slice(":", 1).split(",")
		if vs.size() == 1:
			d[nm] = float(vs[0])
		elif vs.size() == 2:
			d[nm] = Vector2(float(vs[0]), float(vs[1]))
		else:
			d[nm] = Color(float(vs[0]), float(vs[1]), float(vs[2]))
	return d
var swaps := {}

static func swap_textures(rig_: Node, sw: Dictionary) -> int:
	var texs := {}
	for k in sw:
		var img := Image.load_from_file(sw[k])
		img.generate_mipmaps()
		texs[k] = ImageTexture.create_from_image(img)
	var n := 0
	for mi in rig_.find_children("*", "MeshInstance3D", true, false):
		var mats := []
		for si in mi.get_surface_override_material_count():
			mats.append(mi.get_surface_override_material(si))
		if mi.material_override:
			mats.append(mi.material_override)
		for m0 in mats:
			var mm = m0
			while mm != null:
				if mm is ShaderMaterial:
					for u in mm.shader.get_shader_uniform_list():
						var v = mm.get_shader_parameter(u.name)
						if v is Texture2D:
							for k in texs:
								if k in (v as Texture2D).resource_path or (k == "atlas" and u.name == "albedo_tex" and "scancards" in mi.name):
									mm.set_shader_parameter(u.name, texs[k])
									print("[rg] swapped ", mi.name, " ", u.name, " ", v.resource_path, " -> ", sw[k])
									n += 1
				elif mm is BaseMaterial3D:
					var bm := mm as BaseMaterial3D
					for k in texs:
						if bm.albedo_texture and k in bm.albedo_texture.resource_path:
							bm.albedo_texture = texs[k]
							print("[rg] swapped ", mi.name, " albedo -> ", sw[k])
							n += 1
				mm = mm.next_pass
	return n
var tag := ""
var out := ""
var models := ["toma_fit1", "toma_fit1_headtest"]
var times := ["golden"]
var pose := "sit_talk@1.2"
var body_tex := ""
var body_surf := -1
var only := []
var game: Node

func set_params(rig_: Node, ps: Dictionary) -> Dictionary:
	# returns the values the uniforms had before (to set them back)
	var before := {}
	for mi in rig_.find_children("*", "MeshInstance3D", true, false):
		var under: bool = "hairunder" in mi.name
		if not "hair_scancards" in mi.name and not under:
			continue
		for si in mi.get_surface_override_material_count():
			var mm = mi.get_surface_override_material(si)
			while mm is ShaderMaterial:
				for k in ps:
					if under != k.begins_with("u_"):
						continue
					var nm: String = k.substr(2) if under else k
					if not before.has(k):
						before[k] = mm.get_shader_parameter(nm)
					mm.set_shader_parameter(nm, ps[k])
				mm = mm.next_pass
	return before

func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("out="):
			out = a.substr(4)
		elif a.begins_with("models="):
			models = Array(a.substr(7).split(","))
		elif a.begins_with("time="):
			times = Array(a.substr(5).split(","))
		elif a.begins_with("pose="):
			pose = a.substr(5)
		elif a.begins_with("body_tex="):
			body_tex = a.substr(9)
		elif a.begins_with("body_surf="):
			body_surf = int(a.substr(10))
		elif a.begins_with("hairp="):
			hairp = parse_kv(a.substr(6))
		elif a.begins_with("var="):
			variants.append([a.substr(4).get_slice("@", 0), parse_kv(a.substr(4).get_slice("@", 1))])
		elif a.begins_with("cards="):
			cards_bin = a.substr(6)
		elif a == "varonly=1":
			varonly = true
		elif a.begins_with("tex="):
			for kv in a.substr(4).split(";"):
				swaps[kv.get_slice(":", 0)] = kv.substr(kv.find(":") + 1)
		elif a.begins_with("tag="):
			tag = a.substr(4)
		elif a.begins_with("only="):
			only = Array(a.substr(5).split(","))
	DirAccess.make_dir_recursive_absolute(out)
	print("[rg] init out=", out)
	change_scene_to_file("res://scenes/main.tscn")
	_drive.call_deferred()

func wait(sec: float) -> void:
	await create_timer(sec, true, false, true).timeout

func _unpause() -> bool:
	if game.mode != "play" or paused:
		game.resume()
		game.hud.set_hud_visible(false)
		game.player.frozen = true
		game.camera_rig.input_enabled = false
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
		return true
	return false

func shot(name: String) -> void:
	if _unpause():
		print("[rg] unpaused before ", name)
		await wait(0.6)
	# (a window behind others may not redraw on its own: draw once now)
	RenderingServer.force_draw()
	await RenderingServer.frame_post_draw
	var img := root.get_texture().get_image()
	var p := "%s/%s.png" % [out, name]
	img.save_png(p)
	print("[rg] shot ", p, " ", img.get_size())

func _own(n: Node, owner_node: Node) -> void:
	for c in n.get_children():
		c.owner = owner_node
		_own(c, owner_node)

func _freeze(rig) -> void:
	var clip := pose.get_slice("@", 0)
	var t := float(pose.get_slice("@", 1))
	if rig.anim_player and rig.has_clip(clip):
		rig.tree.active = false
		rig.anim_player.play(rig._clips[clip])
		rig.anim_player.seek(t, true)
		rig.anim_player.pause()
	rig.set("_blink_t", 1.0e9)
	rig.set("_blink", 0.0)

func _drive() -> void:
	while current_scene == null:
		await process_frame
	game = current_scene
	while game.mode == "loading":
		await wait(0.25)
	var gs = root.get_node("GameState")
	print("[rg] loaded; time ", gs.flags.get("time", "?"), " quality ", gs.settings.get("quality", "?"))
	await wait(1.0)
	game.menus.close()
	game.resume()
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	game.hud.set_hud_visible(false)
	game.player.frozen = true
	game.camera_rig.input_enabled = false
	await wait(2.0)
	for tm in times:
		if tm != "golden":
			game.world_env.apply_time(tm)
			await wait(2.0)
		for model0 in models:
			var model: String = model0
			if model0.begins_with("file:"):
				var p: String = model0.substr(5)
				model = p.get_file().get_basename() + "_rt"
				var doc := GLTFDocument.new()
				var gst := GLTFState.new()
				var err := doc.append_from_file(p, gst)
				print("[rg] gltf ", p, " err ", err)
				var scn := doc.generate_scene(gst)
				_own(scn, scn)
				var packed := PackedScene.new()
				packed.pack(scn)
				packed.take_over_path("res://assets/characters/%s.glb" % model)
				keep.append(packed)
			var npc = game.npcs["toma"]
			var chair = npc.swivel_chair
			var old = npc.rig
			npc.remove_child(old)
			old.queue_free()
			var d: Dictionary = npc.def.duplicate()
			d["model"] = model
			npc.setup(d, game.player)
			npc.swivel_chair = chair
			await wait(1.0)
			if not swaps.is_empty():
				print("[rg] texture swaps ", swap_textures(npc.rig, swaps))
			if not hairp.is_empty():
				set_params(npc.rig, hairp)
				print("[rg] hair params ", hairp)
			var tints := []
			for mi in npc.rig.find_children("*", "MeshInstance3D", true, false):
				if "scancards" in mi.name:
					for si in mi.get_surface_override_material_count():
						var mm = mi.get_surface_override_material(si)
						if mm is ShaderMaterial:
							tints.append("%s/%d tint=%s" % [mi.name, si, str(mm.get_shader_parameter("tint"))])
			print("[rg] hair tints ", tints)
			if body_tex != "" and model.ends_with("headtest"):
				var img := Image.load_from_file(body_tex)
				var tex := ImageTexture.create_from_image(img)
				for mi in npc.rig.find_children("*", "MeshInstance3D", true, false):
					for si in mi.get_surface_override_material_count():
						var mm = mi.get_surface_override_material(si)
						if (body_surf < 0 or si == body_surf) and mm is StandardMaterial3D and mm.albedo_texture and mm.albedo_texture.get_width() == 4096 and mi.mesh.surface_get_material(si) and ("skin_Human" in mi.mesh.surface_get_material(si).resource_name or "cloth" in mi.mesh.surface_get_material(si).resource_name):
							mm.albedo_texture = tex
							print("[rg] body texture swapped on ", mi.name, " ", si)
			var facing: Vector3 = npc.facing_dir()
			var front: Vector3 = npc.global_position + facing * 1.3
			game.player.teleport(front + Vector3.UP * 0.05, atan2(-facing.x, -facing.z))
			game.player.visible = false
			npc.rig.set_conversing(true)
			await wait(2.5)
			_freeze(npc.rig)
			await wait(1.5)
			var face: Vector3 = npc.rig.head_position() - Vector3.UP * 0.04
			print("[rg] ", tm, " ", model, " face ", face, " facing ", facing)
			var list := []
			for deg in [0, 30, -30, 55, -55, 80, -80, 125, -125, 180]:
				list.append(["r135_%+04d" % deg, face + facing.rotated(Vector3.UP, deg_to_rad(float(deg))) * 1.35 + Vector3.UP * 0.06, 30.0])
			for deg in [0, 55, -55]:
				list.append(["r180_%+04d" % deg, face + facing.rotated(Vector3.UP, deg_to_rad(float(deg))) * 1.8 + Vector3.UP * 0.06, 30.0])
			list.append(["ots_+000", face + facing.rotated(Vector3.UP, deg_to_rad(26.0)) * 1.17 + Vector3.UP * 0.08, 30.0])
			list.append(["tp_back", face - facing * 2.4 + facing.cross(Vector3.UP) * 0.6 + Vector3.UP * 0.75, 52.0])
			list.append(["tp_side", face + facing.cross(Vector3.UP) * 2.4 + Vector3.UP * 0.6, 52.0])
			list.append(["standing_behind", face - facing * 1.0 + Vector3.UP * 0.45, 30.0])
			list.append(["behind_close", face - facing * 0.75 + Vector3.UP * 0.3, 30.0])
			var runs := [] if varonly else [["", {}]]
			runs.append_array(variants)
			# (cards=a.bin,b.bin: each card set injected in turn, its shots tagged with its name)
			var csets: Array = Array(cards_bin.split(",")) if cards_bin != "" else [""]
			for cs in csets:
				var ctag: String = ("_" + String(cs).get_file().get_basename()) if cs != "" else ""
				if cs != "":
					print("[rg] cards injected ", cs, " ", load("res://tools/out/toma_like4/scripts/inject.gd").inject(npc.rig, cs))
					await wait(0.6)
				for s in list:
					if not only.is_empty() and not (s[0] in only):
						continue
					var from: Vector3 = s[1]
					npc.rig.set("_blink_t", 1.0e9)
					game.camera_rig.set_shot(from, face, s[2], from.distance_to(face), true)
					await wait(0.9)
					for r in runs:
						var back := {}
						if not (r[1] as Dictionary).is_empty():
							back = set_params(npc.rig, r[1])
							await wait(0.3)
						await shot("%s_%s%s%s%s_%s" % [tm, model, tag, ctag, ("_" + r[0]) if r[0] != "" else "", s[0]])
						if not back.is_empty():
							set_params(npc.rig, back)
	print("[rg] done")
	quit()
