class_name UITheme
extends RefCounted
## Le cahier de Mano (docs/DESIGN.md §5, docs/ART_DIRECTION.md): the four voices as shared FontVariation roles, the
## palette, and the small widget helpers every screen uses. Pen = Mano's ballpoint (Mynerve), marker = his
## felt-tip (Shantell Sans), print = the school's printed voice and the project font (Atkinson Hyperlegible
## Next), code = the PIE terminal (Atkinson Hyperlegible Mono). The fonts stay dynamic (no MSDF), so they are
## rasterised at the size they are shown, on Retina too.

const F := "res://assets/fonts/"
const PEN_FILE := F + "Mynerve-Regular.ttf"
const MARKER_FILE := F + "ShantellSans-VF.ttf"
const PRINT_FILE := F + "AtkinsonHyperlegibleNext-VF.ttf"
const PRINT_ITALIC_FILE := F + "AtkinsonHyperlegibleNext-Italic-VF.ttf"
const CODE_FILE := F + "AtkinsonHyperlegibleMono-VF.ttf"

# paper and inks (§5.2); contrast is measured against PAPER
const PAPER := Color("#faf8f2")
const PAPER_SHADE := Color("#ece8de")
const SEYES_LINE := Color("#b9afdd")
const SEYES_INTER := Color("#cbd8ee")
const GRID_5MM := Color("#bfcde0")
const MARGIN_RED := Color("#e0605a")
const INK_BLUE := Color("#233e94")        # everything Mano writes, 9.0:1
const INK_BLUE_SOFT := Color("#3a57b5")
const INK_RED := Color("#c2302b")         # dates, corrections
const MARKER_RED := Color("#d23a2c")      # the objective loop, focus marks
const INK_GREEN := Color("#1d7449")       # ticks
const INK_BLACK := Color("#25221e")       # marker labels
const PENCIL := Color("#55565c")          # places not visited yet
const FLUO := Color("#ffe94d")
const STICKY_YELLOW := Color("#fff07a")
const STICKY_PINK := Color("#ffc2d6")
const STICKY_MINT := Color("#c9f1da")
const TAPE := Color(0.937, 0.902, 0.812, 0.8)
# over the 3D scene: film white always carries an ink outline (white over a pale sky alone measures 1.22:1)
const FILM_WHITE := Color("#f7f2e8")
const INK_SHADOW := Color("#120e0a")
const SCRIM := Color("#1a1410")

## Short names for the keys whose own names are long, on key caps (action_key).
const KEY_NAMES := {KEY_ESCAPE: "Esc", KEY_SHIFT: "Shift", KEY_TAB: "Tab", KEY_SPACE: "Space", KEY_ENTER: "Enter", KEY_BACKSPACE: "Back"}

## Older names the minigames still use, resolved to the palette above.
const INK := FILM_WHITE
const MUTED := Color(0.969, 0.949, 0.91, 0.72)
const GOLD := Color("#ffd45c")   # Mano's own subtitle colour, not a general accent
const GOOD := Color(0.49, 0.84, 0.55)

static var pen: FontVariation           # Mynerve 400: journal, inner voice, objective, toasts, tips
static var marker: FontVariation        # Shantell INFM 100, BNCE 30, wght 650: headings, prompt verbs
static var marker_label: FontVariation  # wght 550: small labels (map)
static var marker_menu: FontVariation   # wght 700: menu items
static var marker_title: FontVariation  # wght 800, BNCE 60: titles, banners, chapter times
static var marker_calm: FontVariation   # INFM 60, BNCE 0, wght 500: dialogue choices
static var print_400: FontVariation     # Atkinson Next: subtitles, settings help, credits
static var print_500: FontVariation     # settings labels
static var print_700: FontVariation     # speaker names, key letters
static var print_italic: FontVariation  # asides
static var code: FontVariation          # Atkinson Mono 400: moulinette code
static var code_700: FontVariation      # verdicts
## The minigames' names for the same roles (they follow set_readable() too).
static var body: Font
static var body_semi: Font
static var bold: Font
static var display: Font
static var display_xb: Font
static var hand: Font
static var mono: Font
static var theme: Theme
static var readable := false


