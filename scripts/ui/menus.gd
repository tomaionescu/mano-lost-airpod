class_name Menus
extends CanvasLayer
## Full-screen UI as things in Mano's notebook (docs/DESIGN.md §5.5): loading and pause are the notebook's cover and
## its étiquette, the title menu a Seyès page taped under the logo sticker, the settings a printed school form
## filled in by hand, the credits a printed sheet, the ending the notebook's last page. Also the journal, the
## map, the wardrobe and photo mode. The paper, tape and pen marks are PaperSheet, Tape, NotebookCover and Ink.

## Loading tips on a sticky note, in Mano's words; {action} becomes that action's live key.
const TIPS := [
	["{run} to jog. The campus is bigger than it looks.", "arrow"],
	["Twelve golden rubber ducks hide on campus. Rubber-duck debugging, but make it a collection.", "duck"],
	["{map}: the campus map. {journal}: my notebook.", "map"],
	["Talk to everyone. Students know things. Mostly gossip.", "smile"],
	["{photo_mode} for photo mode. I deserve a good picture.", "camera"],
]
## Where the last save was, the way Mano writes it under Continue ("last time: cour Pasteur, 18:03"); by ZONE_ id.
const PLACE_NOTES := {"street": "rue Pasteur", "court": "cour Pasteur", "passage": "the passage", "amphi": "Amphi 4",
	"volt_gf": "the accueil", "volt_f1": "Bâtiment Voltaire", "sm14": "SM14", "sm15": "SM15", "cafe": "the cafet'",
	"under": "the Under"}
## Everyone the game is made for, in the credits and on the last page.
const FRIENDS := ["Mano", "Toma", "Anisha", "Ian", "Silvia", "Ishita", "Cristina", "Joaquin"]
const MENU_SIZE := 38            # menu words: Shantell 700, 46 px at 1080p
const ETIQUETTE_SIZE := 34       # the pause menu on the étiquette's lines
const PAGE_ROW := 24.0           # the title page's Seyès squares; a menu word takes two of them
const BLUR_TINT := Color(0.07, 0.055, 0.045)
const PAUSE_TINT := Color(0.2, 0.13, 0.08)   # the pause blur is warmer and less dark
const FORM_SIZE := Vector2(800, 840)         # the printed credits sheet
const SETTINGS_SIZE := Vector2(1340, 848)    # the settings form: two printed columns, nothing to scroll
const FORM_PAD := 50.0
const FORM_COL := 600.0
const FORM_GAP := 40.0
const FORM_LABEL_W := 230.0
const FORM_BUTTON_SIZE := 30
const PREVIEW_COLOR := Color("#6fa3ff")      # Toma's subtitle colour (CastDefs), in the live preview

var game
var root: Control
var current: Control = null
var _load_line: Control = null   # the pencil line under the étiquette (loading progress)
var _load_progress := 0.0
var _photo: Dictionary = {}
var _wardrobe_sel := 0
var _wardrobe_t := 0.0
var _map_view: Control
var _blur: ColorRect
var _back := Callable()          # Esc / B on a screen opened from another one (settings, credits)
var _scroll: ScrollContainer = null   # the credits sheet, scrolled with the arrow keys


func _ready() -> void:
	layer = 20
	process_mode = Node.PROCESS_MODE_ALWAYS
	UITheme.init()
	root = Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.theme = UITheme.theme
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(root)
	_blur = ColorRect.new()
	_blur.set_anchors_preset(Control.PRESET_FULL_RECT)
	_blur.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var sm := ShaderMaterial.new()
	var sh := Shader.new()
	sh.code = """shader_type canvas_item;
uniform sampler2D screen : hint_screen_texture, filter_linear_mipmap;
uniform float amount = 3.0;
uniform float dim = 0.45;
uniform vec3 tint = vec3(0.07, 0.055, 0.045);
void fragment() { vec3 c = textureLod(screen, SCREEN_UV, amount).rgb; COLOR = vec4(mix(c, tint, dim), 1.0); }"""
	sm.shader = sh
	_blur.material = sm
	_blur.visible = false
	root.add_child(_blur)


func close() -> void:
	if current:
		current.queue_free()
		current = null
	_blur.visible = false
	_photo = {}
	_back = Callable()
	_scroll = null
	_load_line = null
	set_process(false)


## Shows `c` full screen in place of the current screen. `fade` 0: the screen animates its own paper in.
func _swap(c: Control, blur := false, dim := 0.45, fade := 0.25, tint := BLUR_TINT) -> void:
	if current:
		current.queue_free()
	current = c
	_back = Callable()
	_scroll = null
	_blur.visible = blur
	var m := _blur.material as ShaderMaterial
	m.set_shader_parameter("dim", dim)
	m.set_shader_parameter("tint", Vector3(tint.r, tint.g, tint.b))
	c.set_anchors_preset(Control.PRESET_FULL_RECT)
	c.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(c)
	if fade > 0.0:
		c.modulate.a = 0.0
		var tw := c.create_tween()
		tw.tween_property(c, "modulate:a", 1.0, fade)


# ------------------------------------------------------------------ the notebook's cover
## Mano's notebook closed, with the logo sticker on it and its étiquette (Nom : Mano, Matière : retrouver mon
## AirPod) and `blank` more étiquette lines for whatever is written there.
func _cover(blank: int, cover_size: Vector2) -> NotebookCover:
	var cover := NotebookCover.new()
	cover.blank_lines = blank
	cover.line_h = 56.0
	cover.label_center = 0.6 if blank > 0 else 0.62
	cover.size = cover_size
	cover.pivot_offset = cover_size * 0.5
	cover.theme = Ink.paper_theme()
	var logo := TitleLogo.new()
	logo.width = cover_size.x * 0.7
	logo.position = Vector2(cover_size.x * 0.13, 40.0)
	cover.add_child(logo)
	return cover


## Centres `c` (of size `s`) in its parent with anchors, so it stays centred when the window changes.
static func _center(c: Control, s: Vector2, ofs := Vector2.ZERO) -> void:
	_pin(c, Vector2(0.5, 0.5), ofs - s * 0.5, s)


## Pins `c` to a point of its parent (`anchor`, 0-1 of the parent's size), its top-left `ofs` from that point,
## its size `s`. The size is passed in: reading c.size between the offsets would see it half set.
static func _pin(c: Control, anchor: Vector2, ofs: Vector2, s: Vector2) -> void:
	c.anchor_left = anchor.x
	c.anchor_right = anchor.x
	c.anchor_top = anchor.y
	c.anchor_bottom = anchor.y
	c.offset_left = ofs.x
	c.offset_right = ofs.x + s.x
	c.offset_top = ofs.y
	c.offset_bottom = ofs.y + s.y


## A sticky note in Mano's pen with a doodle, sized to its longest line.
func _note(text: String, doodle: String, color := UITheme.STICKY_YELLOW) -> StickyNote:
	var n := StickyNote.toast(text, doodle, color)
	var widest := 0.0
	for line in text.split("\n"):
		widest = maxf(widest, UITheme.pen.get_string_size(line, HORIZONTAL_ALIGNMENT_LEFT, -1, StickyNote.SIZE).x)
	n.max_w = StickyNote.PAD * 2.0 + StickyNote.DOODLE + StickyNote.GAP + widest + 24.0
	return n


# ------------------------------------------------------------------ loading
## The notebook lying on a dark desk under a lamp: the étiquette, a pencil line ruled under it as the campus
## loads, and one tip on a sticky note.
func show_loading() -> void:
	var c := Control.new()
	var desk := ColorRect.new()
	desk.color = Color("#17120e")
	desk.set_anchors_preset(Control.PRESET_FULL_RECT)
	desk.mouse_filter = Control.MOUSE_FILTER_IGNORE
	c.add_child(desk)
	var lamp := TextureRect.new()
	lamp.texture = _radial_tex(Color(1.0, 0.8, 0.55, 0.2), Color(1.0, 0.8, 0.55, 0.0))
	lamp.set_anchors_preset(Control.PRESET_FULL_RECT)
	lamp.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	lamp.stretch_mode = TextureRect.STRETCH_SCALE
	lamp.mouse_filter = Control.MOUSE_FILTER_IGNORE
	c.add_child(lamp)
	var cover := _cover(0, Vector2(500, 660))
	_center(cover, cover.size, Vector2(-20, 6))
	cover.rotation_degrees = -2.5
	c.add_child(cover)
	_load_line = Control.new()
	_load_line.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_load_line.draw.connect(func():
		var lr := cover.label_rect
		var y := lr.end.y + 44.0
		Ink.pencil_line(_load_line, Vector2(lr.position.x + 10.0, y), Vector2(lr.end.x - 10.0, y - 1.5), _load_progress, 11))
	cover.add_child(_load_line)
	var tip: Array = TIPS[randi() % TIPS.size()]
	var text: String = tip[0]
	for a in ["run", "map", "journal", "photo_mode"]:
		text = text.replace("{%s}" % a, UITheme.action_key(a))
	var note := _note(text, tip[1])
	note.max_w = minf(note.max_w, 330.0)
	cover.add_child(note)
	_swap(c, false, 0.45, 0.0)
	# stuck on the cover's lower corner, hanging over its edge
	note.base = Vector2(cover.size.x - note.size.x * 0.62, cover.size.y - note.size.y - 26.0)
	note.land(Vector2(0, 18))
	_load_progress = 0.0


func set_loading_progress(f: float) -> void:
	if _load_line:
		_load_progress = lerpf(_load_progress, f, 0.25)
		_load_line.queue_redraw()


# ------------------------------------------------------------------ title
## The title over the live Amphi 4 scene (main.show_title): the logo sticker top-left and the menu written in
## marker on a Seyès page taped bottom-left, Continue with a pen note of where and when the save was. No blurb,
## no pill, no eyebrow, no controls footer. `fresh` plays the sticker and the page landing.
func show_title(has_save: bool, fresh := true) -> void:
	var c := Control.new()
	var logo := TitleLogo.new()
	logo.position = Vector2(58, 40)
	c.add_child(logo)
	var items: Array = []   # [word, action, pen note under it]
	if has_save:
		items.append(["Continue", func(): game.continue_game(), _last_time()])
	items.append(["New game", func(): game.request_new_game(), ""])
	# chapter select (V2-30): once a chapter's snapshot exists (chapter 0, the cold open, is not replayed from here)
	if GameState.chapter_saves().any(func(n): return int(n) >= 1):
		items.append(["Chapters", func(): show_chapters(), ""])
	items.append(["Settings", func(): show_settings(func(): show_title(GameState.has_save(), false)), ""])
	items.append(["Credits", func(): show_credits(func(): show_title(GameState.has_save(), false)), ""])
	items.append(["Quit", func(): get_tree().quit(), ""])
	var page := _menu_page(items)
	var ps := page.size
	_pin(page, Vector2(0, 1), Vector2(82, -58 - ps.y), ps)
	c.add_child(page)
	_swap(c, false, 0.45, 0.0 if fresh else 0.15)
	var first: Button = page.get_meta("first")
	if fresh:
		logo.land(0.45)
		_paper_in(page, 0.1)
	first.grab_focus.call_deferred()


