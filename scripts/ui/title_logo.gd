class_name TitleLogo
extends Control
## The game's logo as a die-cut sticker (docs/DESIGN.md §5.5, §7): 720 px wide at 1080p, stuck on at -3°, on the
## title, the notebook's cover (loading, pause) and the credits.
## The built-in lettering: "Mano &" over "the lost AirPod"
## set in-engine in Mano's marker (Shantell Sans 800), each letter turned and lifted a little by a fixed seed,
## so it is the same every run; the dot of the i in AirPod is a tiny AirPod. No generated lettering.
## A hand-lettered logo replaces it: the lettering as an SVG (ink on a transparent background, the letters only)
## saved as res://assets/ui/logo.svg. Every logo then shows it, rasterised at the size it is drawn, with the
## white vinyl border, the shadow and the tilt added here; without the file the built-in lettering shows.

signal landed

const LOGO := "res://assets/ui/logo.svg"
const WIDTH := 600.0      # 720 px at 1080p
const BORDER := 15.0      # the white vinyl round the letters
const TILT := -3.0

var width := WIDTH
var ink := UITheme.INK_BLACK
## Where to read the hand-lettered logo from (a test can point it elsewhere).
var logo_path := LOGO
var _glyphs: Array = []   # [String char, Vector2 baseline pos, int size, float rot, float scale]
var _dot := {}            # the AirPod dotting the i: {"at": Vector2, "s": float}
var _cut: DieCut = null
var _cut_rect := Rect2()

static var _svg_cache := {}   # path + pixel width -> DieCut
static var _font: FontVariation   # its own Shantell 800: a logo stays a logo under Settings > Readable fonts


## The lettering's font: marker_title's axes, but not the shared role that Readable fonts swaps to print.
static func lettering_font() -> FontVariation:
	if _font == null:
		_font = UITheme._fv(UITheme.MARKER_FILE, {"wght": 800, "INFM": 100, "BNCE": 60})
	return _font


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	_build()
	pivot_offset = size * 0.5
	rotation_degrees = TILT


## The logo's height at its width (for laying out round it).
func logo_height() -> float:
	return size.y


func _build() -> void:
	_glyphs.clear()
	_dot = {}
	_cut = _load_svg()
	if _cut:
		var k := (width - BORDER * 2.0) / _cut.art_px.x   # the same overall width as the built-in lettering
		_cut_rect = Rect2(Vector2(BORDER, BORDER), _cut.art_px * k)
		size = _cut_rect.size + Vector2(BORDER, BORDER) * 2.0
		custom_minimum_size = size
		queue_redraw()
		return
	var f: Font = lettering_font()
	var inner := width - BORDER * 2.0
	var line2 := "the lost AirPod"
	var s2 := int(floor(80.0 * inner / maxf(_line_width(f, line2, 80), 1.0)))
	var s1 := mini(int(s2 * 1.62), int(floor(80.0 * inner / maxf(_line_width(f, "Mano &", 80), 1.0))))
	var rng := RandomNumberGenerator.new()
	rng.seed = 1742   # the minute Mano wakes up
	var y := BORDER + f.get_ascent(s1) * 0.92
	_set_line(f, "Mano &", s1, Vector2(BORDER + 4.0, y), rng)
	y += f.get_descent(s1) * 0.35 + f.get_ascent(s2) * 0.98
	_set_line(f, line2, s2, Vector2(BORDER + inner - _line_width(f, line2, s2), y), rng)
	size = Vector2(width, y + f.get_descent(s2) + BORDER)
	custom_minimum_size = size
	queue_redraw()


func _line_width(f: Font, text: String, s: int) -> float:
	var w := 0.0
	for ch in text:
		w += f.get_char_size(ch.unicode_at(0), s).x * 0.97
	return w


func _set_line(f: Font, text: String, s: int, at: Vector2, rng: RandomNumberGenerator) -> void:
	var x := at.x
	for i in text.length():
		var ch := text[i]
		var code := ch.unicode_at(0)
		# a hand varies each letter a little: size, height, slant (the size by transform, so the font caches one size)
		var k := rng.randf_range(0.97, 1.04)
		var lift := rng.randf_range(-2.0, 2.0) * s / 80.0
		var rot := deg_to_rad(rng.randf_range(-3.2, 3.2))
		# the i of AirPod loses its dot to a tiny AirPod (when the font has a dotless i)
		if ch == "i" and text.ends_with("AirPod") and i == text.length() - 5 and f.has_char(0x131):
			ch = "ı"
			var cw := f.get_char_size(0x131, s).x * k
			_dot = {"at": Vector2(x + cw * 0.52, at.y + lift - s * k * 0.73), "s": s * k / 80.0}
		_glyphs.append([ch, Vector2(x, at.y + lift), s, rot, k])
		x += f.get_char_size(code, s).x * k * 0.97