static func init() -> void:
	if theme:
		return
	pen = _fv(PEN_FILE, {})
	marker = _fv(MARKER_FILE, {"wght": 650, "INFM": 100, "BNCE": 30})
	marker_label = _fv(MARKER_FILE, {"wght": 550, "INFM": 100, "BNCE": 30})
	marker_menu = _fv(MARKER_FILE, {"wght": 700, "INFM": 100, "BNCE": 30})
	marker_title = _fv(MARKER_FILE, {"wght": 800, "INFM": 100, "BNCE": 60})
	marker_calm = _fv(MARKER_FILE, {"wght": 500, "INFM": 60, "BNCE": 0})
	print_400 = _fv(PRINT_FILE, {"wght": 400})
	print_500 = _fv(PRINT_FILE, {"wght": 500})
	print_700 = _fv(PRINT_FILE, {"wght": 700})
	print_italic = _fv(PRINT_ITALIC_FILE, {"wght": 400})
	code = _fv(CODE_FILE, {"wght": 400})   # the file's default is 200
	code_700 = _fv(CODE_FILE, {"wght": 700})
	# a glyph one voice lacks (→ in Atkinson, ✓ in Mynerve) comes from another voice, not from a system font
	var hands: Array[Font] = [load(MARKER_FILE), load(PRINT_FILE)]
	var prints: Array[Font] = [load(MARKER_FILE), load(PEN_FILE)]
	for f in [pen]:
		f.fallbacks = hands
	for f in [print_400, print_500, print_700, print_italic, code, code_700]:
		f.fallbacks = prints
	body = print_400
	body_semi = print_500
	bold = print_700
	display = marker
	display_xb = marker_title
	hand = pen
	mono = code
	set_readable(GameState.settings.get("readable_fonts", false))

	theme = Theme.new()
	theme.default_font = print_400
	theme.default_font_size = 22
	theme.set_color("font_color", "Label", FILM_WHITE)
	# buttons are words, not pills: the hovered or focused one gets a red pen underline
	var plain := StyleBoxEmpty.new()
	plain.content_margin_left = 6
	plain.content_margin_right = 6
	plain.content_margin_top = 4
	plain.content_margin_bottom = 8
	var under := PenStyle.make(PenStyle.Kind.UNDERLINE, MARKER_RED, 2.6, 3, Vector2(6, 4))
	under.content_margin_bottom = 8
	for st in ["normal", "disabled"]:
		theme.set_stylebox(st, "Button", plain)
	for st in ["hover", "pressed", "hover_pressed", "focus"]:
		theme.set_stylebox(st, "Button", under)
	theme.set_font("font", "Button", marker_menu)
	theme.set_font_size("font_size", "Button", 28)
	for c in ["font_color", "font_hover_color", "font_focus_color", "font_pressed_color", "font_hover_pressed_color"]:
		theme.set_color(c, "Button", FILM_WHITE)
	theme.set_color("font_disabled_color", "Button", Color(FILM_WHITE, 0.4))
	theme.set_color("font_outline_color", "Button", Color(INK_SHADOW, 0.85))
	theme.set_constant("outline_size", "Button", 6)
	# toggles: a pen-drawn square that gets a tick (the settings form on paper is V2-06)
	theme.set_icon("unchecked", "CheckBox", pen_icon(false))
	theme.set_icon("checked", "CheckBox", pen_icon(true))
	for st in ["normal", "hover", "pressed", "hover_pressed", "focus", "disabled"]:
		theme.set_stylebox(st, "CheckBox", under if st == "focus" else plain)
	# sliders: a thin ruled line and a dot
	var track := StyleBoxFlat.new()
	track.bg_color = Color(FILM_WHITE, 0.35)
	track.content_margin_top = 1
	track.content_margin_bottom = 1
	theme.set_stylebox("slider", "HSlider", track)
	var filled := StyleBoxFlat.new()
	filled.bg_color = Color(FILM_WHITE, 0.9)
	filled.content_margin_top = 1
	filled.content_margin_bottom = 1
	theme.set_stylebox("grabber_area", "HSlider", filled)
	theme.set_stylebox("grabber_area_highlight", "HSlider", filled)
	theme.set_icon("grabber", "HSlider", _dot(16, FILM_WHITE))
	theme.set_icon("grabber_highlight", "HSlider", _dot(18, MARKER_RED))


