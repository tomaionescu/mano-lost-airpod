class_name PenPrompt
extends Control
## The interaction prompt as Mano's pen marks in the world (docs/DESIGN.md §5.5, docs/ART_DIRECTION.md, after
## Life is Strange's leader lines): a small pen ring on the thing, a curved leader line out to the open side of
## the screen, and on its end the verb in marker over a short underline, with a sketched key cap holding the
## live key. Only the nearest interactable gets one. The ring and the line draw on (140 ms), then the words fade
## in (80 ms); out is faster (120 ms). Ring and line boil at 8 fps. The HUD hides it in the letterbox.

const RING := 11.0              # ring diameter: about 13 px at 1080p
const LEAD := Vector2(30, 42)   # from the ring to the elbow under the words: a 52-unit (62 px) leader
const SAFE := 53.0              # 64 px at 1080p from the screen edges
const BOTTOM := 175.0           # clear of the subtitle band
const VERB_SIZE := 25           # Shantell, 30 px at 1080p
const KEY_SIZE := 18            # the key letter, 22 px at 1080p
const IN_T := 0.22
const OUT_T := 0.12
const VERBS := ["look", "read", "sit", "listen", "grab", "talk", "use"]
## What a spot's prompt says: the verb first, and the thing, because a SPOT_ marker sits where Mano stands
## rather than on the thing itself, so the ring alone cannot always point at it. Short, in Mano's words.
const SPOT_WORDS := {"velib": "Look at the bike rack", "sign": "Read the note", "lostbox": "Look in the box",
	"north_door": "Look outside", "logo": "Look at the wall", "elevator": "Look at the lift", "rules": "Read the poster",
	"coffee": "Use the machine", "vending": "Look at the snacks", "slide": "Read the slide", "gate": "Look at the gate",
	"coin_planter": "Look in the planter", "stickers": "Read the stickers", "coin_sofa": "Check the sofa"}

var target = null               # Interactable or null
var _words := ""
var _anchor := Vector2.ZERO
var _side := 1.0                # the words go right (1) or left (-1) of the ring
var _up := -1.0                 # above (-1) or below (1)
var _alpha := 0.0
var _draw_t := 1.0
var _box: HBoxContainer
var _verb: Label
var _key: PanelContainer
var _key_text := ""
var _seen := false


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)   # the whole HUD: it draws at screen positions
	_box = HBoxContainer.new()
	_box.add_theme_constant_override("separation", 8)
	_box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_verb = UITheme.over_scene(UITheme.label("", VERB_SIZE, UITheme.marker, UITheme.FILM_WHITE), 6, 0.5) as Label
	_verb.size_flags_vertical = Control.SIZE_SHRINK_END
	_box.add_child(_verb)
	add_child(_box)
	modulate.a = 0.0


## What the prompt says for `it`: "Talk to Toma", "Say hi", "Read the slide"; a spot it does not know says its
## label when that starts with a verb, or just "Look".
static func words_for(it) -> String:
	if it.kind == "npc":
		return it.label
	if SPOT_WORDS.has(it.id):
		return SPOT_WORDS[it.id]
	var first := String(it.label).get_slice(" ", 0).to_lower()
	return String(it.label) if first in VERBS else "Look"


func set_target(t, words := "") -> void:
	if t == target:
		return
	target = t
	if t == null:
		return
	_words = words if words != "" else words_for(t)
	_verb.text = _words
	_seen = false     # snap to the new thing, and draw the marks on again
	_draw_t = 0.0 if _alpha < 0.5 else 0.35


func tick(dt: float, show: bool, camera: Camera3D) -> void:
	var want := 0.0
	if target != null and show and camera:
		# on a person the ring sits just above the hair (prompt_point floats higher, for a label)
		var p: Vector3 = target.look_point() + Vector3.UP * 0.22 if target.kind == "npc" else target.prompt_point()
		if not camera.is_position_behind(p):
			var sp := camera.unproject_position(p)
			_anchor = sp if not _seen else _anchor.lerp(sp, 1.0 - exp(-dt * 30.0))
			_seen = true
			want = 1.0
	_refresh_key()
	var calm: bool = GameState.settings.get("reduce_motion", false)
	if want > 0.0:
		_alpha = move_toward(_alpha, 1.0, dt / 0.06)
		_draw_t = 1.0 if calm else minf(_draw_t + dt / IN_T, 1.0)
	else:
		_alpha = move_toward(_alpha, 0.0, dt / OUT_T)
	modulate.a = _alpha
	visible = _alpha > 0.002
	if visible:
		_place()
		queue_redraw()


