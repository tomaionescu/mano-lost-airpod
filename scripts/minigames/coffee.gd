extends Node
## The coffee machine ate the coins: mash E / Space to shake it loose before time runs out.
## With Joaquin's tip (flags.joaquin_tip, chapter 2: "Hit the left side, not the right.") every shake counts a
## little more, and the tip is written under the title.

const DURATION := 6.0
const SHAKE := 9.0
const SHAKE_TIP := 11.5

var game
var _done: Callable
var _v := 0.0
var _time := DURATION
var _end := 0.0
var _won := false
var _wobble := 0.0
var _rig_yaw := 0.0
var _fill: ColorRect
var _meter: ColorRect
var _timer_label: Label
var _layer: CanvasLayer


func setup(g, _opts: Dictionary, done: Callable) -> void:
	game = g
	_done = done
	var a: Dictionary = game.binder.anchors.get("coffee", {})
	var pos: Vector3
	var yaw: float
	if a.is_empty():
		var spot: Dictionary = game.binder.spots.get("coffee", {"pos": game.player.global_position})
		pos = spot.pos
		yaw = game.player.facing_yaw() + PI
	else:
		pos = a.pos
		yaw = a.yaw
	var fwd := Vector3(sin(yaw), 0, cos(yaw))
	var side := Vector3(fwd.z, 0, -fwd.x)
	game.player.teleport(pos + fwd * 0.62, yaw + PI)
	_rig_yaw = yaw + PI
	var from := pos + fwd * 2.0 + side * 1.2 + Vector3.UP * 1.55
	var look := pos + fwd * 0.3 + Vector3.UP * 1.15
	game.camera_rig.set_shot(from, look, 38.0, from.distance_to(look))
	_build_ui()
	Sfx.play("machine_shake", -10.0)


func _build_ui() -> void:
	_layer = CanvasLayer.new()
	_layer.layer = 15
	add_child(_layer)
	var root := Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.theme = UITheme.theme
	_layer.add_child(root)
	var top := VBoxContainer.new()
	top.anchor_left = 0.5
	top.anchor_right = 0.5
	top.offset_left = -400
	top.offset_right = 400
	top.offset_top = 56
	var t := UITheme.shadowed(UITheme.label("The machine is stuck", 44, UITheme.display_xb, UITheme.INK), 3, 0.6)
	t.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	top.add_child(t)
	var tip: bool = GameState.flags.get("joaquin_tip", false)
	var s := UITheme.shadowed(UITheme.label("Joaquin's tip: the left side, not the right" if tip else "Shake it loose before it gives up on you", 26, UITheme.hand, UITheme.GOLD), 2, 0.6)
	s.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	top.add_child(s)
	root.add_child(top)
	var bottom := HBoxContainer.new()
	bottom.anchor_left = 0.5
	bottom.anchor_right = 0.5
	bottom.anchor_top = 1.0
	bottom.anchor_bottom = 1.0
	bottom.offset_left = -330
	bottom.offset_right = 330
	bottom.offset_top = -110
	bottom.offset_bottom = -70
	bottom.add_theme_constant_override("separation", 14)
	bottom.add_child(UITheme.key_cap(UITheme.action_key("confirm"), 18))
	bottom.add_child(UITheme.shadowed(UITheme.label("mash!", 24, UITheme.hand, UITheme.INK), 2, 0.6))
	_meter = ColorRect.new()
	_meter.color = Color(0, 0, 0, 0.55)
	_meter.custom_minimum_size = Vector2(420, 18)
	_meter.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	_fill = ColorRect.new()
	_fill.color = UITheme.GOLD
	_fill.size = Vector2(0, 18)
	_meter.add_child(_fill)
	bottom.add_child(_meter)
	_timer_label = UITheme.shadowed(UITheme.label("6.0 s", 20, UITheme.mono, UITheme.INK), 1, 0.6)
	bottom.add_child(_timer_label)
	root.add_child(bottom)


func _unhandled_input(event: InputEvent) -> void:
	if _end > 0.0:
		return
	if event.is_action_pressed("confirm"):
		get_viewport().set_input_as_handled()
		_v += SHAKE_TIP if GameState.flags.get("joaquin_tip", false) else SHAKE
		_wobble = 1.0
		game.camera_rig.add_trauma(0.18)
		Sfx.play("machine_shake", -4.0, "SFX", randf_range(0.9, 1.15))


func _process(dt: float) -> void:
	if _end > 0.0:
		_end -= dt
		if _end <= 0.0:
			_done.call(_won)
		return
	_time -= dt
	_v = maxf(0.0, _v - 30.0 * dt)
	_wobble = maxf(0.0, _wobble - dt * 6.0)
	# Mano throws his weight into it
	if game.player.rig:
		game.player.rig.rotation.y = _rig_yaw + sin(Time.get_ticks_msec() * 0.05) * 0.08 * _wobble
		game.player.rig.rotation.z = sin(Time.get_ticks_msec() * 0.043) * 0.05 * _wobble
	if _v >= 100.0:
		_v = 100.0
		_won = true
		_end = 1.0
		Sfx.play("machine_clunk")
		game.camera_rig.add_trauma(0.45)
		if game.player.rig:
			game.player.rig.rotation.z = 0.0
	elif _time <= 0.0:
		_won = false
		_end = 0.7
		Sfx.ui("ui_back")
		if game.player.rig:
			game.player.rig.rotation.z = 0.0
	_fill.size = Vector2(_meter.size.x * _v / 100.0, 18)
	_fill.color = UITheme.GOOD if _v > 70.0 else UITheme.GOLD
	_timer_label.text = "%.1f s" % maxf(_time, 0.0)