## Chapter select (V2-30): the same taped page, one chapter per word ("3 Blue Hour"), with a pen note of where and
## when it opens and what of its ducks, film and moments the night has found. A replay starts from the chapter's
## snapshot with that night's choices, keeps everything found since, and skips the cold open and the dream
## (main.start_chapter(n, true)). Esc or B goes back to the title.
func show_chapters() -> void:
	var c := Control.new()
	var logo := TitleLogo.new()
	logo.position = Vector2(58, 40)
	c.add_child(logo)
	var finds := Collectibles.best_known()
	var items: Array = []
	for n in GameState.chapter_saves():
		if int(n) < 1 or not Chapters.has(int(n)):
			continue
		var ch: Dictionary = Chapters.get_chapter(int(n))
		var card: Dictionary = ch.get("card", {})
		var k: Dictionary = Collectibles.in_chapter(int(n), finds)
		var bits: Array = []
		for pair in [["duck", k.ducks], ["photo", k.film], ["moment", k.moments]]:
			var v: Vector2i = pair[1]
			if v.y > 0:
				bits.append("%s %d/%d" % [pair[0] + ("s" if v.y > 1 else ""), v.x, v.y])
		var note := "%s, %s   %s" % [String(card.get("time", ch.get("clock", ""))), String(card.get("place", "")), "  ".join(bits)]
		var num := int(n)
		var where := "%s, %s" % [String(card.get("time", ch.get("clock", ""))), String(card.get("place", ""))]
		items.append([String(card.get("chapter", "%d %s" % [num, ch.get("title", "")])), func(): confirm_replay(num, where), note])
	var back := func(): show_title(GameState.has_save(), false)
	if items.is_empty():
		back.call()
		return
	var page := _menu_page(items, "Which part of the night?")
	var ps := page.size
	_pin(page, Vector2(0, 1), Vector2(82, -58 - ps.y), ps)
	c.add_child(page)
	_swap(c, false, 0.45, 0.15)
	_back = back
	var first: Button = page.get_meta("first")
	first.grab_focus.call_deferred()


## New game over a save (V2-33): the same taped page asks first. "Keep my night" is circled to begin with, and
## Esc or B keeps the night too.
func confirm_new_game() -> void:
	_confirm(["Start again", func(): game.new_game(true), ""], "Start again? Tonight's progress goes.",
		func(): show_title(GameState.has_save(), false))


## Chapter select over a night in progress asks first, as New game does: a replay starts from the chapter's
## snapshot and the save in progress (where Mano is, the side stories since) goes; "Keep my night", Esc or B go back
## to the chapter list. With no night in progress (the last one ended: show_recap cleared the save) it starts at once.
func confirm_replay(n: int, where: String) -> void:
	if not GameState.has_save():
		game.start_chapter(n, true)
		return
	_confirm(["Go back", func(): game.start_chapter(n, true), "the ducks, photos and moments stay"],
		"Back to %s? Tonight's progress goes." % where, show_chapters)


## The taped page with a question in pen: `yes` [word, action, note] and "Keep my night" (circled to begin with;
## Esc or B is `keep` too).
func _confirm(yes: Array, question: String, keep: Callable) -> void:
	var c := Control.new()
	var logo := TitleLogo.new()
	logo.position = Vector2(58, 40)
	c.add_child(logo)
	var page := _menu_page([yes, ["Keep my night", keep, ""]], question)
	var ps := page.size
	_pin(page, Vector2(0, 1), Vector2(82, -58 - ps.y), ps)
	c.add_child(page)
	_swap(c, false, 0.45, 0.15)
	_back = keep
	var buttons: Array = page.get_meta("buttons")
	(buttons[1] as Button).grab_focus.call_deferred()


## The title menu: one word per two Seyès squares, in marker, a pen note under an item that has one; the page
## was ripped out of the notebook along its left edge and is taped on at the top corners. `heading`: a line in
## pen above the words (the New game question).
func _menu_page(items: Array, heading := "") -> PaperSheet:
	var page := PaperSheet.new()
	page.row = PAGE_ROW
	page.first_line = PAGE_ROW * 1.9
	page.margin_x = 52.0
	page.edges = [PaperSheet.Edge.CUT, PaperSheet.Edge.CUT, PaperSheet.Edge.CUT, PaperSheet.Edge.TORN]
	page.seed_value = 41
	page.theme = Ink.paper_theme()
	var f: Font = UITheme.marker_menu
	var line := 1
	var buttons: Array[Button] = []
	var widest := 0.0
	if heading != "":
		var hl := UITheme.label(heading, 28, UITheme.pen, UITheme.INK_BLUE)
		hl.position = Vector2(page.margin_x + 14.0, page.line_y(line) - UITheme.pen.get_ascent(28))
		hl.mouse_filter = Control.MOUSE_FILTER_IGNORE
		page.add_child(hl)
		widest = UITheme.pen.get_string_size(heading, HORIZONTAL_ALIGNMENT_LEFT, -1, 28).x
		line += 3
	for i in items.size():
		var it: Array = items[i]
		var b := _paper_button(page, it[0], it[1], MENU_SIZE, 30 + i)
		_on_line(b, page.margin_x + 14.0, page.line_y(line), f, MENU_SIZE)
		widest = maxf(widest, _word_w(it[0], MENU_SIZE))
		buttons.append(b)
		if String(it[2]) != "":
			# Mano's note under the word, on the blue line nearly two squares down, clear of the word's red loop
			var note := UITheme.label(it[2], 25, UITheme.pen, UITheme.INK_BLUE)
			note.position = Vector2(page.margin_x + 22.0, page.line_y(line) + PAGE_ROW * 1.75 - UITheme.pen.get_ascent(25))
			note.mouse_filter = Control.MOUSE_FILTER_IGNORE
			page.add_child(note)
			widest = maxf(widest, UITheme.pen.get_string_size(it[2], HORIZONTAL_ALIGNMENT_LEFT, -1, 25).x + 8.0)
			line += 2
		line += 2
	_chain_focus(buttons)
	page.size = Vector2(maxf(page.margin_x + 14.0 + widest + 48.0, 360.0), page.line_y(line - 2) + PAGE_ROW * 1.6)
	page.pivot_offset = page.size * 0.5
	page.rotation_degrees = 1.4
	Tape.stick(page, Vector2(14.0, 4.0), 92.0, -38.0, 3, 28.0)
	Tape.stick(page, Vector2(page.size.x - 12.0, 6.0), 92.0, 34.0, 4, 28.0)
	page.set_meta("first", buttons[0])
	page.set_meta("buttons", buttons)
	return page


## A word in marker on paper: a button whose text sits on `baseline` like handwriting on a ruled line; the focused
## one is circled in red pen, the loop drawing itself on.
func _paper_button(parent: Control, text: String, cb: Callable, size := MENU_SIZE, seed_value := 1) -> Button:
	var b := Button.new()
	b.text = text
	b.theme = Ink.paper_theme()
	b.add_theme_font_size_override("font_size", size)
	var loop := Ink.paper_loop(seed_value, Vector2(14, 5))
	var none := StyleBoxEmpty.new()   # the same margins as the loop, so circling a word never moves it
	none.content_margin_left = 14
	none.content_margin_right = 14
	none.content_margin_top = 5
	none.content_margin_bottom = 5
	for st in ["normal", "hover", "pressed", "hover_pressed", "disabled"]:
		b.add_theme_stylebox_override(st, none)
	b.add_theme_stylebox_override("focus", loop)
	b.mouse_entered.connect(func(): b.grab_focus())
	b.focus_entered.connect(func():
		Ink.draw_on(b, loop)
		Sfx.ui("ui_hover", -14.0))
	b.pressed.connect(func():
		Sfx.ui("ui_click", -4.0)
		cb.call())
	parent.add_child(b)
	return b


## Puts a button's text baseline on `baseline` at `x` (its loop's margin hangs to the left of it).
static func _on_line(b: Button, x: float, baseline: float, f: Font, size: int) -> void:
	b.position = Vector2(x - 14.0, baseline - 5.0 - f.get_ascent(size))


## The width of a _paper_button word with its loop's margins, from the font: a button outside the tree has no
## theme yet, so its own minimum size would come out as the margins alone.
static func _word_w(text: String, size: int) -> float:
	return UITheme.marker_menu.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, size).x + 28.0


## Paper comes in the way the notebook does: up 60 units, turning from -4° to its own angle, 380 ms.
func _paper_in(c: Control, delay := 0.0) -> void:
	if Ink.calm():
		return
	c.modulate.a = 0.0
	await get_tree().process_frame   # an anchored sheet has its place only once the layout has run
	if not is_instance_valid(c):
		return
	var rest := c.rotation_degrees
	var at := c.position
	c.position = at + Vector2(0, 60)
	c.rotation_degrees = rest - 4.0
	var tw := c.create_tween().set_parallel()
	tw.tween_property(c, "modulate:a", 1.0, 0.12).set_delay(delay)
	tw.tween_property(c, "position", at, 0.38).set_delay(delay).set_trans(Tween.TRANS_QUART).set_ease(Tween.EASE_OUT)
	tw.tween_property(c, "rotation_degrees", rest, 0.38).set_delay(delay).set_trans(Tween.TRANS_QUART).set_ease(Tween.EASE_OUT)
	Sfx.ui("journal_open", -12.0)