## One role: a FontVariation of `file` at the given axes (names such as "INFM" become OpenType tags).
static func _fv(file: String, axes: Dictionary) -> FontVariation:
	var fv := FontVariation.new()
	fv.base_font = load(file)
	var ts := TextServerManager.get_primary_interface()
	var tags := {}
	for k in axes:
		tags[ts.name_to_tag(k)] = axes[k]
	fv.variation_opentype = tags
	return fv


## Settings > "Readable fonts": the handwriting roles switch to the print face. The roles are shared
## resources, so every label that uses them follows.
static func set_readable(on: bool) -> void:
	if pen == null:
		return
	readable = on
	var printed: Font = load(PRINT_FILE)
	pen.base_font = printed if on else load(PEN_FILE)
	for f in [marker, marker_label, marker_menu, marker_title, marker_calm]:
		f.base_font = printed if on else load(MARKER_FILE)


## Text over the 3D scene: film white (or a speaker colour) with an ink outline and a soft shadow.
static func over_scene(l: Control, outline := 6, shadow := 0.45) -> Control:
	l.add_theme_color_override("font_outline_color", Color(INK_SHADOW, 0.85))
	l.add_theme_constant_override("outline_size", outline)
	l.add_theme_color_override("font_shadow_color", Color(INK_SHADOW, shadow))
	l.add_theme_constant_override("shadow_offset_x", 0)
	l.add_theme_constant_override("shadow_offset_y", 2)
	l.add_theme_constant_override("shadow_outline_size", outline + 8)
	return l


## A flat box. Corners stay at 4 px or less: no rounded glass cards over the scene.
static func box(c: Color, radius := 0, border := Color(0, 0, 0, 0), pad := 14) -> StyleBoxFlat:
	var s := StyleBoxFlat.new()
	s.bg_color = c
	s.set_corner_radius_all(mini(radius, 4))
	if border.a > 0:
		s.border_color = border
		s.set_border_width_all(1)
	s.content_margin_left = pad + 4
	s.content_margin_right = pad + 4
	s.content_margin_top = pad * 0.6
	s.content_margin_bottom = pad * 0.6
	s.anti_aliasing = true
	return s


static func label(text: String, size := 20, font: Font = null, color := INK) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", size)
	if font:
		l.add_theme_font_override("font", font)
	l.add_theme_color_override("font_color", color)
	return l


## A drop shadow plus a thin ink outline (the minigames' text over the scene: film white over a pale wall
## alone is unreadable).
static func shadowed(l: Label, size := 2, alpha := 0.7) -> Label:
	l.add_theme_color_override("font_shadow_color", Color(0, 0, 0, alpha))
	l.add_theme_constant_override("shadow_offset_x", 0)
	l.add_theme_constant_override("shadow_offset_y", size)
	l.add_theme_constant_override("shadow_outline_size", size * 3)
	l.add_theme_color_override("font_outline_color", Color(INK_SHADOW, 0.8))
	l.add_theme_constant_override("outline_size", 4)
	return l


## A key drawn as a sketched keycap round the live letter (Atkinson 700), so rebinding still shows.
static func key_cap(text: String, size := 16) -> PanelContainer:
	var p := PanelContainer.new()
	var sb := PenStyle.make(PenStyle.Kind.BOX, FILM_WHITE, 1.8, text.length(), Vector2(8, 1))
	p.add_theme_stylebox_override("panel", sb)
	var l := over_scene(label(text, maxi(size, 18), print_700, FILM_WHITE), 5, 0.35) as Label
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	p.add_child(l)
	return p


