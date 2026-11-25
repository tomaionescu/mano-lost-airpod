class_name CreditsRoll
extends CanvasLayer
## The credits (V2-27, docs/DESIGN.md §3.5 chapter 5): while the song picked for the playlist plays on, the camera rises from
## the steps over the courtyard toward rue Pasteur and KB1's lit windows (world.json shots credits_start ->
## credits_end), the names go up the right of the screen in print over the night, and the night's film prints go up
## the left (Ishita's disposable camera: the tour's photos and the group photo, plus copies of photo-mode shots, all
## in GameState.film_dir()) through scripts/fx/film.gdshader (faded, warm, a light leak, grain). Any key after the
## first seconds runs it to its end. `finished` once the screen is black again.

signal finished

const DURATION := 46.0        # seconds, about the song's first verse and chorus
const SKIP_AFTER := 2.5       # a key this soon is the one that ended the last line: it does not skip
const FADE_IN := 1.2
const FADE_OUT := 1.6
const TEXT_W := 620.0
const PRINT_W := 340.0
const FILM_SHADER := preload("res://scripts/fx/film.gdshader")

var game
var shot_a := {}
var shot_b := {}
var _t := 0.0
var _ending := false
var _root: Control
var _text: VBoxContainer
var _prints: VBoxContainer
var _shade: ColorRect
## What the roll shows, for autotests: the prints' paths and the names in order.
var shown_prints: Array = []
var names: Array = []


## The prints in the film folder, in the order they were taken: film_01.png..., photo-mode copies (photo_*.png),
## then the group photo last.
static func print_paths() -> Array:
	var dir := GameState.film_dir()
	var out: Array = []
	var d := DirAccess.open(ProjectSettings.globalize_path(dir))
	if d == null:
		return out
	var files: Array = []
	for f in d.get_files():
		if String(f).ends_with(".png"):
			files.append(String(f))
	files.sort()
	for f in files:
		if f != "group.png":
			out.append(dir.path_join(f))
	if "group.png" in files:
		out.append(dir.path_join("group.png"))
	return out


func _ready() -> void:
	layer = 18
	UITheme.init()
	_root = Control.new()
	_root.set_anchors_preset(Control.PRESET_FULL_RECT)
	_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_root.theme = UITheme.theme
	add_child(_root)
	# a soft dark band behind the names, so print over a lit window stays readable
	_shade = ColorRect.new()
	_shade.color = Color(UITheme.SCRIM, 0.0)
	_shade.set_anchors_preset(Control.PRESET_FULL_RECT)
	_shade.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_root.add_child(_shade)
	_text = VBoxContainer.new()
	_text.add_theme_constant_override("separation", 6)
	_text.custom_minimum_size = Vector2(TEXT_W, 0)
	_text.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_root.add_child(_text)
	_prints = VBoxContainer.new()
	_prints.add_theme_constant_override("separation", 46)
	_prints.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_root.add_child(_prints)
	_build_text()
	_build_prints()
	_root.modulate.a = 0.0
	_root.create_tween().tween_property(_root, "modulate:a", 1.0, FADE_IN)


func _line(text: String, size: int, font: Font, color := UITheme.FILM_WHITE, align := HORIZONTAL_ALIGNMENT_CENTER) -> Label:
	var l := UITheme.label(text, size, font, color)
	l.horizontal_alignment = align
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.custom_minimum_size = Vector2(TEXT_W, 0)
	l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	UITheme.over_scene(l, 6, 0.5)
	_text.add_child(l)
	return l


func _gap(h: float) -> void:
	var c := Control.new()
	c.custom_minimum_size = Vector2(0, h)
	c.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_text.add_child(c)


func _build_text() -> void:
	_line("Mano & the Lost AirPod", 52, UITheme.marker_title)
	_gap(10)
	_line(Menus.dedication(), 30, UITheme.pen)
	_gap(40)
	_line("Starring, as themselves", 30, UITheme.marker)
	for id in ["mano", "toma", "anisha", "ian", "silvia", "ishita", "cristina", "joaquin"]:
		var info: Dictionary = game._speaker_info(id) if game else {"name": id.capitalize(), "color": UITheme.FILM_WHITE}
		_line(String(info.get("name", id)), 34, UITheme.marker_menu, info.get("color", UITheme.FILM_WHITE))
		names.append(String(info.get("name", id)))
	_gap(30)
	_line("And, made up for the night", 26, UITheme.marker)
	_line("Karim (BDE), Mme Dupont, ACU Léo, Chloé (BDE), Théo, Yanis, Inès, M. Bernard, the sleepy SUP, the piscine survivor, the waiting student, the duck whisperer", 24, UITheme.print_400)
	_gap(30)
	var song := String(GameState.flags.get("playlist", ""))
	if song != "":
		_line("The song for the steps", 26, UITheme.marker)
		_line("\"%s\", %s. Picked by Mano, for Toma." % [Chat.song_title(song), Chat.song_artist(song)], 24, UITheme.print_400)
		_gap(30)
	var shots := int(GameState.flags.get("film_shots", 0)) + (1 if bool(GameState.flags.get("group_photo", false)) else 0)
	if shots > 0:
		_line("Ishita's film", 26, UITheme.marker)
		_line("%d photo%s on a disposable camera. Developed in a week." % [shots, "" if shots == 1 else "s"], 24, UITheme.print_400)
		_gap(30)
	for row in Menus.CREDITS:
		_line(String(row[0]), 26, UITheme.marker)
		_line(String(row[1]), 22, UITheme.print_400, Color(UITheme.FILM_WHITE, 0.9))
		_gap(18)
	_gap(40)
	_line("Thank you for listening. With both ears.", 30, UITheme.pen)


