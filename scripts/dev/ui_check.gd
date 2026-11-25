extends Node
## Dev check (docs/DESIGN.md V2-06): the notebook screens, run headless without the level. The credits and the last
## page name all eight friends; the chapter card writes itself and turns away in about 3.6 s; the built-in title
## lettering is built from Shantell with its AirPod dot, and a hand-lettered res://assets/ui/logo.svg replaces it
## (checked with a stand-in SVG in res://tests/out/, never the real path); the title page is wide
## enough for Continue's "last time" note; the étiquette's handwriting fits on its lines; the settings form fits
## its sheet with nothing to scroll; none of these screens uses capitals, middle-dot strings or emoji.
##   Godot --headless --path . res://scenes/dev/ui_check.tscn      exit code 1 when a check fails

const FILES := ["res://scripts/ui/menus.gd", "res://scripts/ui/chapter_card.gd", "res://scripts/ui/title_logo.gd",
	"res://scripts/ui/notebook_cover.gd", "res://scripts/ui/paper_sheet.gd", "res://scripts/ui/tape.gd",
	"res://scripts/ui/ink.gd", "res://scripts/ui/die_cut.gd"]
## GameState sends dev scenes to res://tests/out/ (V2-33), so this never lands in the user folder.
var SVG: String = GameState.base_dir + "logo_check.test.svg"

var _fails: Array = []
var _ui: Control


func _ready() -> void:
	UITheme.init()
	_ui = Control.new()
	_ui.size = Vector2(1600, 900)
	add_child(_ui)

	# everyone the game is made for
	var to := Menus.dedication()
	for f in Menus.FRIENDS:
		_check("the dedication names %s" % f, f in to)
	_check("eight friends", Menus.FRIENDS.size() == 8)
	var cut := to.find(", Ishita")
	_check("the last page breaks the dedication after Silvia", cut > 0 and to.substr(0, cut + 1).ends_with("Silvia,"))

	# the chapter card: about 3.6 s from the black to the page turned away
	var card := ChapterCard.new()
	card.time_text = "17:42"
	card.date = "jeudi 15 octobre"
	card.place = "Amphi 4"
	var t0 := Time.get_ticks_msec()
	_ui.add_child(card)
	var gone := [false]
	card.gone.connect(func(): gone[0] = true)
	while not gone[0] and Time.get_ticks_msec() - t0 < 8000:
		await get_tree().process_frame
	var secs := (Time.get_ticks_msec() - t0) / 1000.0
	print("[test] chapter card: %.2f s" % secs)
	_check("the chapter card takes about 3.6 s (%.2f)" % secs, gone[0] and secs > 3.3 and secs < 3.95)

	# the built-in lettering, and the hand-lettered SVG that replaces it
	var logo := TitleLogo.new()
	_ui.add_child(logo)
	await _frames(1)
	_check("the interim logo sets every letter", logo._glyphs.size() == "Mano &".length() + "the lost AirPod".length())
	_check("the interim logo is %d wide" % int(TitleLogo.WIDTH), is_equal_approx(logo.size.x, TitleLogo.WIDTH))
	_check("an AirPod dots the i", not logo._dot.is_empty())
	_check("no SVG logo yet: interim lettering", logo._cut == null or FileAccess.file_exists(TitleLogo.LOGO))
	var f := FileAccess.open(SVG, FileAccess.WRITE)
	f.store_string('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="150" viewBox="0 0 400 150">'
		+ '<path d="M20 120 L60 30 L100 120 Z M130 40 h60 v80 h-60 Z" fill="#25221e"/>'
		+ '<circle cx="300" cy="75" r="50" fill="#25221e"/></svg>')
	f.close()
	var hand := TitleLogo.new()
	hand.logo_path = SVG
	_ui.add_child(hand)
	await _frames(1)
	_check("an SVG logo replaces the lettering", hand._cut != null and hand._glyphs.is_empty())
	_check("the SVG sticker keeps the logo's width", is_equal_approx(hand.size.x, TitleLogo.WIDTH))
	_check("the SVG keeps its proportions", hand._cut != null and absf(hand._cut_rect.size.y / hand._cut_rect.size.x - 150.0 / 400.0) < 0.02)
	DirAccess.remove_absolute(ProjectSettings.globalize_path(SVG))

	# the title page fits Continue's note, the étiquette fits Mano's handwriting
	var menus := Menus.new()
	var note := "last time: the accueil, 23:45"
	var page := menus._menu_page([["Continue", func(): pass, note], ["New game", func(): pass, ""], ["Quit", func(): pass, ""]])
	var nw := UITheme.pen.get_string_size(note, HORIZONTAL_ALIGNMENT_LEFT, -1, 25).x
	_check("the title page is wide enough for the note", page.size.x >= page.margin_x + 22.0 + nw)
	page.free()
	var cover := menus._cover(4, Vector2(500, 650))
	_ui.add_child(cover)
	await _frames(1)
	for v: Label in cover.values():
		_check("'%s' fits on its étiquette line" % v.text, v.position.x + v.get_combined_minimum_size().x <= cover.label_rect.end.x - 12.0)
	cover.queue_free()

	# the settings form: two printed columns that fit the sheet, the buttons below them
	add_child(menus)
	menus.show_settings(func(): pass)
	await _frames(3)
	var cols := 0
	for sheet in menus.current.get_children():
		if sheet is PaperSheet:
			for c in sheet.get_children():
				if c is VBoxContainer:
					cols += 1
					_check("a settings column fits the form (%d)" % int(c.size.y), c.position.y + c.size.y <= Menus.SETTINGS_SIZE.y - 70.0)
	_check("the settings form has two columns", cols == 2)
	_check("the settings form fits a 16:9 window", Menus.SETTINGS_SIZE.y <= 860.0 and Menus.SETTINGS_SIZE.x <= 1500.0)
	menus.show_credits(func(): pass)
	await _frames(2)
	_check("the credits open with the dedication", _has_text(menus.current, to))
	menus.queue_free()

	# no template chrome in these screens
	for path in FILES:
		var src := FileAccess.get_file_as_string(path)
		_check("%s: no to_upper()" % path, not "to_upper(" in src)
		_check("%s: no middle-dot strings" % path, not "  ·  " in src and not " · " in src)
		var emoji := false
		for i in src.length():
			var c := src.unicode_at(i)
			emoji = emoji or (c >= 0x2600 and c <= 0x27BF) or c >= 0x1F000
		_check("%s: no emoji" % path, not emoji)

	for fail in _fails:
		print("[test] FAIL ", fail)
	print("[test] ui_check: %d failed" % _fails.size())
	get_tree().quit(1 if not _fails.is_empty() else 0)


func _check(what: String, ok: bool) -> void:
	if not ok:
		_fails.append(what)


func _has_text(n: Node, text: String) -> bool:
	if n is Label and (n as Label).text == text:
		return true
	for c in n.get_children():
		if _has_text(c, text):
			return true
	return false


func _frames(n: int) -> void:
	for i in n:
		await get_tree().process_frame