## "last time: cour Pasteur, 18:03": the place of the save and its time, in Mano's words.
func _last_time() -> String:
	var data = GameState.read_save()
	if not data is Dictionary:
		return ""
	var flags: Dictionary = data.get("flags", {})
	var clock := ""
	var c = flags.get("clock", null)
	if c is String:
		clock = c
	elif c is float or c is int:   # minutes after midnight
		clock = "%02d:%02d" % [int(c) / 60 % 24, int(c) % 60]
	else:
		clock = String(WorldEnv.TIMES.get(flags.get("time", WorldEnv.DEFAULT_TIME), {}).get("clock", ""))
	var place := ""
	var p: Array = data.get("pos", [])
	if p.size() == 3 and game and game.binder:
		var z: Dictionary = game.binder.zone_at(Vector3(p[0], p[1], p[2]))
		var zid := String(z.get("id", ""))
		place = WorldData.zone_name(zid) if WorldData.zone_name(zid) != "" else PLACE_NOTES.get(zid, String(z.get("label", "")))
	var parts := PackedStringArray()
	for s in [place, clock]:
		if s != "":
			parts.append(s)
	return "last time: " + ", ".join(parts) if not parts.is_empty() else ""


# ------------------------------------------------------------------ pause
## The closed notebook at an angle on the left of the screen, over a warmer and lighter blur (docs/DESIGN.md §5.5):
## the menu is written on its étiquette's blank lines, and a sticky note beside the L/R AirPod doodle says how
## the night is going. `fresh` plays the notebook sliding in (not when coming back from the settings). Over a
## conversation, a cutscene or a minigame (Main.pause) the menu is Resume and Settings only.
func show_pause(fresh := true) -> void:
	game.enter_menu("pause")
	get_tree().paused = true
	var c := Control.new()
	var items := [
		["Resume", func(): game.resume()],
		["Journal", func():
			get_tree().paused = false
			show_journal()],
		["Settings", func(): show_settings(func(): show_pause(false))],
		["Save & quit", func():
			game.save()
			get_tree().paused = false
			game.show_title()],
	]
	if not game.paused_from.is_empty():
		items = [items[0], items[2]]   # in the middle of a scene: nothing to save, and the journal would let it run on
	var cs := Vector2(500, 650)
	var cover := _cover(items.size(), cs)
	_pin(cover, Vector2(0, 0.5), Vector2(150, -cs.y * 0.5), cs)
	cover.rotation_degrees = -3.5
	c.add_child(cover)
	_swap(c, true, 0.3, 0.0 if fresh else 0.12, PAUSE_TINT)
	# the étiquette is laid out now that the cover is on screen: the menu goes on its blank lines
	var x := cover.label_rect.position.x + 34.0
	var buttons: Array[Button] = []
	for i in items.size():
		var b := _paper_button(cover, items[i][0], items[i][1], ETIQUETTE_SIZE, 50 + i)
		_on_line(b, x, cover.line_y(cover.fields.size() + i) + 2.0, UITheme.marker_menu, ETIQUETTE_SIZE)
		buttons.append(b)
	_chain_focus(buttons)
	var mins := int(GameState.play_time / 60.0)
	var found: int = game.ducks.count()
	var note := _note("%d minute%s on campus\n%d duck%s out of %d" % [mins, "" if mins == 1 else "s", found,
		"" if found == 1 else "s", game.ducks.total()], "airpod")
	cover.add_child(note)
	note.base = Vector2(cover.size.x - 70.0, cover.size.y * 0.68)
	if fresh:
		_paper_in(cover)
		note.land(Vector2(30, 0))
	else:
		note.land(Vector2.ZERO)
	set_process(true)
	buttons[0].grab_focus.call_deferred()


## Up and down move round the words in a loop.
static func _chain_focus(buttons: Array[Button]) -> void:
	for i in buttons.size():
		buttons[i].focus_neighbor_top = buttons[i].get_path_to(buttons[(i - 1 + buttons.size()) % buttons.size()])
		buttons[i].focus_neighbor_bottom = buttons[i].get_path_to(buttons[(i + 1) % buttons.size()])


# ------------------------------------------------------------------ settings
## Settings on a printed school form (une fiche) that Mano filled in by hand (docs/DESIGN.md §5.5, docs/ART_DIRECTION.md): the
## sections in his marker, the printed labels in Atkinson, printed boxes he ticked in blue ballpoint, sliders as
## a printed scale with his pencil mark and the value in pen, choices as words with the chosen one circled in
## red, and a live preview of the subtitles. Everything changes in place; Esc or B goes back.
func show_settings(back: Callable) -> void:
	var c := Control.new()
	var ss := SETTINGS_SIZE
	var sheet := _printed_sheet(ss, 23)
	_center(sheet, ss, Vector2(0, 4))
	sheet.rotation_degrees = 0.4
	c.add_child(sheet)
	_form_head(sheet, "Settings")
	var cols: Array[VBoxContainer] = []
	for i in 2:
		var col := VBoxContainer.new()
		col.position = Vector2(FORM_PAD + i * (FORM_COL + FORM_GAP), 104)
		col.custom_minimum_size = Vector2(FORM_COL, 0)
		col.add_theme_constant_override("separation", 2)
		sheet.add_child(col)
		cols.append(col)
	var v := cols[0]
	_heading(v, "Controls", true)
	_slider(v, "Mouse sensitivity", "mouse_sensitivity", 0.2, 3.0, 0.05)
	_slider(v, "Controller sensitivity", "pad_sensitivity", 0.3, 2.5, 0.05)
	_toggle(v, "Invert camera Y", "invert_y")
	_heading(v, "Sound")
	_slider(v, "Master volume", "volume_master", 0.0, 1.0, 0.01)
	_slider(v, "Music", "volume_music", 0.0, 1.0, 0.01)
	_slider(v, "Sound effects", "volume_sfx", 0.0, 1.0, 0.01)
	_slider(v, "Voices", "volume_voice", 0.0, 1.0, 0.01)
	_heading(v, "Picture")
	_slider(v, "Field of view", "fov", 44.0, 70.0, 1.0)
	_choices(v, "Graphics", "quality", [["low", "low"], ["medium", "medium"], ["high", "high"], ["ultra", "ultra"]])
	_toggle(v, "Film grain", "film_grain")
	v = cols[1]
	_heading(v, "Subtitles and text", true)
	var preview := _subtitle_preview()
	_choices(v, "Subtitle size", "subtitles_size", [["S", 0.84], ["M", 1.0], ["L", 1.2], ["XL", 1.5]], func(): _fill_preview(preview))
	v.add_child(preview)
	_toggle(v, "Typewriter text", "typewriter")
	_heading(v, "Accessibility")
	_toggle(v, "Readable fonts", "readable_fonts", func(on: bool):
		UITheme.set_readable(on)
		_fill_preview(preview))
	_toggle(v, "Reduce motion", "reduce_motion")
	_toggle(v, "Objective marker", "waypoint")
	var done := _paper_button(sheet, "Back", func(): back.call(), FORM_BUTTON_SIZE, 61)
	_on_line(done, FORM_PAD + 4.0, ss.y - 36.0, UITheme.marker_menu, FORM_BUTTON_SIZE)
	var reset := _paper_button(sheet, "Reset to defaults", func():
		GameState.reset_settings()
		UITheme.set_readable(GameState.settings.get("readable_fonts", false))
		show_settings(back), FORM_BUTTON_SIZE, 62)
	_on_line(reset, FORM_PAD + 150.0, ss.y - 36.0, UITheme.marker_menu, FORM_BUTTON_SIZE)
	done.focus_neighbor_right = done.get_path_to(reset)
	reset.focus_neighbor_left = reset.get_path_to(done)
	_swap(c, true, 0.5, 0.18)
	_back = back
	done.grab_focus.call_deferred()


## A sheet of plain printed paper (a school form, the credits): a guillotine-cut white sheet, no ruling.
func _printed_sheet(s: Vector2, seed_value: int) -> PaperSheet:
	var sheet := PaperSheet.new()
	sheet.ruling = PaperSheet.Ruling.PLAIN
	sheet.margin_x = -1.0
	sheet.seed_value = seed_value
	sheet.lift = 1.5
	sheet.size = s
	sheet.pivot_offset = s * 0.5
	sheet.theme = Ink.paper_theme()
	return sheet


## The printed head of a form: its title, a rule across the sheet and "Nom :" with Mano's name on the dotted line.
func _form_head(sheet: PaperSheet, title: String) -> void:
	var head := UITheme.label(title, 30, UITheme.print_700, UITheme.INK_BLACK)
	head.position = Vector2(FORM_PAD, 34)
	sheet.add_child(head)
	var field := UITheme.label("Nom" + NotebookCover.NBSP + ":", 18, UITheme.print_500, Color(UITheme.INK_BLACK, 0.8))
	var fx := sheet.size.x - FORM_PAD - 250.0
	field.position = Vector2(fx, 50)
	sheet.add_child(field)
	var mano := UITheme.label("Mano", 30, UITheme.pen, UITheme.INK_BLUE)
	mano.position = Vector2(fx + 66.0, 72.0 - UITheme.pen.get_ascent(30))
	sheet.add_child(mano)
	var print_ink := Control.new()
	print_ink.mouse_filter = Control.MOUSE_FILTER_IGNORE
	print_ink.draw.connect(func():
		var y := 88.0
		print_ink.draw_line(Vector2(FORM_PAD, y), Vector2(sheet.size.x - FORM_PAD, y), Color(UITheme.INK_BLACK, 0.7), 1.2, true)
		var x := fx + 50.0
		while x < sheet.size.x - FORM_PAD:
			print_ink.draw_line(Vector2(x, 73.0), Vector2(minf(x + 1.6, sheet.size.x - FORM_PAD), 73.0), Color(UITheme.INK_BLACK, 0.5), 1.2, true)
			x += 5.0)
	sheet.add_child(print_ink)


## A section of the form, headed in Mano's marker.
func _heading(parent: Control, text: String, first := false) -> void:
	var l := UITheme.label(text, 28, UITheme.marker, UITheme.INK_BLACK)
	l.custom_minimum_size = Vector2(0, 44 if first else 64)
	l.vertical_alignment = VERTICAL_ALIGNMENT_BOTTOM
	parent.add_child(l)


## One printed line of the form: the label in Atkinson 500 on the left, what Mano filled in on the right.
func _form_row(parent: Control, text: String) -> HBoxContainer:
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", 14)
	h.custom_minimum_size = Vector2(0, 46)
	var l := UITheme.label(text, 22, UITheme.print_500, UITheme.INK_BLACK)
	l.custom_minimum_size = Vector2(FORM_LABEL_W, 0)
	l.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	h.add_child(l)
	parent.add_child(h)
	return h


