class_name Ink
extends RefCounted
## Pen marks on paper shared by the notebook screens (docs/DESIGN.md §5.4, docs/ART_DIRECTION.md): handwriting that
## writes itself on, a line ruled with a ruler, a pencil line, the red "circle the answer" loop. Everything is a
## live stroke or a live label, never an image, so it stays sharp on Retina. Settings > Reduce motion makes
## every write-on and draw-on instant.

const WRITE_ON := preload("res://scripts/fx/write_on.gdshader")
const CPS := 25.0   # handwriting goes on at about 25 characters a second

static var _paper_theme: Theme


static func calm() -> bool:
	return GameState.settings.get("reduce_motion", false)


## The theme for controls on paper (the settings form, the title page, the notebook's étiquette): ink colours
## instead of film white, no outline, red pen marks for focus without the dark under-stroke the scene needs,
## printed checkboxes that get a blue ballpoint tick, sliders as a printed scale with a pencil tick.
static func paper_theme() -> Theme:
	if _paper_theme:
		return _paper_theme
	UITheme.init()
	var t := Theme.new()
	t.default_font = UITheme.print_400
	t.default_font_size = 22
	t.set_color("font_color", "Label", UITheme.INK_BLACK)
	var plain := StyleBoxEmpty.new()
	plain.content_margin_left = 6
	plain.content_margin_right = 6
	plain.content_margin_top = 4
	plain.content_margin_bottom = 8
	var under := PenStyle.make(PenStyle.Kind.UNDERLINE, UITheme.MARKER_RED, 2.4, 3, Vector2(6, 4))
	under.content_margin_bottom = 8
	under.shadow = Color(0, 0, 0, 0)
	for st in ["normal", "disabled"]:
		t.set_stylebox(st, "Button", plain)
	for st in ["hover", "pressed", "hover_pressed", "focus"]:
		t.set_stylebox(st, "Button", under)
	t.set_font("font", "Button", UITheme.marker_menu)
	t.set_font_size("font_size", "Button", 28)
	for c in ["font_color", "font_hover_color", "font_focus_color", "font_pressed_color", "font_hover_pressed_color"]:
		t.set_color(c, "Button", UITheme.INK_BLACK)
	t.set_color("font_disabled_color", "Button", Color(UITheme.INK_BLACK, 0.35))
	t.set_constant("outline_size", "Button", 0)
	# a printed box; ticked in Mano's blue ballpoint
	var box := [PackedVector2Array([Vector2(5, 5), Vector2(23, 5), Vector2(23, 23), Vector2(5, 23), Vector2(5, 5)])]
	var tick := [PackedVector2Array([Vector2(7.5, 13.5), Vector2(10.5, 17.5), Vector2(13.0, 21.5), Vector2(17.5, 12.0), Vector2(26.0, 2.0)])]
	var empty_box := UITheme.stroke_texture(Vector2i(28, 28), box, Color(UITheme.INK_BLACK, 0.75), 1.3, false)
	var ticked := empty_box.get_image()
	var ink := UITheme.stroke_texture(Vector2i(28, 28), tick, UITheme.INK_BLUE, 2.4, false).get_image()
	ticked.blend_rect(ink, Rect2i(Vector2i.ZERO, ink.get_size()), Vector2i.ZERO)
	var ticked_tex := ImageTexture.create_from_image(ticked)
	ticked_tex.set_size_override(Vector2i(28, 28))
	t.set_icon("unchecked", "CheckBox", empty_box)
	t.set_icon("checked", "CheckBox", ticked_tex)
	var loop := paper_loop(8, Vector2(8, 4))
	for st in ["normal", "hover", "pressed", "hover_pressed", "disabled"]:
		t.set_stylebox(st, "CheckBox", plain)
	t.set_stylebox("focus", "CheckBox", loop)
	# a slider is a printed scale: a thin rule with five ticks, and Mano's pencil mark on it
	var rule := StyleBoxFlat.new()
	rule.bg_color = Color(UITheme.INK_BLACK, 0.5)
	rule.content_margin_top = 0.75
	rule.content_margin_bottom = 0.75
	t.set_stylebox("slider", "HSlider", rule)
	t.set_stylebox("grabber_area", "HSlider", StyleBoxEmpty.new())
	t.set_stylebox("grabber_area_highlight", "HSlider", StyleBoxEmpty.new())
	# a focused scale (keys, pad) is underlined in red pen, not boxed by the engine's default focus frame
	var slider_focus := PenStyle.make(PenStyle.Kind.UNDERLINE, UITheme.MARKER_RED, 2.2, 6, Vector2(0, 0))
	slider_focus.shadow = Color(0, 0, 0, 0)
	t.set_stylebox("focus", "HSlider", slider_focus)
	var mark := [PackedVector2Array([Vector2(7.0, 4.0), Vector2(6.4, 14.0), Vector2(5.6, 24.0)])]
	t.set_icon("grabber", "HSlider", UITheme.stroke_texture(Vector2i(12, 28), mark, Color(UITheme.PENCIL, 0.95), 3.0, false))
	t.set_icon("grabber_highlight", "HSlider", UITheme.stroke_texture(Vector2i(12, 28), mark, UITheme.MARKER_RED, 3.2, false))
	var notch := [PackedVector2Array([Vector2(2.0, 1.0), Vector2(2.0, 9.0)])]
	t.set_icon("tick", "HSlider", UITheme.stroke_texture(Vector2i(4, 10), notch, Color(UITheme.INK_BLACK, 0.55), 1.0, false))
	_paper_theme = t
	return t