## The key for `action` as the player's hardware prints it: the live binding's first key in the keyboard's
## layout (W on QWERTY, Z on AZERTY), or the pad button while a controller is in use.
static func action_key(action: String) -> String:
	if GameState.using_pad:
		return {"interact": "A", "confirm": "A", "back": "B", "journal": "View", "map": "Y", "wardrobe": "X", "pause": "Menu", "photo_mode": "D↑", "phone": "D↓", "run": "L3"}.get(action, "A")
	if InputMap.has_action(action):
		for ev in InputMap.action_get_events(action):
			var k := ev as InputEventKey
			if k == null:
				continue
			var code := k.keycode
			if k.physical_keycode != KEY_NONE:
				# the headless display server has no keyboard layout to ask
				code = k.physical_keycode if DisplayServer.get_name() == "headless" else DisplayServer.keyboard_get_label_from_physical(k.physical_keycode)
			return KEY_NAMES.get(code, OS.get_keycode_string(code))
	return {"interact": "E", "confirm": "E", "back": "Esc", "journal": "Tab", "map": "M", "wardrobe": "F", "pause": "Esc", "photo_mode": "P", "phone": "Q", "run": "Shift"}.get(action, "E")


## A checkbox drawn in pen: a sketched square, ticked or not.
static func pen_icon(checked: bool) -> ImageTexture:
	var strokes: Array = [PenStyle.make(PenStyle.Kind.BOX, FILM_WHITE, 2.0, 5).path(Rect2(4, 4, 20, 20))]
	if checked:
		strokes.append(PackedVector2Array([Vector2(7.5, 13.5), Vector2(10, 16.5), Vector2(12.5, 20), Vector2(17, 11.5), Vector2(25, 2.5)]))
	return stroke_texture(Vector2i(28, 28), strokes, FILM_WHITE, 2.2)


## Pen strokes (polylines inside `size`) rasterised at 3× and shown at `size`, so they stay sharp on Retina;
## an ink under-stroke keeps them readable over the scene (`under` false: none, for marks on paper).
static func stroke_texture(size: Vector2i, strokes: Array, color: Color, width: float, under := true) -> ImageTexture:
	const K := 3
	var w := size.x * K
	var h := size.y * K
	var dist := PackedFloat32Array()
	dist.resize(w * h)
	dist.fill(1e6)
	var reach := (width * 0.5 + 2.0) * K
	for poly: PackedVector2Array in strokes:
		for i in poly.size() - 1:
			var a := poly[i] * K
			var b := poly[i + 1] * K
			var ab := b - a
			var l2 := maxf(ab.length_squared(), 1e-6)
			for y in range(maxi(int(minf(a.y, b.y) - reach), 0), mini(int(maxf(a.y, b.y) + reach) + 1, h)):
				for x in range(maxi(int(minf(a.x, b.x) - reach), 0), mini(int(maxf(a.x, b.x) + reach) + 1, w)):
					var p := Vector2(x + 0.5, y + 0.5)
					var d := p.distance_to(a + ab * clampf((p - a).dot(ab) / l2, 0.0, 1.0))
					if d < dist[y * w + x]:
						dist[y * w + x] = d
	var img := Image.create(w, h, false, Image.FORMAT_RGBA8)
	var r_in := width * 0.5 * K
	var r_out := r_in + 1.3 * K
	for y in h:
		for x in w:
			var d := dist[y * w + x]
			var a_out := clampf(r_out - d + 0.5, 0.0, 1.0) * 0.7 if under else 0.0
			if a_out <= 0.0 and d > r_in + 1.0:
				continue
			var a_in := clampf(r_in - d + 0.5, 0.0, 1.0)
			var c := INK_SHADOW.lerp(color, a_in) if under else Color(color)
			c.a = maxf(a_out, a_in) * (1.0 if under else color.a)
			img.set_pixel(x, y, c)
	var tex := ImageTexture.create_from_image(img)
	tex.set_size_override(size)
	return tex


static func _dot(size: int, c: Color) -> ImageTexture:
	const K := 3
	var img := Image.create(size * K, size * K, false, Image.FORMAT_RGBA8)
	var r := size * K * 0.5
	for y in size * K:
		for x in size * K:
			var d := Vector2(x + 0.5 - r, y + 0.5 - r).length()
			var ring := clampf(r - d, 0.0, 1.0)
			var core := clampf(r - 1.5 * K - d, 0.0, 1.0)
			var col := INK_SHADOW.lerp(c, core)
			col.a = ring
			img.set_pixel(x, y, col)
	var tex := ImageTexture.create_from_image(img)
	tex.set_size_override(Vector2i(size, size))
	return tex