## A printed scale (a rule with five ticks) with Mano's pencil mark on it and the value in pen beside it.
func _slider(parent: Control, text: String, key: String, lo: float, hi: float, step: float) -> void:
	var h := _form_row(parent, text)
	var s := HSlider.new()
	s.min_value = lo
	s.max_value = hi
	s.step = step
	s.value = GameState.settings[key]
	s.tick_count = 5
	s.ticks_on_borders = true
	s.custom_minimum_size = Vector2(220, 30)
	s.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	var val := UITheme.label(_value_text(s.value, step, hi), 26, UITheme.pen, UITheme.INK_BLUE)
	val.custom_minimum_size = Vector2(72, 0)
	val.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	s.value_changed.connect(func(x: float):
		val.text = _value_text(x, step, hi)
		GameState.set_setting(key, x))
	h.add_child(s)
	h.add_child(val)


## Volumes read as a percentage, other values with a French decimal comma (1,25).
static func _value_text(x: float, step: float, hi: float) -> String:
	if hi <= 1.0:
		return "%d %%" % int(round(x * 100.0))
	if step >= 1.0:
		return str(int(round(x)))
	return str(snappedf(x, step)).replace(".", ",")


## A setting with a few named values ([word, value]): the words in marker, the chosen one circled in red pen
## (the loop draws itself on when it moves). `changed` runs after a new value is set.
func _choices(parent: Control, text: String, key: String, options: Array, changed := Callable()) -> void:
	var h := _form_row(parent, text)
	h.add_theme_constant_override("separation", 9)
	var group := ButtonGroup.new()
	for opt: Array in options:
		var b := Button.new()
		b.text = String(opt[0])
		b.toggle_mode = true
		b.button_group = group
		b.button_pressed = _same(GameState.settings.get(key), opt[1])
		b.add_theme_font_override("font", UITheme.marker)
		b.add_theme_font_size_override("font_size", 26)
		var loop := Ink.paper_loop(String(opt[0]).length() + 5, Vector2(10, 4))
		var none := StyleBoxEmpty.new()   # the loop's margins, so circling a word never moves it
		none.content_margin_left = 10
		none.content_margin_right = 10
		none.content_margin_top = 4
		none.content_margin_bottom = 4
		for st in ["normal", "hover", "disabled"]:
			b.add_theme_stylebox_override(st, none)
		for st in ["pressed", "hover_pressed"]:
			b.add_theme_stylebox_override(st, loop)
		b.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		b.toggled.connect(func(on: bool):
			if on:
				Ink.draw_on(b, loop))
		b.pressed.connect(func():
			GameState.set_setting(key, opt[1])
			Sfx.ui("ui_click", -8.0)
			if changed.is_valid():
				changed.call())
		h.add_child(b)


## A printed box Mano ticks in blue ballpoint.
func _toggle(parent: Control, text: String, key: String, also := Callable()) -> void:
	var h := _form_row(parent, text)
	var b := CheckBox.new()
	b.button_pressed = GameState.settings.get(key, false)
	b.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	b.toggled.connect(func(on: bool):
		GameState.set_setting(key, on)
		Sfx.ui("ui_click", -8.0)
		if also.is_valid():
			also.call(on))
	h.add_child(b)


static func _same(a, b) -> bool:
	if (a is float or a is int) and (b is float or b is int):
		return is_equal_approx(float(a), float(b))
	return a == b


## The live subtitle preview: a strip of the scene's dark taped onto the form, with a real subtitle card on it
## (Dialogue.make_label) at the chosen size and font.
func _subtitle_preview() -> Control:
	var strip := ColorRect.new()
	strip.color = UITheme.SCRIM
	strip.custom_minimum_size = Vector2(0, 112)
	strip.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var l := Dialogue.make_label()
	l.name = "Line"
	var w := FORM_COL - 30.0   # a little narrower than in the game, to fit the column
	l.custom_minimum_size.x = w
	# pinned to the strip's centre with no height of its own: it grows round the centre as the size changes
	l.set_anchors_preset(Control.PRESET_CENTER)
	l.offset_left = -w * 0.5
	l.offset_right = w * 0.5
	l.offset_top = 0.0
	l.offset_bottom = 0.0
	l.grow_vertical = Control.GROW_DIRECTION_BOTH
	strip.add_child(l)
	Tape.stick(strip, Vector2(10.0, 4.0), 70.0, -32.0, 9, 24.0)   # taped onto the form
	Tape.stick(strip, Vector2(FORM_COL - 12.0, 4.0), 70.0, 28.0, 10, 24.0)
	_fill_preview(strip)
	return strip


func _fill_preview(strip: Control) -> void:
	var l := strip.get_node("Line") as RichTextLabel
	Dialogue.fill_line(l, "toma", "Toma", PREVIEW_COLOR, "One AirPod? Of course.", Dialogue.subtitle_size(),
		Dialogue.arrow_texture(0))
	strip.custom_minimum_size.y = maxf(112.0, Dialogue.subtitle_size() * 2.7 + 26.0)


# ------------------------------------------------------------------ credits
## The printed credits, after the dedication to the eight FRIENDS that Mano writes at the top of the sheet.
const CREDITS := [
	["Made at", "EPITA, Le Kremlin-Bicêtre. Every friend in the game is played by themselves."],
	["Engine", "Godot Engine 4.7 (MIT)"],
	["Campus", "Footprints and heights from OpenStreetMap (© OpenStreetMap contributors, ODbL), the French cadastre (DGFiP, Etalab) and IGN BD TOPO (Licence Ouverte 2.0)."],
	["Title lettering", "For now set in Shantell Sans, until Toma or Mano letter the logo by hand."],
	["Characters", "MakeHuman / MPFB (CC0). Clothing by Elvaerwyn, Mindfront, punkduck, culturalibre and DredNicolson (CC-BY), MRT, Namuhekam and spamrakuen (CC0). Hair, faces and outfits fitted for this game."],
	["Motion capture", "Carnegie Mellon University Graphics Lab Motion Capture Database (mocap.cs.cmu.edu). Bandai Namco Research Motion Dataset (CC BY-NC 4.0)."],
	["Textures and skies", "Poly Haven and ambientCG (CC0)."],
	["Music", "\"Almost Bliss\", \"Evening\", \"Morning\", \"Raving Energy\", \"Sneaky Snitch\", \"Study And Relax\" - Kevin MacLeod (incompetech.com). Licensed under Creative Commons: By Attribution 4.0 License. http://creativecommons.org/licenses/by/4.0/"],
	["Sound effects", "Kenney (kenney.nl) and Freesound contributors (CC0). Full list in assets/audio/CREDITS.md."],
	["Voices", "The fictional staff and students speak with synthetic voices: Higgsfield preset voices, Qwen Audio TTS (Alibaba Cloud). Nobody's voice was cloned, and the friends have none: their lines wait for them to record."],
	["Opening dream", "The first half is rendered in the game; the second half was generated with Higgsfield (Wan 3.0) from two frames of the empty Amphi 4 rendered in the game. Nobody's photo or likeness was used."],
	["Fonts", "Mynerve, © 2022 The Mynerve Project Authors (Carolina Short).\nShantell Sans, © 2022 The Shantell Sans Project Authors (Shantell Martin, Arrow Type).\nAtkinson Hyperlegible Next and Atkinson Hyperlegible Mono, © 2020-2024 their Project Authors (Braille Institute of America).\nAll under the SIL Open Font License 1.1; the licence texts are in assets/fonts/licenses."],
]


## "Made for Mano, Toma, …, Cristina and Joaquin.": the dedication, in the credits and on the last page.
static func dedication() -> String:
	return "Made for %s and %s." % [", ".join(PackedStringArray(FRIENDS.slice(0, FRIENDS.size() - 1))), FRIENDS[-1]]


## The credits on a printed sheet (Atkinson): the logo sticker stuck over its top edge, the dedication to the
## eight friends in Mano's pen, then the printed list. The arrow keys and the wheel scroll it; Esc or B goes back.
func show_credits(back: Callable) -> void:
	var c := Control.new()
	var ss := FORM_SIZE
	var sheet := _printed_sheet(ss, 29)
	_center(sheet, ss, Vector2(0, 14))
	sheet.rotation_degrees = -0.4
	c.add_child(sheet)
	var scroll := ScrollContainer.new()
	scroll.position = Vector2(FORM_PAD, 150)
	scroll.size = Vector2(ss.x - FORM_PAD * 2.0, ss.y - 150 - 86)
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_SHOW_NEVER
	sheet.add_child(scroll)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 4)
	v.custom_minimum_size = Vector2(scroll.size.x - 12.0, 0)
	scroll.add_child(v)
	var to := UITheme.label(dedication(), 30, UITheme.pen, UITheme.INK_BLUE)
	to.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	to.custom_minimum_size = Vector2(v.custom_minimum_size.x - 40.0, 0)
	v.add_child(to)
	for row in CREDITS:
		var head := UITheme.label(row[0], 22, UITheme.print_700, UITheme.INK_BLACK)
		head.custom_minimum_size = Vector2(0, 46)
		head.vertical_alignment = VERTICAL_ALIGNMENT_BOTTOM
		v.add_child(head)
		var l := UITheme.label(row[1], 22, UITheme.print_400, Color(UITheme.INK_BLACK, 0.86))
		l.add_theme_constant_override("line_spacing", 4)
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		l.custom_minimum_size = Vector2(v.custom_minimum_size.x, 0)
		v.add_child(l)
	var end := Control.new()   # room for the last line to scroll clear of the fade
	end.custom_minimum_size = Vector2(0, 56)
	v.add_child(end)
	# the list fades out into the paper where the window cuts it, instead of a line sliced in half
	sheet.paper_over(Rect2(FORM_PAD - 8.0, scroll.position.y + scroll.size.y - 60.0, scroll.size.x + 16.0, 62.0))
	var logo := TitleLogo.new()
	logo.width = 380.0
	logo.position = Vector2(FORM_PAD - 18.0, -26.0)
	sheet.add_child(logo)
	var done := _paper_button(sheet, "Back", func(): back.call(), FORM_BUTTON_SIZE, 71)
	_on_line(done, FORM_PAD + 4.0, ss.y - 36.0, UITheme.marker_menu, FORM_BUTTON_SIZE)
	_swap(c, true, 0.55, 0.18)
	_back = back
	_scroll = scroll
	done.grab_focus.call_deferred()