## Writes a one-line label on from left to right over `seconds` (0: at the pen's speed), after `delay`.
## Returns the tween, or null when it appears at once (Reduce motion).
static func write_on(l: Label, seconds := 0.0, delay := 0.0) -> Tween:
	var m := ShaderMaterial.new()
	m.shader = WRITE_ON
	l.material = m
	if calm():
		return null
	var w := maxf(l.get_combined_minimum_size().x, 1.0)
	var soft := clampf(w * 0.08, 6.0, 22.0)
	m.set_shader_parameter("soft", soft)
	m.set_shader_parameter("reveal", -soft)
	var t := seconds if seconds > 0.0 else maxf(l.text.length() / CPS, 0.12)
	var tw := l.create_tween()
	tw.tween_interval(delay)
	tw.tween_method(func(v: float): m.set_shader_parameter("reveal", v), -soft, w + soft * 2.0, t)
	return tw


## A line ruled along a ruler from `a` to `b`: dead straight, a touch heavier where the pen came down.
static func ruler_line(ci: CanvasItem, a: Vector2, b: Vector2, color: Color, width := 2.0, progress := 1.0) -> void:
	if progress <= 0.0:
		return
	var e := a.lerp(b, clampf(progress, 0.0, 1.0))
	ci.draw_line(a, e, color, width, true)
	ci.draw_line(a, a.lerp(e, 0.06), Color(color, color.a * 0.5), width + 0.8, true)


## A pencil line: graphite grey that catches the paper's grain, so its darkness wavers along the stroke.
static func pencil_line(ci: CanvasItem, a: Vector2, b: Vector2, progress := 1.0, seed_value := 3, width := 2.2) -> void:
	if progress <= 0.0:
		return
	var rng := RandomNumberGenerator.new()
	rng.seed = seed_value
	var n := maxi(int(a.distance_to(b) / 9.0), 2)
	var last := int(ceil(n * clampf(progress, 0.0, 1.0)))
	var nrm := (b - a).orthogonal().normalized()
	var wob := 0.0
	for i in last:
		var t0 := float(i) / n
		var t1 := minf(float(i + 1) / n, progress)
		wob = clampf(wob + rng.randf_range(-0.25, 0.25), -0.7, 0.7)
		var alpha := rng.randf_range(0.55, 0.85)
		ci.draw_line(a.lerp(b, t0) + nrm * wob, a.lerp(b, t1) + nrm * wob, Color(UITheme.PENCIL, alpha), width, true)


## The red pen loop round a focused word on paper (no dark under-stroke: that is for marks over the scene).
static func paper_loop(seed_value := 1, margins := Vector2(14, 6)) -> PenStyle:
	var p := PenStyle.make(PenStyle.Kind.LOOP, UITheme.MARKER_RED, 2.4, seed_value, margins)
	p.shadow = Color(0, 0, 0, 0)
	return p


## Draws `style` on over `seconds` ("circle the answer": 160 ms).
static func draw_on(owner: Node, style: PenStyle, seconds := 0.16) -> void:
	if calm() or not owner.is_inside_tree():
		style.progress = 1.0
		return
	style.progress = 0.0
	owner.create_tween().tween_property(style, "progress", 1.0, seconds).set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_OUT)