## Sticks the logo on: it lands a little big and turned, then settles (a sticker lands in 160 ms).
func land(delay := 0.0) -> void:
	if Ink.calm():
		landed.emit()
		return
	_set_land(0.0)
	modulate.a = 0.0
	var tw := create_tween().set_parallel()
	tw.tween_property(self, "modulate:a", 1.0, 0.08).set_delay(delay)
	tw.tween_method(_set_land, 0.0, 1.0, 0.16).set_delay(delay).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	tw.chain().tween_callback(func(): landed.emit())


func _set_land(k: float) -> void:
	scale = Vector2.ONE * lerpf(1.12, 1.0, k)
	rotation = deg_to_rad(TILT) + lerpf(deg_to_rad(6.0), 0.0, k)


func _draw() -> void:
	if _cut:
		_cut.draw(self, _cut_rect, Vector2(3, 5), 0.3)
		return
	var f: Font = lettering_font()
	var vinyl := Color("#fefefb")
	# shadow, then the white vinyl grown round every letter (it merges into one die-cut shape), then the ink
	for pass_i in 3:
		for g: Array in _glyphs:
			var ch: String = g[0]
			var p: Vector2 = g[1]
			var s: int = g[2]
			var c := Vector2(f.get_char_size(ch.unicode_at(0), s).x * 0.5, -s * 0.3)
			draw_set_transform_matrix(Transform2D(g[3], Vector2.ONE * float(g[4]), 0.0, p + c) * Transform2D(0.0, -c))
			match pass_i:
				0:
					draw_char_outline(f, Vector2(3, 5), ch, s, int(BORDER * 2.0 + 4.0), Color(UITheme.INK_SHADOW, 0.28))
					draw_char(f, Vector2(3, 5), ch, s, Color(UITheme.INK_SHADOW, 0.28))
				1:
					draw_char_outline(f, Vector2.ZERO, ch, s, int(BORDER * 2.0), vinyl)
					draw_char(f, Vector2.ZERO, ch, s, vinyl)
				2:
					draw_char(f, Vector2.ZERO, ch, s, ink)
		draw_set_transform_matrix(Transform2D.IDENTITY)
		if not _dot.is_empty():
			_draw_pod(pass_i)


## The tiny AirPod dotting the i: a bud and its stem, in the same three passes as the letters.
func _draw_pod(pass_i: int) -> void:
	var at: Vector2 = _dot.at
	var k: float = _dot.s
	var bud := PackedVector2Array()
	for i in 20:
		var a := TAU * i / 20.0
		bud.append(at + Vector2(cos(a) * 7.0, sin(a) * 6.0).rotated(-0.5) * k)
	var stem_a := at + Vector2(2.5, 3.5) * k
	var stem_b := at + Vector2(6.5, 17.0) * k
	match pass_i:
		0:
			draw_circle(at + Vector2(3, 5) + Vector2(3, 6) * k, (BORDER + 9.0) * k, Color(UITheme.INK_SHADOW, 0.28), true, -1.0, true)
		1:
			draw_circle(at + Vector2(3, 6) * k, (BORDER + 8.0) * k, Color("#fefefb"), true, -1.0, true)
		2:
			draw_colored_polygon(bud, ink)
			draw_line(stem_a, stem_b, ink, 5.5 * k, true)
			draw_circle(stem_b, 2.75 * k, ink, true, -1.0, true)
			draw_circle(at + Vector2(-2.2, -1.0) * k, 1.6 * k, Color("#fefefb"), true, -1.0, true)   # the speaker grille


## The hand-lettered logo, if there is one: rasterised from the SVG at the pixels it covers on this screen
## (twice its units on Retina), or the imported texture in an exported build.
func _load_svg() -> DieCut:
	var px_w := width * _pixels_per_unit()
	var key := "%s@%d" % [logo_path, int(px_w)]
	if _svg_cache.has(key):
		return _svg_cache[key]
	var img: Image = null
	if FileAccess.file_exists(logo_path):
		var src := FileAccess.get_file_as_string(logo_path)
		var probe := Image.new()
		if src != "" and probe.load_svg_from_string(src, 1.0) == OK and probe.get_width() > 0:
			img = Image.new()
			img.load_svg_from_string(src, px_w / probe.get_width())
	elif ResourceLoader.exists(logo_path):
		var t := load(logo_path) as Texture2D
		if t:
			img = t.get_image()
			if img and img.is_compressed():
				img.decompress()
	var cut: DieCut = null
	if img and img.get_width() > 0:
		cut = DieCut.bake(img, BORDER * img.get_width() / width)
	_svg_cache[key] = cut
	return cut


## Screen pixels per UI unit: 1.2 in a 1080p window, 2.4 on a Retina one (the canvas stretch).
func _pixels_per_unit() -> float:
	if is_inside_tree():
		return maxf(get_viewport().get_final_transform().get_scale().x, 1.0)
	return 2.4