# ------------------------------------------------------------------ journal
## Mano's journal (V2-08, docs/DESIGN.md §5.5): the open notebook on two pages, with tabs along its top in his marker:
## today (the half-finished Dijkstra notes and "17:42, woke up. ONE AirPod." on the first page, the to-dos with the
## done ones struck through, what he knows), people (one kind line each, changing over the night: data/journal.json),
## film (Ishita's camera: exposures left, per chapter, what is on it), ducks (per chapter; the debugging tips at
## twelve), moments (the sit-downs) and on the side (the side stories once met). Left and right (A, D, Q, E, LB, RB)
## turn the tabs; Tab or Esc closes it. The tab is remembered while the game runs.
const JOURNAL_TABS := ["today", "people", "film", "ducks", "moments", "on the side"]
const JOURNAL_FILE := "res://data/journal.json"
var journal_tab := 0
var _journal_data := {}


func show_journal(tab := -1) -> void:
	var fresh: bool = game.mode != "journal"
	game.enter_menu("journal")
	if tab >= 0:
		journal_tab = clampi(tab, 0, JOURNAL_TABS.size() - 1)
	if _journal_data.is_empty():
		var d = WorldData._read(JOURNAL_FILE)
		_journal_data = d if d is Dictionary else {}
	var c := Control.new()
	# white French school paper (not cream); Mano writes in blue ballpoint, headings in his marker
	var paper := UITheme.PAPER
	var ink := UITheme.INK_BLUE
	var book := HBoxContainer.new()
	book.set_anchors_preset(Control.PRESET_CENTER)
	book.position = Vector2(-640, -318)
	book.add_theme_constant_override("separation", 0)
	book.rotation_degrees = -0.6
	var pages: Array[VBoxContainer] = []
	for page in 2:
		var p := PanelContainer.new()
		var sb := UITheme.box(paper if page == 0 else UITheme.PAPER.lerp(UITheme.PAPER_SHADE, 0.35), 2, Color(0, 0, 0, 0.08), 34)
		sb.shadow_color = Color(0, 0, 0, 0.35)
		sb.shadow_size = 18
		p.add_theme_stylebox_override("panel", sb)
		p.custom_minimum_size = Vector2(640, 640)
		var v := VBoxContainer.new()
		v.add_theme_constant_override("separation", 8)
		p.add_child(v)
		book.add_child(p)
		pages.append(v)
	_journal_tab_row(c)
	match JOURNAL_TABS[journal_tab]:
		"today":
			_journal_today(pages[0], pages[1], ink)
		"people":
			_journal_people(pages[0], pages[1], ink)
		"film":
			_journal_film(pages[0], pages[1], ink)
		"ducks":
			_journal_ducks(pages[0], pages[1], ink)
		"moments":
			_moments(pages[0], ink)
			_journal_coins(pages[1], ink)
		"on the side":
			_journal_side(pages[0], pages[1], ink)
	c.add_child(book)
	var keys := "LB, RB: turn the page    B: close" if GameState.using_pad else "A, D: turn the page    Tab or Esc: close"
	var hint := UITheme.over_scene(UITheme.label(keys, 19, UITheme.print_500, UITheme.FILM_WHITE), 5, 0.4) as Label
	hint.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	hint.grow_horizontal = Control.GROW_DIRECTION_BOTH   # centred whatever its length (keys or pad)
	hint.offset_left = 0.0
	hint.offset_right = 0.0
	hint.offset_top = -40.0
	hint.offset_bottom = -40.0
	c.add_child(hint)
	_swap(c, true, 0.45, 0.25 if fresh else 0.0)
	set_process(true)
	if fresh:
		Sfx.ui("journal_open", -4.0)
	else:
		Sfx.ui("ui_hover", -8.0)


## The tabs over the book: the words in marker on paper tabs, the open one circled in red.
func _journal_tab_row(c: Control) -> void:
	var row := HBoxContainer.new()
	row.set_anchors_preset(Control.PRESET_CENTER_TOP)
	row.position = Vector2(-600, 52)
	row.add_theme_constant_override("separation", 14)
	for i in JOURNAL_TABS.size():
		var on := i == journal_tab
		var tab := PanelContainer.new()
		var sb := UITheme.box(UITheme.PAPER if on else UITheme.PAPER_SHADE, 2, Color(0, 0, 0, 0.1), 10)
		sb.content_margin_left = 16
		sb.content_margin_right = 16
		sb.content_margin_top = 4
		sb.content_margin_bottom = 6
		tab.add_theme_stylebox_override("panel", sb)
		var l := UITheme.label(JOURNAL_TABS[i], 26, UITheme.marker, UITheme.INK_RED if on else UITheme.INK_BLACK)
		tab.add_child(l)
		if on:
			l.draw.connect(func():
				Ink.ruler_line(l, Vector2(0, l.size.y - 3.0), Vector2(l.size.x, l.size.y - 4.0), UITheme.MARKER_RED, 2.4))
		row.add_child(tab)
	c.add_child(row)


func journal_turn(d: int) -> void:
	journal_tab = posmod(journal_tab + d, JOURNAL_TABS.size())
	show_journal()


func _head(v: VBoxContainer, text: String, first := false) -> void:
	v.add_child(UITheme.label(text, 40 if first else 30, UITheme.marker_menu if first else UITheme.marker, UITheme.INK_BLACK if first else UITheme.INK_RED))


func _pen(v: VBoxContainer, text: String, size := 25, color := UITheme.INK_BLUE) -> Label:
	var l := _wrap(UITheme.label(text, size, UITheme.pen, color))
	v.add_child(l)
	return l


## today: the first page's half-finished Dijkstra notes trailing off in a long sleepy pen stroke, the margin note,
## the to-dos; what he knows on the right.
func _journal_today(left: VBoxContainer, right: VBoxContainer, ink: Color) -> void:
	_head(left, "Mano's journal", true)
	var notes := VBoxContainer.new()
	notes.add_theme_constant_override("separation", 0)
	for line in _journal_data.get("dijkstra", []):
		var l := UITheme.label(String(line), 21, UITheme.pen, UITheme.INK_BLUE_SOFT)
		notes.add_child(l)
	# the sleepy stroke: the last line's pen trails off down the page
	var stroke := Control.new()
	stroke.custom_minimum_size = Vector2(560, 34)
	stroke.draw.connect(func():
		var pts := PackedVector2Array()
		for i in 40:
			var k := float(i) / 39.0
			pts.append(Vector2(30.0 + k * 470.0, 6.0 + k * 22.0 + sin(k * 9.0) * 3.0 * (1.0 - k)))
		stroke.draw_polyline(pts, Color(UITheme.INK_BLUE_SOFT, 0.75), 1.6, true))
	notes.add_child(stroke)
	var margin := UITheme.label(String(_journal_data.get("margin", "")), 22, UITheme.pen, UITheme.INK_RED)
	margin.rotation_degrees = -3.0
	notes.add_child(margin)
	left.add_child(notes)
	_head(left, "Right now")
	_todo_list(left, ink)
	_head(right, "What I know")
	var clues: Array = GameState.flags.get("clues", [])
	if clues.is_empty():
		_pen(right, "Nothing yet. Talk to Toma.", 26, UITheme.PENCIL)
	for cl in clues.slice(maxi(0, clues.size() - 9)):
		_pen(right, "- " + cl, 23, ink)


## people: who Mano has met tonight, each in their colour, with a kind line that changes over the night.
func _journal_people(left: VBoxContainer, right: VBoxContainer, ink: Color) -> void:
	_head(left, "People")
	# the three new friends once Mano has met them (V2-21; Cristina once a message from Cristina has reached him)
	var met_flags := {"ishita": "ishita_met", "joaquin": "joaquin_met", "cristina": "cristina_texted"}
	var lines: Dictionary = _journal_data.get("people", {})
	var i := 0
	for id in ["toma", "anisha", "ian", "silvia", "ishita", "joaquin", "cristina"]:
		if met_flags.has(id) and not GameState.flags.get(met_flags[id], false):
			continue
		if not game.npcs.has(id):
			continue
		var v: VBoxContainer = left if i < 4 else right
		if i == 4:
			_head(right, "People (still)")
		i += 1
		var n = game.npcs[id]
		var tag := HBoxContainer.new()
		var dot := ColorRect.new()
		dot.color = n.color
		dot.custom_minimum_size = Vector2(12, 12)
		dot.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		tag.add_child(dot)
		tag.add_child(UITheme.label(n.display_name, 27, UITheme.marker_label, UITheme.INK_BLACK))
		v.add_child(tag)
		for e in lines.get(id, []):
			if Conditions.eval(String(e.get("when", "true"))):
				_pen(v, String(e.get("text", "")), 23, ink)
				break
	if i <= 4:
		_head(right, "Also tonight")
		for id in ["karim", "madame"]:
			if game.npcs.has(id):
				_pen(right, "- " + String(game.npcs[id].display_name), 24, ink)


## film: Ishita's disposable camera, ten exposures and the group photo; what is on it, by chapter.
func _journal_film(left: VBoxContainer, right: VBoxContainer, ink: Color) -> void:
	_head(left, "Ishita's film")
	if not GameState.flags.get("camera", false):
		_pen(left, "No camera yet. Ishita has it.", 25, UITheme.PENCIL)
		return
	var shots := int(GameState.flags.get("film_shots", 0))
	_pen(left, "%d of %d photos taken, %d left. The last one's for the steps." % [shots, Film.EXPOSURES, Film.left()], 25, ink)
	if bool(GameState.flags.get("group_photo", false)):
		_pen(left, "The group photo: all eight of us. The last exposure.", 24, ink)
	for n in range(1, 6):
		var k := Film.count_in(n)
		if k.y > 0:
			_pen(left, "Chapter %d: %d of %d" % [n, k.x, k.y], 24, UITheme.PENCIL if k.x == 0 else ink)
	_head(right, "On the film")
	var t := Film.taken()
	var all := Film.spots()
	if t.is_empty():
		_pen(right, "Nothing yet. Photo mode (P) near something worth it.", 24, UITheme.PENCIL)
	for id in t:
		if all.has(id):
			_pen(right, "- " + String(all[id].label), 24, ink)