## The live key on the cap: E on a keyboard (as the layout prints it), A on a pad.
func _refresh_key() -> void:
	var k := UITheme.action_key("interact")
	if k == _key_text:
		return
	_key_text = k
	if _key:
		_box.remove_child(_key)
		_key.queue_free()
	_key = UITheme.key_cap(k, KEY_SIZE)
	_key.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	_box.add_child(_key)
	if _side < 0.0:
		_box.move_child(_key, 0)


## The words go toward the open side of the screen and stay inside the safe area, above the subtitle band.
func _place() -> void:
	var vp := size
	var bs := _box.get_combined_minimum_size()
	_box.size = bs
	if _side > 0.0 and _anchor.x > vp.x * 0.6:
		_side = -1.0
	elif _side < 0.0 and _anchor.x < vp.x * 0.4:
		_side = 1.0
	if _up < 0.0 and _anchor.y - LEAD.y - bs.y < SAFE:
		_up = 1.0
	elif _up > 0.0 and (_anchor.y - LEAD.y - bs.y > SAFE + 30.0 or _anchor.y + LEAD.y > vp.y - BOTTOM):
		_up = -1.0
	# the verb sits next to the elbow and the key cap on the far end, so the line runs under the words only
	if _key and _key.get_index() != (_box.get_child_count() - 1 if _side > 0.0 else 0):
		_box.move_child(_key, -1 if _side > 0.0 else 0)
	var e := _elbow(bs)
	_box.position = Vector2(e.x + 5.0 if _side > 0.0 else e.x - 5.0 - bs.x, e.y - bs.y - 1.0)
	_box.modulate.a = clampf((_draw_t - 0.62) / 0.38, 0.0, 1.0)


func _elbow(bs: Vector2) -> Vector2:
	var vp := size
	var e := _anchor + Vector2(_side * LEAD.x, _up * LEAD.y)
	# slide the elbow so the words stay on screen (the leader stretches or shortens)
	if _side > 0.0:
		e.x = minf(e.x, vp.x - SAFE - bs.x - 10.0)
	else:
		e.x = maxf(e.x, SAFE + bs.x + 10.0)
	e.y = clampf(e.y, SAFE + bs.y, vp.y - BOTTOM)
	return e


func _draw() -> void:
	if target == null and _alpha <= 0.0:
		return
	var frame := Doodles.boil()
	var under := Color(UITheme.INK_SHADOW, 0.55)
	var ring_k := clampf(_draw_t / 0.3, 0.0, 1.0)
	Doodles.draw(self, "ring", Rect2(_anchor - Vector2(RING, RING) * 0.5, Vector2(RING, RING)), UITheme.FILM_WHITE, 1.6, frame, under, ring_k)
	var lead_k := clampf((_draw_t - 0.25) / 0.5, 0.0, 1.0)
	if lead_k <= 0.0:
		return
	var bs := _box.size
	var e := _elbow(bs)
	var c := Vector2(_anchor.x + _side * LEAD.x * 0.12, e.y)
	var s := _anchor + (c - _anchor).normalized() * (RING * 0.5 + 1.5)
	var rng := RandomNumberGenerator.new()
	rng.seed = 99 + frame * 31
	var pts := PackedVector2Array()
	for i in 13:
		var t := i / 12.0
		var q := s.lerp(c, t).lerp(c.lerp(e, t), t)
		if i > 0 and i < 12:
			q += Vector2(rng.randf_range(-0.35, 0.35), rng.randf_range(-0.35, 0.35))
		pts.append(q)
	# the line runs on under the words, rising a touch, with a flick at the end
	var end := e + Vector2(_side * (_verb.size.x + 4.0), -1.5)
	for i in range(1, 7):
		var t := i / 6.0
		pts.append(e.lerp(end, t) + Vector2(0, 0.5 * sin(t * 5.0 + frame)))
	pts.append(end + Vector2(_side * 3.0, -3.0))
	var lines := Doodles._clip([pts], lead_k)
	for p: PackedVector2Array in lines:
		draw_polyline(p, under, 1.6 + 2.4, true)
	for p: PackedVector2Array in lines:
		draw_polyline(p, UITheme.FILM_WHITE, 1.6, true)