func _build_prints() -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = 1015
	var list := print_paths()
	for i in list.size():
		var path := String(list[i])
		var img := Image.load_from_file(ProjectSettings.globalize_path(path))
		if img == null or img.is_empty():
			continue
		shown_prints.append(path)
		var group := path.get_file() == "group.png"
		var w := PRINT_W * (1.25 if group else 1.0)
		var h := w * float(img.get_height()) / maxf(img.get_width(), 1.0)
		# the white border of a print, its picture through the film shader, a pen caption under the group photo
		var paper := PanelContainer.new()
		var sb := StyleBoxFlat.new()
		sb.bg_color = Color("#f4efe4")
		sb.content_margin_left = 12
		sb.content_margin_right = 12
		sb.content_margin_top = 12
		sb.content_margin_bottom = 34 if group else 16
		sb.shadow_color = Color(0, 0, 0, 0.45)
		sb.shadow_size = 14
		sb.shadow_offset = Vector2(4, 8)
		paper.add_theme_stylebox_override("panel", sb)
		paper.mouse_filter = Control.MOUSE_FILTER_IGNORE
		var v := VBoxContainer.new()
		v.add_theme_constant_override("separation", 4)
		v.mouse_filter = Control.MOUSE_FILTER_IGNORE
		var pic := TextureRect.new()
		pic.texture = ImageTexture.create_from_image(img)
		pic.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		pic.stretch_mode = TextureRect.STRETCH_SCALE
		pic.custom_minimum_size = Vector2(w, h)
		pic.mouse_filter = Control.MOUSE_FILTER_IGNORE
		var m := ShaderMaterial.new()
		m.shader = FILM_SHADER
		m.set_shader_parameter("seed", float(i) * 3.7)
		m.set_shader_parameter("leak", rng.randf_range(0.25, 0.7))
		m.set_shader_parameter("leak_from", [Vector2(1, 0), Vector2(0, 0), Vector2(1, 1), Vector2(0, 0.5)][rng.randi() % 4])
		pic.material = m
		v.add_child(pic)
		if group:
			var cap := UITheme.label("the steps, 23:52. all eight.", 24, UITheme.pen, UITheme.INK_BLUE)
			cap.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
			v.add_child(cap)
		paper.add_child(v)
		var holder := Control.new()
		holder.custom_minimum_size = Vector2(w + 24.0, h + (58.0 if group else 28.0))
		holder.mouse_filter = Control.MOUSE_FILTER_IGNORE
		holder.add_child(paper)
		paper.rotation_degrees = rng.randf_range(-3.5, 3.5)
		paper.position = Vector2(rng.randf_range(-14.0, 14.0), 0)
		_prints.add_child(holder)


func _process(dt: float) -> void:
	if game == null:
		return
	_t += dt
	var vp := _root.get_viewport_rect().size
	var k := clampf(_t / DURATION, 0.0, 1.0)
	# the names and the prints go up at one pace, from below the screen to above it
	var th := _text.get_combined_minimum_size().y
	var ph := _prints.get_combined_minimum_size().y
	var right := vp.x * (0.5 if shown_prints.is_empty() else 0.68) - TEXT_W * 0.5
	_text.position = Vector2(right, lerpf(vp.y + 40.0, -th - 40.0, k))
	_prints.position = Vector2(vp.x * 0.2 - PRINT_W * 0.5, lerpf(vp.y + 140.0, -ph - 40.0, k))
	_shade.color.a = 0.28 * clampf(_t / FADE_IN, 0.0, 1.0)
	# the camera: from the steps, up and over the courtyard toward KB1 (its look follows a beat behind its rise)
	if not shot_a.is_empty() and not shot_b.is_empty():
		var e := k * k * (3.0 - 2.0 * k)
		var el := clampf((k - 0.08) / 0.92, 0.0, 1.0)
		el = el * el * (3.0 - 2.0 * el)
		var from := WorldData.vec(shot_a.from).lerp(WorldData.vec(shot_b.from), e)
		var look := WorldData.vec(shot_a.look).lerp(WorldData.vec(shot_b.look), el)
		var fov := lerpf(float(shot_a.get("fov", 40.0)), float(shot_b.get("fov", 46.0)), e)
		game.camera_rig.set_shot(from, look, fov, -1.0, true)
	if _t >= DURATION and not _ending:
		_end()


func skip() -> void:
	if _t < SKIP_AFTER or _ending:
		return
	print("[credits] skipped at %.1f s" % _t)
	_end()


func _end() -> void:
	_ending = true
	var tw := create_tween()
	tw.tween_property(_root, "modulate:a", 0.0, FADE_OUT * 0.6)
	tw.parallel().tween_property(game.hud.fade, "color:a", 1.0, FADE_OUT)
	tw.tween_callback(func(): finished.emit())


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("confirm") or event.is_action_pressed("pause") or event.is_action_pressed("back"):
		get_viewport().set_input_as_handled()
		skip()