## ducks: how many of each chapter's ducks are found; at twelve, the debugging tips.
func _journal_ducks(left: VBoxContainer, right: VBoxContainer, ink: Color) -> void:
	_head(left, "Golden rubber ducks")
	_pen(left, "%d out of %d found%s" % [game.ducks.count(), game.ducks.total(), ". Merch fit unlocked!" if GameState.flags.get("merch", false) else ""], 26, ink)
	var by: Dictionary = game.ducks.by_chapter()
	for n in range(1, 6):
		if by.has(n):
			var v: Vector2i = by[n]
			_pen(left, "Chapter %d: %d of %d" % [n, v.x, v.y], 24, UITheme.PENCIL if v.x == 0 else ink)
	if GameState.flags.get("whisperer_met", false) and not GameState.flags.get("duck_zero", false):
		_pen(left, "Whoever hid them hangs about cour Pasteur.", 23, UITheme.PENCIL)
	_head(right, "Rubber-duck debugging")
	if not GameState.flags.get("ducks_all", false):
		_pen(right, "(a page for when I find all twelve)", 24, UITheme.PENCIL)
		return
	for tip in _journal_data.get("duck_tips", []):
		_pen(right, "- " + String(tip), 23, ink)
	if GameState.flags.get("duck_zero", false):
		_pen(right, "+ duck zero. The original. It squeaks in C.", 23, UITheme.INK_RED)


func _journal_coins(v: VBoxContainer, ink: Color) -> void:
	_head(v, "Coins")
	_pen(v, "%d €" % GameState.flags.get("coins", 0), 26, ink)
	var choco: String = GameState.flags.get("choco", "")
	if choco != "":
		_head(v, "Pastry war")
		_pen(v, "Team %s" % ("pain au chocolat" if choco == "pac" else "chocolatine"), 26, ink)


## on the side: the side stories Mano has come across, ticked once done, struck through once their time is past.
func _journal_side(left: VBoxContainer, right: VBoxContainer, ink: Color) -> void:
	_head(left, "On the side")
	var any := false
	var k := 0
	for e in _journal_data.get("side", []):
		if not Conditions.eval(String(e.get("seen", "false"))):
			continue
		any = true
		var v: VBoxContainer = left if k < 2 else right
		k += 1
		var done := Conditions.eval(String(e.get("done", "false")))
		var failed: bool = not done and e.has("fail") and Conditions.eval(String(e.fail))
		var title := UITheme.label(("[x] " if done else "[  ] ") + String(e.title), 27, UITheme.marker_label, UITheme.INK_GREEN if done else UITheme.INK_BLACK)
		v.add_child(title)
		var note := _pen(v, String(e.get("done_note" if done else ("fail_note" if failed else "note"), e.get("note", ""))), 23, UITheme.PENCIL if failed else ink)
		if failed:
			note.draw.connect(func():
				var w := minf(UITheme.pen.get_string_size(note.text, HORIZONTAL_ALIGNMENT_LEFT, -1, 23).x, note.size.x)
				Ink.ruler_line(note, Vector2(-2, note.size.y * 0.5), Vector2(w + 4.0, note.size.y * 0.5 - 1.0), Color(UITheme.INK_RED, 0.7), 2.0))
	if not any:
		_pen(left, "Nothing on the side yet. Talk to people. Look around.", 24, UITheme.PENCIL)


## Tonight's to-dos (V2-20): the main one, the optional ones (at most two) and, struck through, the ones done.
func _todo_list(v: VBoxContainer, ink: Color) -> void:
	var main: String = game.story.objective()
	if main != "":
		v.add_child(_wrap(UITheme.label(main, 28, UITheme.pen, ink)))
	for t in Chapters.optional_todos():
		v.add_child(_wrap(UITheme.label("- " + Chapters.text_of(t), 25, UITheme.pen, ink)))
	var done: Array = Chapters.done_todos()
	for t in done.slice(maxi(0, done.size() - 4)):
		var l := _wrap(UITheme.label(Chapters.text_of(t), 24, UITheme.pen, UITheme.PENCIL))
		l.draw.connect(func():
			var f: Font = UITheme.pen
			var w := minf(f.get_string_size(l.text, HORIZONTAL_ALIGNMENT_LEFT, -1, 24).x, l.size.x)
			var y := l.size.y * 0.55
			Ink.ruler_line(l, Vector2(-2, y), Vector2(w + 4.0, y - 1.0), Color(UITheme.INK_BLUE, 0.8), 2.0))
		v.add_child(l)


## The sit-downs Mano has had tonight (V2-14): one line each in his voice (data/world.json sits "journal"), and how
## many of the six.
func _moments(v: VBoxContainer, ink: Color) -> void:
	var done: Array = GameState.flags.get("moments", [])
	var all := WorldData.sit_ids()
	v.add_child(UITheme.label("Moments", 30, UITheme.marker, UITheme.INK_RED))
	if done.is_empty():
		v.add_child(UITheme.label("None yet. Sit down somewhere, for once.", 24, UITheme.pen, UITheme.PENCIL))
		return
	for id in done:
		var line := String(WorldData.sit(String(id)).get("journal", ""))
		if String(line) != "":
			var l := _wrap(UITheme.label("- " + String(line), 22, UITheme.pen, ink))
			l.custom_minimum_size = Vector2(560, 0)
			v.add_child(l)
	v.add_child(UITheme.label("%d of %d" % [done.size(), all.size()], 22, UITheme.pen, UITheme.PENCIL))
	if done.size() >= all.size():
		# all six (V2-30): the extra line
		v.add_child(_wrap(UITheme.label("Six times tonight I sat down and just listened. Stop looking, and things come back.", 22, UITheme.pen, UITheme.INK_RED)))


func _wrap(l: Label) -> Label:
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.custom_minimum_size = Vector2(560, 0)
	return l


# ------------------------------------------------------------------ map
func show_map() -> void:
	game.enter_menu("map")
	var c := Control.new()
	_map_view = MapView.new()
	_map_view.game = game
	_map_view.set_anchors_preset(Control.PRESET_FULL_RECT)
	c.add_child(_map_view)
	_swap(c, true)
	set_process(true)
	Sfx.ui("map_open", -4.0)


# ------------------------------------------------------------------ wardrobe
func show_wardrobe() -> void:
	game.enter_menu("wardrobe")
	_wardrobe_sel = game.OUTFITS.keys().find(GameState.outfit)
	_render_wardrobe()
	set_process(true)


func _render_wardrobe() -> void:
	var c := Control.new()
	var panel := VBoxContainer.new()
	panel.set_anchors_preset(Control.PRESET_CENTER_RIGHT)
	panel.position = Vector2(-520, -260)
	panel.custom_minimum_size = Vector2(440, 0)
	panel.add_theme_constant_override("separation", 10)
	panel.add_child(UITheme.over_scene(UITheme.label("Pick the fit", 47, UITheme.marker_title, UITheme.FILM_WHITE), 8, 0.5))
	var keys: Array = game.OUTFITS.keys()
	for i in keys.size():
		var k: String = keys[i]
		var o: Dictionary = game.OUTFITS[k]
		var unlocked: bool = game.outfit_unlocked(k)
		var b := Button.new()
		b.text = "%s%s\n%s" % [o.name, " (wearing)" if k == GameState.outfit else "", o.desc if unlocked else "Locked: " + o.locked]
		b.alignment = HORIZONTAL_ALIGNMENT_LEFT
		b.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		b.custom_minimum_size = Vector2(460, 0)
		b.add_theme_font_override("font", UITheme.print_500)
		b.add_theme_font_size_override("font_size", 22)
		b.disabled = not unlocked
		b.pressed.connect(func():
			game.wear(k)
			_wardrobe_sel = i
			_render_wardrobe())
		b.focus_entered.connect(func(): _wardrobe_sel = i)
		panel.add_child(b)
		if i == _wardrobe_sel:
			b.grab_focus.call_deferred()
	var hint := UITheme.over_scene(UITheme.label("%s to wear it, F or Esc when done" % UITheme.action_key("confirm"), 18, UITheme.print_500, UITheme.FILM_WHITE), 5, 0.4)
	panel.add_child(hint)
	c.add_child(panel)
	_swap(c)
	c.modulate.a = 1.0


# ------------------------------------------------------------------ photo mode
func show_photo() -> void:
	game.enter_menu("photo")
	_photo = {"yaw": game.player.facing_yaw() + 0.5, "pitch": 0.15, "dist": 2.4, "height": 1.25, "fov": 40.0, "pose": 0}
	var c := Control.new()
	# the controls as a short list in the corner, not one long dotted line
	var tip := UITheme.over_scene(UITheme.label("Photo mode\ndrag or arrows: turn around\nwheel: closer, further\nW, S: higher, lower\n[ and ]: lens\n1 to 4: pose\nC: save a picture\nP: back", 18, UITheme.print_500, UITheme.FILM_WHITE), 5, 0.45) as Label
	tip.add_theme_constant_override("line_spacing", 2)
	tip.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
	tip.grow_vertical = Control.GROW_DIRECTION_BEGIN
	tip.offset_left = 44
	tip.offset_bottom = -36
	c.add_child(tip)
	# Ishita's film (V2-30): when the view frames one of the photo spots, a pen note says so and C puts it on her film
	_film_note = UITheme.over_scene(UITheme.label("", 30, UITheme.pen, UITheme.FILM_WHITE), 9, 0.7) as Label
	_film_note.set_anchors_preset(Control.PRESET_CENTER_TOP)
	_film_note.position = Vector2(-420, 64)
	_film_note.custom_minimum_size = Vector2(840, 0)
	_film_note.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	c.add_child(_film_note)
	_swap(c)
	c.modulate.a = 1.0
	set_process(true)


var _film_note: Label = null
## The photo spot photo mode frames now (Film.framed), or {}; checked a few times a second.
var photo_framed := {}
var _framed_t := 0.0


## Where photo mode's camera is and what it looks at (as _update_photo sets them).
func photo_view() -> Array:
	var ph := _photo
	var p: Vector3 = game.player.global_position
	var look: Vector3 = p + Vector3.UP * float(ph.height)
	var from: Vector3 = look + Vector3(sin(ph.yaw) * cos(ph.pitch), sin(ph.pitch), cos(ph.yaw) * cos(ph.pitch)) * float(ph.dist)
	return [from, look]


func _update_film_note(dt: float) -> void:
	_framed_t -= dt
	if _framed_t > 0.0 or _film_note == null or not is_instance_valid(_film_note):
		return
	_framed_t = 0.25
	photo_framed = {}
	if bool(GameState.flags.get("camera", false)) and Film.left() > 0:
		var v := photo_view()
		photo_framed = Film.framed(v[0], v[1])
	if photo_framed.is_empty():
		_film_note.text = ""
	else:
		_film_note.text = "Ishita's film: %s. C to take it (%d left)" % [photo_framed.label, Film.left()]


func _capture_photo() -> void:
	var was := current.visible
	var framed := photo_framed.duplicate()
	current.visible = false
	game.hud.root.visible = false
	await RenderingServer.frame_post_draw
	var img: Image = game.get_viewport().get_texture().get_image()
	current.visible = was
	game.hud.root.visible = true
	var dir := GameState.photos_dir()   # ~/Pictures, except in autotests and tests (V2-33)
	DirAccess.make_dir_recursive_absolute(dir)
	var path := dir.path_join("mano-%s.png" % Time.get_datetime_string_from_system().replace(":", "-"))
	img.save_png(path)
	# a small copy goes with Ishita's film for the credits' prints (V2-27; user://film/, *.autotest in autotests)
	var copy := img.duplicate() as Image
	if copy.get_width() > 960:
		copy.resize(960, roundi(copy.get_height() * 960.0 / copy.get_width()), Image.INTERPOLATE_LANCZOS)
	var film := ProjectSettings.globalize_path(GameState.film_dir())
	DirAccess.make_dir_recursive_absolute(film)
	Sfx.play("shutter")
	# framed for Ishita's film: it is one of her prints (film_NN.png, the credits show it), not one of the player's copies
	if not framed.is_empty() and Film.take(String(framed.id)) != "dup":
		copy.save_png(film.path_join("film_%02d.png" % int(GameState.flags.get("film_shots", 0))))
		game.toast("Ishita's film: %d of %d" % [int(GameState.flags.get("film_shots", 0)), Film.EXPOSURES], "camera")
		print("[photo] photo mode: %s on Ishita's film, %d exposures used" % [framed.id, int(GameState.flags.get("film_shots", 0))])
		_framed_t = 0.0
		return
	copy.save_png(film.path_join("photo_%s.png" % Time.get_datetime_string_from_system().replace(":", "-")))
	game.toast("Saved to Pictures", "camera")


# ------------------------------------------------------------------ ending
## The notebook's last page over the blurred scene (docs/DESIGN.md §5.5, docs/ART_DIRECTION.md): "à suivre…" in red marker,
## ruled under; the night as a pen list; the sequel on a "coming soon" sticker; the dedication to the eight
## friends; two words to circle. The page writes itself on, line by line.
func show_ending() -> void:
	game.enter_menu("ending")
	var c := Control.new()
	var page := PaperSheet.new()
	var ps := Vector2(1000, 760)
	page.size = ps
	page.pivot_offset = ps * 0.5
	page.row = 38.0
	page.first_line = 38.0 * 1.6
	page.margin_x = 104.0
	page.seed_value = 1015
	page.lift = 1.6
	page.theme = Ink.paper_theme()
	_center(page, ps, Vector2(0, -6))
	page.rotation_degrees = -0.8
	c.add_child(page)
	var x0 := page.margin_x + 26.0
	var lines: Array[Label] = []
	var title := _page_line(page, "à suivre…", 74, UITheme.marker_title, UITheme.MARKER_RED, x0, page.line_y(2))
	var mins := int(GameState.play_time / 60.0)
	var found: int = game.ducks.count()
	var losses: int = GameState.flags.get("foot_losses", 0)
	var stats := ["%d minute%s on campus" % [mins, "" if mins == 1 else "s"],
		"%d golden duck%s out of %d" % [found, "" if found == 1 else "s", game.ducks.total()],
		"%d babyfoot defeat%s" % [losses, "" if losses == 1 else "s"]]
	for i in stats.size():
		lines.append(_page_line(page, "– " + stats[i], 30, UITheme.pen, UITheme.INK_BLUE, x0 + 8.0, page.line_y(4 + i)))
	var to := dedication()
	var cut := to.find(", Ishita")   # two lines, broken after Silvia
	lines.append(_page_line(page, to.substr(0, cut + 1) if cut > 0 else to, 30, UITheme.pen, UITheme.INK_BLUE, x0, page.line_y(9)))
	if cut > 0:
		lines.append(_page_line(page, to.substr(cut + 2), 30, UITheme.pen, UITheme.INK_BLUE, x0, page.line_y(10)))
	var rule := Control.new()
	rule.mouse_filter = Control.MOUSE_FILTER_IGNORE
	rule.set_meta("k", 0.0)
	var tw_w := UITheme.marker_title.get_string_size(title.text, HORIZONTAL_ALIGNMENT_LEFT, -1, 74).x
	rule.draw.connect(func():
		var y := page.line_y(2) + 16.0
		Ink.ruler_line(rule, Vector2(x0 - 10.0, y), Vector2(x0 + tw_w + 18.0, y - 1.0), UITheme.MARKER_RED, 3.0, float(rule.get_meta("k"))))
	page.add_child(rule)
	var keep := _paper_button(page, "Keep exploring", func(): game.resume(), MENU_SIZE, 81)
	_on_line(keep, x0, page.line_y(13), UITheme.marker_menu, MENU_SIZE)
	var back := _paper_button(page, "Back to title", func(): game.show_title(), MENU_SIZE, 82)
	_on_line(back, x0 + _word_w(keep.text, MENU_SIZE) + 36.0, page.line_y(13), UITheme.marker_menu, MENU_SIZE)
	keep.focus_neighbor_right = keep.get_path_to(back)
	back.focus_neighbor_left = back.get_path_to(keep)
	var note := _note("coming soon:\nMano & the OTHER lost AirPod", "airpod", UITheme.STICKY_PINK)
	page.add_child(note)
	var credit := UITheme.over_scene(UITheme.label("Music by Kevin MacLeod (incompetech.com), CC BY 4.0. Full credits on the title screen.", 18,
		UITheme.print_500, UITheme.FILM_WHITE), 5, 0.4) as Label
	credit.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	credit.grow_horizontal = Control.GROW_DIRECTION_BOTH
	credit.offset_top = -40.0
	credit.offset_bottom = -16.0
	c.add_child(credit)
	_swap(c, true, 0.4, 0.0)
	note.base = Vector2(ps.x - note.size.x - 70.0, page.line_y(4) - 30.0)
	# written on in order: the title and its red rule, the list, the dedication
	var calm := Ink.calm()
	_paper_in(page)
	var t := 0.45
	Ink.write_on(title, 0.9, t)
	t += 0.95
	if calm:
		rule.set_meta("k", 1.0)
	else:
		var tw := rule.create_tween()
		tw.tween_interval(t)
		tw.tween_method(func(k: float):
			rule.set_meta("k", k)
			rule.queue_redraw(), 0.0, 1.0, 0.22).set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)
	t += 0.35
	for l in lines:
		Ink.write_on(l, 0.0, t)
		t += l.text.length() / Ink.CPS + 0.12
	if calm:
		note.land(Vector2.ZERO)
	else:
		# the sticker lands while the list is being written, so the page never waits on it
		get_tree().create_timer(minf(t, 2.6), false).timeout.connect(func():
			if is_instance_valid(note):
				note.land(Vector2(0, -24)))
		note.modulate.a = 0.0
	keep.grab_focus.call_deferred()


## The recap (V2-27: "your night"): the notebook's last page after the post-credits, "à suivre…" in red
## marker and the night as Mano lived it, one pen line per choice that mattered (data/recap.json: a "Toma's night"
## column joins it once toma_picks has entries); then "Keep exploring" (the campus at night) or the title.
func show_recap() -> void:
	game.enter_menu("ending")
	var c := Control.new()
	var page := PaperSheet.new()
	var ps := Vector2(1080, 800)
	page.size = ps
	page.pivot_offset = ps * 0.5
	page.row = 36.0
	page.first_line = 36.0 * 1.6
	page.margin_x = 104.0
	page.seed_value = 1016
	page.lift = 1.6
	page.theme = Ink.paper_theme()
	_center(page, ps, Vector2(0, -6))
	page.rotation_degrees = -0.8
	c.add_child(page)
	var x0 := page.margin_x + 26.0
	var title := _page_line(page, "à suivre…", 70, UITheme.marker_title, UITheme.MARKER_RED, x0, page.line_y(2))
	var head := _page_line(page, "My night", 32, UITheme.marker, UITheme.INK_BLACK, x0, page.line_y(4))
	var lines: Array[Label] = [head]
	var y := 5
	for t in recap_lines():
		lines.append(_page_line(page, "– " + String(t), 27, UITheme.pen, UITheme.INK_BLUE, x0 + 8.0, page.line_y(y)))
		y += 1
	var toma_picks: Array = _toma_picks()
	if not toma_picks.is_empty():
		var tx := ps.x * 0.58
		lines.append(_page_line(page, "Toma's night", 32, UITheme.marker, UITheme.INK_BLACK, tx, page.line_y(4)))
		for i in mini(toma_picks.size(), 11):
			lines.append(_page_line(page, "– " + String(toma_picks[i]), 27, UITheme.pen, UITheme.INK_BLUE, tx + 8.0, page.line_y(5 + i)))
	var to := dedication()
	var cut := to.find(", Ishita")
	lines.append(_page_line(page, to.substr(0, cut + 1) if cut > 0 else to, 27, UITheme.pen, UITheme.INK_BLUE, x0, page.line_y(y + 1)))
	if cut > 0:
		lines.append(_page_line(page, to.substr(cut + 2), 27, UITheme.pen, UITheme.INK_BLUE, x0, page.line_y(y + 2)))
	var keep := _paper_button(page, "Keep exploring", func(): game.resume(), MENU_SIZE, 83)
	_on_line(keep, x0, page.line_y(y + 4), UITheme.marker_menu, MENU_SIZE)
	var back := _paper_button(page, "Back to title", func(): game.show_title(), MENU_SIZE, 84)
	_on_line(back, x0 + _word_w(keep.text, MENU_SIZE) + 36.0, page.line_y(y + 4), UITheme.marker_menu, MENU_SIZE)
	keep.focus_neighbor_right = keep.get_path_to(back)
	back.focus_neighbor_left = back.get_path_to(keep)
	var credit := UITheme.over_scene(UITheme.label("Music by Kevin MacLeod (incompetech.com), CC BY 4.0. Full credits on the title screen.", 18,
		UITheme.print_500, UITheme.FILM_WHITE), 5, 0.4) as Label
	credit.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	credit.grow_horizontal = Control.GROW_DIRECTION_BOTH
	credit.offset_top = -40.0
	credit.offset_bottom = -16.0
	c.add_child(credit)
	_swap(c, true, 0.4, 0.0)
	_paper_in(page)
	var t := 0.45
	Ink.write_on(title, 0.9, t)
	t += 1.0
	for l in lines:
		Ink.write_on(l, 0.0, t)
		t += minf(l.text.length() / Ink.CPS, 1.2) + 0.08
	recap_shown = recap_lines()
	keep.grab_focus.call_deferred()


## What the recap page lists (autotests read it back).
var recap_shown: Array = []


## The author's own picks for the night (data/recap.json "toma_picks"): an empty list, and no column, by default.
func _toma_picks() -> Array:
	var p := "res://data/recap.json"
	if not FileAccess.file_exists(p):
		return []
	var j = JSON.parse_string(FileAccess.get_file_as_string(p))
	return j.get("toma_picks", []) if j is Dictionary else []


## The night as Mano lived it, from the flags: one short line per choice that mattered, each with a fallback.
func recap_lines() -> Array:
	var f := GameState.flags
	var out: Array = ["Woke up at 17:42 with one AirPod. Went home with two. Briefly."]
	match String(f.get("choco", "")):
		"pac":
			out.append("Pain au chocolat, apparently. Ian's side.")
		"choco":
			out.append("Chocolatine, apparently. Silvia's side.")
		_:
			out.append("Dodged the pastry war. Then ended it.")
	var partner := String(f.get("foot_partner", ""))
	var losses := int(f.get("foot_losses", 0))
	var who := "alone" if partner in ["", "solo"] else "with " + partner.capitalize()
	# no losses: "0 defeats, then a win" read like a bug on the last page
	out.append("Babyfoot %s: a win, first try." % who if losses == 0 else "Babyfoot %s: %d defeat%s, then a win." % [who, losses, "" if losses == 1 else "s"])
	var fav := String(f.get("ishita_fav", ""))
	var favs := {"amphi": "my seat in Amphi 4", "sofa": "the Under's sofa", "stickers": "the sticker column", "velib": "the bike rack",
		"vending": "the red vending machine", "bay": "KB1's glass bays"}
	out.append("Ishita's favourite place: %s." % favs.get(fav, "still deciding"))
	var song := String(f.get("playlist", ""))
	out.append("The song for the steps: \"%s\"." % Chat.song_title(song) if song != "" else "No song picked. Toma noticed.")
	var total := int(f.get("kebab_total", 0))
	if total > 0:
		out.append("Kebab orders: %d of %d right. Ask Ian about the rest." % [int(f.get("kebab_score", 0)), total]
			if "ian" in f.get("kebab_wrong", []) else "Kebab orders: %d of %d right." % [int(f.get("kebab_score", 0)), total])
	var given := String(f.get("given_to", ""))
	out.append("The other AirPod went to %s, for one song." % given.capitalize() if given != "" else "Kept both AirPods. In the case.")
	var moments: int = f.get("moments", []).size()
	var photos := int(f.get("film_shots", 0)) + (1 if bool(f.get("group_photo", false)) else 0)
	out.append("%d of %d moments. %d photo%s on Ishita's film." % [moments, WorldData.sit_ids().size(), photos, "" if photos == 1 else "s"])
	var found: int = game.ducks.count() if game and game.ducks else 0
	var mins := int(GameState.play_time / 60.0)
	out.append("%d golden duck%s. %d minute%s on campus." % [found, "" if found == 1 else "s", mins, "" if mins == 1 else "s"])
	return out


## One line of handwriting on a page: its baseline on `baseline`, starting at `x`.
func _page_line(page: Control, text: String, size: int, font: Font, color: Color, x: float, baseline: float) -> Label:
	var l := UITheme.label(text, size, font, color)
	l.position = Vector2(x, baseline - font.get_ascent(size))
	l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	page.add_child(l)
	return l


# ------------------------------------------------------------------ per-frame for interactive screens
func _process(dt: float) -> void:
	if game == null or game.player == null:
		return
	match game.mode:
		"wardrobe":
			_wardrobe_t += dt
			var p: Vector3 = game.player.global_position
			var ang: float = game.player.facing_yaw() + sin(_wardrobe_t * 0.35) * 0.9
			var from: Vector3 = p + Vector3(sin(ang) * 2.3, 1.35, cos(ang) * 2.3)
			game.camera_rig.set_shot(from, p + Vector3.UP * 0.95 + Vector3(cos(ang), 0, -sin(ang)) * 0.45, 38.0, from.distance_to(p + Vector3.UP), true)
		"photo":
			_update_photo(dt)
			_update_film_note(dt)
		"map":
			pass   # the map redraws its live overlay itself, ten times a second; its sheet is baked once (V2-09)


func _update_photo(dt: float) -> void:
	if _photo.is_empty():
		return
	var ph := _photo
	if Input.is_physical_key_pressed(KEY_LEFT) or Input.is_physical_key_pressed(KEY_A):
		ph.yaw += 1.3 * dt
	if Input.is_physical_key_pressed(KEY_RIGHT) or Input.is_physical_key_pressed(KEY_D):
		ph.yaw -= 1.3 * dt
	if Input.is_physical_key_pressed(KEY_UP):
		ph.pitch = minf(1.2, ph.pitch + dt)
	if Input.is_physical_key_pressed(KEY_DOWN):
		ph.pitch = maxf(-0.5, ph.pitch - dt)
	if Input.is_physical_key_pressed(KEY_W):
		ph.height = minf(2.2, ph.height + dt * 0.8)
	if Input.is_physical_key_pressed(KEY_S):
		ph.height = maxf(0.3, ph.height - dt * 0.8)
	var p: Vector3 = game.player.global_position
	var look: Vector3 = p + Vector3.UP * float(ph.height)
	var from: Vector3 = look + Vector3(sin(ph.yaw) * cos(ph.pitch), sin(ph.pitch), cos(ph.yaw) * cos(ph.pitch)) * float(ph.dist)
	game.camera_rig.set_shot(from, look, ph.fov, from.distance_to(look), true)


func _unhandled_input(event: InputEvent) -> void:
	if game == null:
		return
	if _back.is_valid() and (event.is_action_pressed("back") or event.is_action_pressed("pause")):
		# a sheet opened from another screen (settings, credits) goes back to it, not out of the menus
		get_viewport().set_input_as_handled()
		Sfx.ui("ui_back", -6.0)
		_back.call()
		return
	if _scroll and (event.is_action_pressed("ui_down", true) or event.is_action_pressed("ui_up", true)):
		get_viewport().set_input_as_handled()
		_scroll.scroll_vertical += 64 if event.is_action_pressed("ui_down", true) else -64
		return
	var m: String = game.mode
	if m == "journal" and (event.is_action_pressed("move_left") or event.is_action_pressed("move_right") or event.is_action_pressed("ui_left") \
			or event.is_action_pressed("ui_right") or (event is InputEventKey and event.pressed and not event.echo and event.physical_keycode in [KEY_Q, KEY_E]) \
			or (event is InputEventJoypadButton and event.pressed and event.button_index in [JOY_BUTTON_LEFT_SHOULDER, JOY_BUTTON_RIGHT_SHOULDER])):
		get_viewport().set_input_as_handled()
		var right: bool = event.is_action_pressed("move_right") or event.is_action_pressed("ui_right") \
			or (event is InputEventKey and event.physical_keycode == KEY_E) or (event is InputEventJoypadButton and event.button_index == JOY_BUTTON_RIGHT_SHOULDER)
		journal_turn(1 if right else -1)
		return
	if m in ["journal", "map"] and (event.is_action_pressed("back") or event.is_action_pressed("journal") or event.is_action_pressed("map")):
		get_viewport().set_input_as_handled()
		Sfx.ui("journal_close", -6.0)
		game.resume()
	elif m == "pause" and event.is_action_pressed("pause"):
		get_viewport().set_input_as_handled()
		game.resume()
	elif m == "wardrobe" and (event.is_action_pressed("back") or event.is_action_pressed("wardrobe")):
		get_viewport().set_input_as_handled()
		game.camera_rig.clear_shot()
		game.resume()
	elif m == "photo":
		if event.is_action_pressed("photo_mode") or event.is_action_pressed("back"):
			get_viewport().set_input_as_handled()
			game.player.rig.set_conversing(false)
			game.camera_rig.clear_shot()
			game.resume()
		elif event.is_action_pressed("photo_capture"):
			_capture_photo()
		elif event is InputEventMouseMotion and (event.button_mask & MOUSE_BUTTON_MASK_LEFT):
			var d := CameraRig.points_moved(event as InputEventMouseMotion)
			_photo.yaw -= d.x * 0.0042
			_photo.pitch = clampf(_photo.pitch + d.y * 0.0033, -0.5, 1.2)
		elif event is InputEventMouseButton and event.pressed:
			if event.button_index == MOUSE_BUTTON_WHEEL_UP:
				_photo.dist = maxf(0.7, _photo.dist - 0.15)
			elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
				_photo.dist = minf(7.0, _photo.dist + 0.15)
		elif event is InputEventKey and event.pressed:
			match event.physical_keycode:
				KEY_BRACKETLEFT:
					_photo.fov = maxf(18.0, _photo.fov - 4.0)
				KEY_BRACKETRIGHT:
					_photo.fov = minf(80.0, _photo.fov + 4.0)
				KEY_1:
					game.player.rig.set_conversing(false)
				KEY_2:
					game.player.rig.play_gesture("wave")
				KEY_3:
					game.player.rig.set_conversing(true)
				KEY_4:
					game.player.rig.play_gesture("look_around")


## A soft pool of light: `a` in the middle fading to `b` at the edges (a desk lamp, the pause blur's warmth).
static func _radial_tex(a: Color, b: Color, center := Vector2(0.5, 0.42)) -> GradientTexture2D:
	var g := Gradient.new()
	g.set_color(0, a)
	g.set_color(1, b)
	var t := GradientTexture2D.new()
	t.gradient = g
	t.fill = GradientTexture2D.FILL_RADIAL
	t.fill_from = center
	t.fill_to = center + Vector2(0.62, 0.0)
	t.width = 256
	t.height = 256
	return t
